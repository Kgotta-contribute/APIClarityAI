import json
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import create_engine, text
from supabase import create_client, Client
from app.config.config import settings
from app.services.transcription_service import transcribe_audio_file


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"

DATABASE_URL = settings.database_url or os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 10}) if DATABASE_URL else None

SUPABASE_URL = settings.supabase_url or os.getenv("SUPABASE_URL")
SUPABASE_KEY = settings.supabase_key or os.getenv("SUPABASE_KEY")
supabase_client: Optional[Client] = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None

# Statuses that mean "this file is not safe to delete yet" -- either it hasn't
# been uploaded, or it's actively being processed. cleanup_old_files() must
# never touch a row in one of these states, or it can delete a file out from
# under an in-flight upload/transcription and crash that request.
IN_FLIGHT_STATUSES = (
    "pending",
    "processing",
    "queued",
    "extracting_audio",
    "transcribing",
)


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def ensure_storage() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    TRANSCRIPT_DIR.mkdir(exist_ok=True)

    if engine:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        business_group TEXT NOT NULL DEFAULT 'Default',
                        options_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        completed_at TEXT
                    );
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS files (
                        file_id TEXT PRIMARY KEY,
                        job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                        file_name TEXT NOT NULL,
                        size_bytes BIGINT NOT NULL DEFAULT 0,
                        mime_type TEXT,
                        status TEXT NOT NULL,
                        stage TEXT NOT NULL,
                        percentage REAL NOT NULL DEFAULT 0,
                        current_chunk INT NOT NULL DEFAULT 0,
                        total_chunks INT NOT NULL DEFAULT 1,
                        storage_path TEXT,
                        transcript_path TEXT,
                        raw_transcript_path TEXT,
                        duration REAL NOT NULL DEFAULT 0,
                        error_details TEXT,
                        received_at TEXT NOT NULL,
                        uploaded_at TEXT,
                        completed_at TEXT
                    );
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS transcript_chunks (
                        id TEXT PRIMARY KEY,
                        file_id TEXT NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,
                        chunk_number INT NOT NULL,
                        text TEXT NOT NULL,
                        start_time REAL NOT NULL,
                        end_time REAL NOT NULL,
                        speaker TEXT NOT NULL,
                        embedding vector(1024)
                    );
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS visitor_stats (
                        stat_key TEXT PRIMARY KEY,
                        stat_value INT NOT NULL
                    );
                    """
                )
            )
            conn.execute(
                text(
                    "INSERT INTO visitor_stats (stat_key, stat_value) VALUES ('visits', 1024) ON CONFLICT (stat_key) DO NOTHING;"
                )
            )

        try:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE transcript_chunks ALTER COLUMN embedding TYPE vector(1024);"))
        except Exception:
            pass


def cleanup_old_files(max_files: int = 20) -> None:
    """
    Safely purges files beyond the top `max_files` most recent.
    - Excludes any file that is pending upload OR actively processing, so an
      in-flight upload/transcription can never be deleted out from under it.
    - Runs strictly upon new job/upload creation, never on read/query events.
    - Handles cascades across transcript_chunks, files, jobs, disk, and
      Supabase Storage.
    """
    ensure_storage()
    if not engine:
        return
    try:
        with engine.begin() as conn:
            old_rows = conn.execute(
                text(
                    """
                    SELECT job_id, file_id FROM files
                    WHERE status NOT IN :in_flight_statuses
                    ORDER BY received_at DESC
                    OFFSET :max_files
                    """
                ),
                {"in_flight_statuses": tuple(IN_FLIGHT_STATUSES), "max_files": max_files},
            ).fetchall()
            old_files = [row_to_dict(row) for row in old_rows]

        for item in old_files:
            try:
                delete_file(item["job_id"], item["file_id"])
                print(f"Safe retention cleanup: Purged old file {item['file_id']} beyond top {max_files}")
            except Exception as item_err:
                print(f"Error purging old file {item['file_id']}: {item_err}")
    except Exception as exc:
        print(f"Notice during file cleanup: {exc}")


def get_visitor_count() -> int:
    ensure_storage()
    with engine.begin() as conn:
        result = conn.execute(text("SELECT stat_value FROM visitor_stats WHERE stat_key = 'visits'")).fetchone()
        return result[0] if result else 1024


def increment_visitor_count() -> int:
    ensure_storage()
    with engine.begin() as conn:
        conn.execute(text("UPDATE visitor_stats SET stat_value = stat_value + 1 WHERE stat_key = 'visits';"))
        result = conn.execute(text("SELECT stat_value FROM visitor_stats WHERE stat_key = 'visits'")).fetchone()
        return result[0] if result else 1025


def row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)


def create_job(file_names: list[str], business_group: str, options: dict[str, Any]) -> dict[str, Any]:
    ensure_storage()
    cleanup_old_files(max_files=20)
    job_id = f"JOB-{uuid.uuid4().hex[:12].upper()}"
    created_at = utc_now()
    file_ids: dict[str, str] = {}

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO jobs (job_id, status, business_group, options_json, created_at) VALUES (:job_id, :status, :business_group, :options_json, :created_at)"
            ),
            {
                "job_id": job_id,
                "status": "Received",
                "business_group": business_group or "Default",
                "options_json": json.dumps(options),
                "created_at": created_at,
            },
        )
        for index, file_name in enumerate(file_names):
            file_id = f"FILE-{uuid.uuid4().hex[:12].upper()}"
            file_ids[str(index)] = file_id
            file_ids[file_name] = file_id
            conn.execute(
                text(
                    """
                    INSERT INTO files
                        (file_id, job_id, file_name, status, stage, received_at)
                    VALUES (:file_id, :job_id, :file_name, :status, :stage, :received_at)
                    """
                ),
                {
                    "file_id": file_id,
                    "job_id": job_id,
                    "file_name": file_name,
                    "status": "pending",
                    "stage": "received",
                    "received_at": created_at,
                },
            )
    return {"jobID": job_id, "fileID": file_ids}


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    ensure_storage()
    with engine.begin() as conn:
        result = conn.execute(text("SELECT * FROM jobs WHERE job_id = :job_id"), {"job_id": job_id}).fetchone()
        return row_to_dict(result) if result else None


def get_file(job_id: str, file_id: str) -> Optional[dict[str, Any]]:
    ensure_storage()
    with engine.begin() as conn:
        result = conn.execute(
            text("SELECT * FROM files WHERE job_id = :job_id AND file_id = :file_id"),
            {"job_id": job_id, "file_id": file_id},
        ).fetchone()
        return row_to_dict(result) if result else None


def get_signed_url_for_file(job_id: str, file_id: str, expires_in: int = 3600) -> Optional[str]:
    file_row = get_file(job_id, file_id)
    if not file_row or not supabase_client:
        return None
    rel_path = f"{job_id}/{file_id}/{Path(file_row['file_name']).name}"
    try:
        res = supabase_client.storage.from_("audio-files").create_signed_url(rel_path, expires_in)
        return res.get("signedUrl") or res.get("signedURL")
    except Exception as e:
        print(f"Error generating signed URL for {rel_path}: {e}")
        return None


def list_files(page: int = 1, limit: int = 20) -> tuple[list[dict[str, Any]], int]:
    ensure_storage()
    effective_limit = min(limit, 20)
    offset = max(page - 1, 0) * effective_limit
    with engine.begin() as conn:
        total_row = conn.execute(text("SELECT COUNT(*) AS total FROM files")).fetchone()
        total = min(total_row[0] if total_row else 0, 20)

        rows = conn.execute(
            text(
                """
                SELECT f.*, j.business_group
                FROM files f
                JOIN jobs j ON j.job_id = f.job_id
                ORDER BY f.received_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": effective_limit, "offset": offset},
        ).fetchall()
        return [row_to_dict(row) for row in rows], total


def save_upload(job_id: str, file_id: str, upload_file: Any) -> dict[str, Any]:
    ensure_storage()
    cleanup_old_files(max_files=20)
    existing = get_file(job_id, file_id)
    if not existing:
        raise ValueError("File record not found")

    safe_name = Path(existing["file_name"]).name
    target = UPLOAD_DIR / f"{job_id}_{file_id}_{safe_name}"

    file_bytes = upload_file.file.read()
    target.write_bytes(file_bytes)
    size_bytes = len(file_bytes)
    content_type = getattr(upload_file, "content_type", None) or "application/octet-stream"

    # Enforce 25 MB file size limit
    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
    if size_bytes > MAX_FILE_SIZE_BYTES:
        target.unlink(missing_ok=True)  # clean up the file we just wrote
        raise ValueError(f"File '{existing['file_name']}' exceeds the 25 MB size limit ({size_bytes / 1024 / 1024:.1f} MB uploaded). Please upload a file under 25 MB.")


    supabase_storage_path = f"{job_id}/{file_id}/{safe_name}"
    if supabase_client:
        try:
            supabase_client.storage.from_("audio-files").upload(
                path=supabase_storage_path,
                file=file_bytes,
                file_options={"content-type": content_type, "upsert": "true"}
            )
            print(f"Uploaded audio file to Supabase Storage bucket 'audio-files': {supabase_storage_path}")
        except Exception as exc:
            print(f"Supabase storage upload notice: {exc}")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE files
                SET size_bytes = :size_bytes, mime_type = :mime_type, status = :status, stage = :stage, percentage = :percentage,
                    current_chunk = :current_chunk, total_chunks = :total_chunks, storage_path = :storage_path, uploaded_at = :uploaded_at
                WHERE job_id = :job_id AND file_id = :file_id
                """
            ),
            {
                "size_bytes": size_bytes,
                "mime_type": content_type,
                "status": "processing",
                "stage": "queued",
                "percentage": 10,
                "current_chunk": 1,
                "total_chunks": 5,
                "storage_path": str(target),
                "uploaded_at": utc_now(),
                "job_id": job_id,
                "file_id": file_id,
            },
        )
        conn.execute(text("UPDATE jobs SET status = :status WHERE job_id = :job_id"), {"status": "Processing", "job_id": job_id})
    return {"jobID": job_id, "fileID": file_id, "FileName": existing["file_name"], "uploadStatus": "success"}


def update_file_progress(job_id: str, file_id: str, status: str, stage: str, percentage: float, current_chunk: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE files
                SET status = :status, stage = :stage, percentage = :percentage, current_chunk = :current_chunk
                WHERE job_id = :job_id AND file_id = :file_id
                """
            ),
            {
                "status": status,
                "stage": stage,
                "percentage": percentage,
                "current_chunk": current_chunk,
                "job_id": job_id,
                "file_id": file_id,
            },
        )


def create_sliding_window_chunks(segments: list[dict[str, Any]], window_size: int = 3, step: int = 2) -> list[dict[str, Any]]:
    if not segments:
        return []
    if len(segments) <= 2:
        return segments

    sliding = []
    for i in range(0, len(segments), step):
        win = segments[i : i + window_size]
        if not win:
            continue
        combined_text = " ".join(s["text"].strip() for s in win if s.get("text"))
        if not combined_text:
            continue
        speakers = list(dict.fromkeys(s.get("speaker") for s in win if s.get("speaker")))
        spk_label = ", ".join(speakers) if speakers else "Speaker 1"
        sliding.append({
            "chunk_number": len(sliding) + 1,
            "text": combined_text,
            "start_time": win[0]["start_time"],
            "end_time": win[-1]["end_time"],
            "speaker": spk_label
        })
    return sliding


def process_file(job_id: str, file_id: str) -> None:
    try:
        file_row = get_file(job_id, file_id)
        if not file_row:
            return

        job_row = get_job(job_id)
        selected_language = None
        if job_row and job_row.get("options_json"):
            try:
                opts = json.loads(job_row["options_json"]) if isinstance(job_row["options_json"], str) else job_row["options_json"]
                selected_language = opts.get("language")
            except Exception as e:
                print(f"Notice reading job options_json: {e}")

        def progress_cb(stage: str, percentage: float, current_chunk: int):
            update_file_progress(job_id, file_id, "processing", stage, percentage, current_chunk)

        segments = transcribe_audio_file(file_row["storage_path"], progress_cb=progress_cb, language=selected_language)
        progress_cb("saving_transcript", 95.0, 5)

        raw_text = " ".join(segment["text"] for segment in segments)
        diarized_text = "\n".join(
            f"[{int(segment['start_time'] // 60):02d}:{int(segment['start_time'] % 60):02d}] "
            f"{segment['speaker']}: {segment['text']}"
            for segment in segments
        )
        transcript_path = TRANSCRIPT_DIR / f"{job_id}_{file_id}_diarized.txt"
        raw_path = TRANSCRIPT_DIR / f"{job_id}_{file_id}_raw.txt"
        transcript_path.write_text(diarized_text, encoding="utf-8")
        raw_path.write_text(raw_text, encoding="utf-8")

        from app.services.embedding_service import get_embeddings_batch
        semantic_chunks = create_sliding_window_chunks(segments, window_size=3, step=2)
        chunk_texts = [c["text"] for c in semantic_chunks]
        embeddings = get_embeddings_batch(chunk_texts) if chunk_texts else []

        with engine.begin() as conn:
            conn.execute(text("DELETE FROM transcript_chunks WHERE file_id = :file_id"), {"file_id": file_id})
            for idx, c in enumerate(semantic_chunks):
                emb_val = str(embeddings[idx]) if idx < len(embeddings) else None
                conn.execute(
                    text(
                        """
                        INSERT INTO transcript_chunks
                            (id, file_id, chunk_number, text, start_time, end_time, speaker, embedding)
                        VALUES (:id, :file_id, :chunk_number, :text, :start_time, :end_time, :speaker, :embedding)
                        """
                    ),
                    {
                        "id": f"CHUNK-{uuid.uuid4().hex[:12].upper()}",
                        "file_id": file_id,
                        "chunk_number": c["chunk_number"],
                        "text": c["text"],
                        "start_time": c["start_time"],
                        "end_time": c["end_time"],
                        "speaker": c["speaker"],
                        "embedding": emb_val,
                    },
                )
            conn.execute(
                text(
                    """
                    UPDATE files
                    SET status = :status, stage = :stage, percentage = :percentage, current_chunk = :current_chunk, total_chunks = :total_chunks,
                        transcript_path = :transcript_path, raw_transcript_path = :raw_transcript_path, duration = :duration, completed_at = :completed_at
                    WHERE job_id = :job_id AND file_id = :file_id
                    """
                ),
                {
                    "status": "completed",
                    "stage": "completed",
                    "percentage": 100,
                    "current_chunk": len(segments),
                    "total_chunks": len(segments),
                    "transcript_path": str(transcript_path),
                    "raw_transcript_path": str(raw_path),
                    "duration": segments[-1]["end_time"] if segments else 0,
                    "completed_at": utc_now(),
                    "job_id": job_id,
                    "file_id": file_id,
                },
            )

            remaining_row = conn.execute(
                text(
                    "SELECT COUNT(*) AS total FROM files WHERE job_id = :job_id AND status NOT IN ('completed', 'failed', 'stopped')"
                ),
                {"job_id": job_id},
            ).fetchone()
            remaining = remaining_row[0] if remaining_row else 0

            if remaining == 0:
                conn.execute(
                    text("UPDATE jobs SET status = :status, completed_at = :completed_at WHERE job_id = :job_id"),
                    {"status": "Completed", "completed_at": utc_now(), "job_id": job_id},
                )
    except Exception as exc:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE files
                    SET status = :status, stage = :stage, error_details = :error_details
                    WHERE job_id = :job_id AND file_id = :file_id
                    """
                ),
                {"status": "Failed", "stage": "failed", "error_details": str(exc), "job_id": job_id, "file_id": file_id},
            )
            conn.execute(text("UPDATE jobs SET status = :status WHERE job_id = :job_id"), {"status": "Failed", "job_id": job_id})


def file_status_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fileID": row["file_id"],
        "fileName": row["file_name"],
        "status": row["status"],
        "progress": {
            "stage": row["stage"],
            "currentChunk": row["current_chunk"],
            "totalChunks": row["total_chunks"],
            "percentage": row["percentage"],
        },
        "errorDetails": row["error_details"],
    }


def job_status_payload(job_id: str) -> dict[str, Any]:
    ensure_storage()
    with engine.begin() as conn:
        job_row = conn.execute(text("SELECT * FROM jobs WHERE job_id = :job_id"), {"job_id": job_id}).fetchone()
        if not job_row:
            raise ValueError("Job not found")
        job = row_to_dict(job_row)
        files = conn.execute(text("SELECT * FROM files WHERE job_id = :job_id ORDER BY received_at"), {"job_id": job_id}).fetchall()
    return {
        "jobID": job_id,
        "status": job["status"],
        "files": [file_status_payload(row_to_dict(row)) for row in files],
    }


def get_chunks(job_id: str, file_id: str) -> dict[str, Any]:
    file_row = get_file(job_id, file_id)
    if not file_row:
        raise ValueError("File not found")
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT * FROM transcript_chunks WHERE file_id = :file_id ORDER BY chunk_number"),
            {"file_id": file_id},
        ).fetchall()
    segments = [row_to_dict(row) for row in rows]
    return {
        "jobID": job_id,
        "fileID": file_id,
        "fileName": file_row["file_name"],
        "totalSize": file_row["size_bytes"],
        "chunks": [
            {
                "chunkNumber": segment["chunk_number"],
                "totalChunks": len(segments) or 1,
                "startByte": 0,
                "endByte": max(file_row["size_bytes"] - 1, 0),
                "sizeBytes": file_row["size_bytes"],
                "startTime": segment["start_time"],
                "endTime": segment["end_time"],
                "transcriptSegments": [
                    {
                        "start": segment["start_time"],
                        "end": segment["end_time"],
                        "text": segment["text"],
                        "speaker": segment["speaker"],
                    }
                ],
            }
            for segment in segments
        ],
    }


def get_transcripts_for_files(files: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    for file_ref in files:
        row = get_file(file_ref["jobId"], file_ref["fileId"])
        if not row:
            continue
        t_path = row.get("transcript_path") or row.get("raw_transcript_path")
        if t_path and Path(t_path).exists():
            content = Path(t_path).read_text(encoding="utf-8")
            result.append({
                "file_name": row["file_name"],
                "text": content
            })
    return result


def transcript_text_for_files(files: list[dict[str, str]]) -> str:
    items = get_transcripts_for_files(files)
    texts: list[str] = []
    for item in items:
        label = f"=== TRANSCRIPT: {item['file_name']} ===\n{item['text']}\n=== END OF TRANSCRIPT: {item['file_name']} ==="
        texts.append(label)
    return "\n\n".join(texts)


def delete_file(job_id: str, file_id: str) -> None:
    row = get_file(job_id, file_id)
    if not row:
        return

    # Each of the three deletion targets (local disk, Supabase Storage, DB)
    # lives in a different system and can fail independently. Each one gets
    # its own try/except so that, for example, a locked local file or a
    # transient network blip on the Storage API can never prevent the other
    # two from completing.
    for path_key in ("storage_path", "transcript_path", "raw_transcript_path"):
        file_path_value = row.get(path_key)
        if not file_path_value:
            continue
        try:
            path = Path(file_path_value)
            if path.exists():
                path.unlink()
        except Exception as e:
            print(f"Notice deleting local file for {path_key} ({file_path_value}): {e}")

    if supabase_client:
        try:
            rel_path = f"{job_id}/{file_id}/{Path(row['file_name']).name}"
            supabase_client.storage.from_("audio-files").remove([rel_path])
        except Exception as e:
            print(f"Notice deleting from Supabase storage: {e}")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM transcript_chunks WHERE file_id = :file_id"), {"file_id": file_id})
        conn.execute(text("DELETE FROM files WHERE job_id = :job_id AND file_id = :file_id"), {"job_id": job_id, "file_id": file_id})
        remaining_row = conn.execute(text("SELECT COUNT(*) AS total FROM files WHERE job_id = :job_id"), {"job_id": job_id}).fetchone()
        remaining = remaining_row[0] if remaining_row else 0
        if remaining == 0:
            conn.execute(text("DELETE FROM jobs WHERE job_id = :job_id"), {"job_id": job_id})


def search_transcript_chunks(
    query_text: str,
    file_ids: list[str] | None = None,
    match_count: int = 10,
    match_threshold: float = 0.0,
) -> list[dict[str, Any]]:
    import re
    from app.services.embedding_service import get_embedding
    from app.services.reranker_service import rerank_chunks

    query_vec = get_embedding(query_text)
    vec_str = str(query_vec)

    # Stage 1: High-Recall Candidate Pool (Top 20 candidates via Dense pgvector)
    candidate_limit = max(match_count * 2, 20)

    with engine.begin() as conn:
        res = conn.execute(
            text(
                """
                SELECT id, file_id, chunk_number, text, start_time, end_time, speaker, similarity
                FROM match_transcript_chunks(
                    CAST(:query_embedding AS vector),
                    :match_file_ids,
                    :match_count,
                    :match_threshold
                )
                """
            ),
            {
                "query_embedding": vec_str,
                "match_file_ids": file_ids if file_ids else None,
                "match_count": candidate_limit,
                "match_threshold": match_threshold,
            },
        ).fetchall()
        candidates = [row_to_dict(row) for row in res]

        # Stage 1.5: Lexical entity & keyword scoring
        stopwords = {"what", "when", "where", "which", "while", "would", "about", "there", "their", "these", "those", "from", "with", "that", "this", "have", "been", "does", "said", "mean"}
        q_words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{4,}\b', query_text) if w.lower() not in stopwords]

        for item in candidates:
            dense_sim = float(item.get("similarity", 0.0))
            item["dense_similarity"] = dense_sim
            lex_score = 0.0
            if q_words:
                text_lower = item.get("text", "").lower()
                matches = sum(1 for w in q_words if w in text_lower)
                lex_score = matches / len(q_words)
            item["lexical_score"] = lex_score
            item["fused_score"] = dense_sim + (lex_score * 0.15)

        candidates.sort(key=lambda x: x.get("fused_score", 0.0), reverse=True)

        # Stage 2: Cross-Encoder High-Precision Reranking via BAAI/bge-reranker-base (Top 10 chunks)
        # Final Score = 0.50·reranker + 0.30·dense + 0.20·lexical
        reranked_chunks = rerank_chunks(query_text, candidates, top_k=match_count, w1=0.50, w2=0.30, w3=0.20)
        return reranked_chunks
