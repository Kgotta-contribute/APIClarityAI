import asyncio
import json
import math
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.services import local_store
from app.services.rate_limiter import chat_rate_limiter, get_client_ip

router = APIRouter()

@router.get("/jobs")
def get_jobs():
    return {"jobs": []}


@router.post("/v1/create")
def create_job(payload: dict[str, Any]):
    file_names = payload.get("fileDetails") or payload.get("fileNames") or []
    if not isinstance(file_names, list) or not file_names:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if len(file_names) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 files allowed")
    return local_store.create_job(
        [str(file_name) for file_name in file_names],
        str(payload.get("businessGroup") or "Default"),
        dict(payload.get("options") or {}),
    )


@router.get("/v1/visitor-count")
def get_visitor_count():
    return {"visits": local_store.get_visitor_count()}


@router.post("/v1/visitor-count/increment")
def increment_visitor_count():
    return {"visits": local_store.increment_visitor_count()}



def dispatch_transcription_task(job_id: str, file_id: str, background_tasks: BackgroundTasks) -> None:
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            from app.tasks import process_file_task
            process_file_task.delay(job_id, file_id)
            print(f"Dispatched Celery task process_file_task for {job_id}/{file_id}")
            return
        except Exception as exc:
            print(f"Celery dispatch failed ({exc}), falling back to FastAPI BackgroundTasks")

    print(f"Using FastAPI BackgroundTasks for local processing of {job_id}/{file_id}")
    background_tasks.add_task(local_store.process_file, job_id, file_id)


@router.post("/v1/jobs/{job_id}/files/{file_id}/upload")
async def upload_file(job_id: str, file_id: str, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    try:
        response = local_store.save_upload(job_id, file_id, file)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        await file.close()

    dispatch_transcription_task(job_id, file_id, background_tasks)
    return response


@router.get("/v1/jobs/{job_id}/status")
async def job_status(job_id: str):
    async def events():
        for _ in range(600):
            try:
                payload = local_store.job_status_payload(job_id)
            except ValueError:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                return

            yield f"data: {json.dumps(payload)}\n\n"
            statuses = [file_info["status"].lower() for file_info in payload["files"]]
            if statuses and all(status in {"completed", "failed", "error", "stopped"} for status in statuses):
                return
            await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream")


def calc_processing_duration(started: str | None, completed: str | None) -> str:
    if not started or not completed:
        return "-"
    try:
        from datetime import datetime
        t1 = datetime.fromisoformat(started.replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(completed.replace("Z", "+00:00"))
        diff = (t2 - t1).total_seconds()
        if diff < 0:
            return "-"
        if diff < 60:
            return f"{int(diff)}s"
        mins = int(diff // 60)
        secs = int(diff % 60)
        return f"{mins}m {secs}s"
    except Exception:
        return "-"


@router.get("/v1/allData")
def all_data(
    cursor: int = Query(1, ge=1),
    page: int | None = Query(None, ge=1),
    limit: int = Query(100, ge=1, le=1000),
):
    current_page = page or cursor
    rows, total = local_store.list_files(current_page, limit)
    records = []
    for row in rows:
        started = row.get("uploaded_at") or row.get("received_at")
        completed = row.get("completed_at")
        records.append(
            {
                "jobID": row["job_id"],
                "fileID": row["file_id"],
                "fileName": row["file_name"],
                "sizeBytes": row["size_bytes"],
                "fileStatus": row["status"],
                "userName": "Local User",
                "status": row["status"],
                "receivedAt": row["received_at"],
                "sourceFileName": row["storage_path"] or row["file_name"],
                "duration": row["duration"],
                "startedProcessingAt": started,
                "processedAt": completed,
                "fileProcessingDuration": calc_processing_duration(started, completed),
            }
        )
    return {
        "records": records,
        "pagination": {
            "page": current_page,
            "limit": limit,
            "total": total,
            "totalPages": max(1, math.ceil(total / limit)),
        },
    }


@router.get("/v1/jobs/{job_id}/files/{file_id}/download")
def download_raw(job_id: str, file_id: str):
    row = local_store.get_file(job_id, file_id)
    if not row or not row.get("raw_transcript_path"):
        raise HTTPException(status_code=404, detail="Transcript not found")
    path = Path(row["raw_transcript_path"])
    return FileResponse(path, media_type="text/plain", filename=f"{Path(row['file_name']).stem}_raw.txt")


@router.get("/v1/jobs/{job_id}/files/{file_id}/download-diarized")
def download_diarized(job_id: str, file_id: str):
    row = local_store.get_file(job_id, file_id)
    if not row or not row.get("transcript_path"):
        raise HTTPException(status_code=404, detail="Transcript not found")
    path = Path(row["transcript_path"])
    return FileResponse(path, media_type="text/plain", filename=f"{Path(row['file_name']).stem}_diarized.txt")


@router.get("/v1/jobId/{job_id}/fileId/{file_id}/audioChunks")
def audio_chunks(job_id: str, file_id: str):
    try:
        return local_store.get_chunks(job_id, file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/v1/jobId/{job_id}/fileId/{file_id}/streamAudio")
def stream_audio(job_id: str, file_id: str):
    row = local_store.get_file(job_id, file_id)
    if not row or not row.get("storage_path"):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(Path(row["storage_path"]), media_type=row.get("mime_type") or "application/octet-stream")


@router.get("/v1/jobId/{job_id}/fileId/{file_id}/signedUrl")
def signed_url(job_id: str, file_id: str):
    url = local_store.get_signed_url_for_file(job_id, file_id)
    if not url:
        raise HTTPException(status_code=404, detail="Signed URL generation failed or Supabase storage unavailable")
    return {"signedUrl": url}


@router.post("/v1/jobId/{job_id}/fileId/{file_id}/delete")
def delete_file(job_id: str, file_id: str):
    try:
        local_store.delete_file(job_id, file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "message": "Audio file deleted successfully"}


@router.post("/v1/jobId/{job_id}/fileId/{file_id}/retry")
def retry_file(job_id: str, file_id: str, background_tasks: BackgroundTasks):
    if not local_store.get_file(job_id, file_id):
        raise HTTPException(status_code=404, detail="File not found")
    local_store.update_file_progress(job_id, file_id, "processing", "queued", 10, 1)
    dispatch_transcription_task(job_id, file_id, background_tasks)
    return {"success": True, "message": "Retry initiated"}


@router.post("/v1/jobId/{job_id}/fileId/{file_id}/stop")
def stop_file(job_id: str, file_id: str):
    if not local_store.get_file(job_id, file_id):
        raise HTTPException(status_code=404, detail="File not found")
    local_store.update_file_progress(job_id, file_id, "stopped", "stopped", 0, 0)
    return {"success": True, "message": "Transcription stopped"}


@router.post("/v1/chat")
def chat(payload: dict[str, Any], request: Request):
    client_ip = get_client_ip(request)
    allowed, retry_after = chat_rate_limiter.check_rate_limit(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "text": f"⏳ **Rate Limit Exceeded**: You can send a maximum of 2 questions per minute. Please wait {retry_after}s before asking again.",
                "is_rate_limited": True,
                "retry_after": retry_after
            },
            headers={"Retry-After": str(retry_after)}
        )

    question = str(payload.get("userQuestion") or "").strip()
    files = payload.get("files") or []
    if not question:
        return {"text": "Ask a question about one of the selected transcripts."}
    
    file_ids = [f["fileId"] for f in files if isinstance(f, dict) and f.get("fileId")]
    file_items = local_store.get_transcripts_for_files(files)
    if not file_items:
        return {"text": "I could not find transcript text for the selected file(s) yet."}

    # Distinguish general summary/comparison requests or multi-file chats from specific single-file questions
    is_general_summary = (
        len(file_items) > 1 or any(
            w in question.lower()
            for w in [
                "summarize", "summary", "key points", "overview", "general", "brief",
                "call notes", "meeting notes", "key issues", "next steps", "action items", "who are",
                "compare", "comparison", "difference", "differences", "versus", "vs", "both", "across"
            ]
        )
    )

    if is_general_summary:
        if len(file_items) > 1:
            per_file_budget = max(2500, 12000 // len(file_items))
            context_blocks = []
            for item in file_items:
                f_name = item["file_name"]
                f_text = item["text"]
                if len(f_text) > per_file_budget:
                    half = per_file_budget // 2
                    f_text = f_text[:half] + "\n... [middle transcript truncated] ...\n" + f_text[-half:]
                context_blocks.append(f"=== AUDIO FILE TRANSCRIPT: {f_name} ===\n{f_text}\n=== END OF TRANSCRIPT: {f_name} ===")
            context_str = "\n\n".join(context_blocks)
        else:
            full_text = file_items[0]["text"] if file_items else ""
            if len(full_text) > 12000:
                context_str = full_text[:4000] + "\n\n... [middle transcript truncated] ...\n\n" + full_text[-4000:]
            else:
                context_str = full_text
    else:
        # Two-Stage Retrieval: BGE-small Dense + Lexical Candidate Pool (20) -> BGE-reranker-base (Top 10)
        matched_chunks = local_store.search_transcript_chunks(question, file_ids=file_ids, match_count=10)
        if matched_chunks:
            context_lines = []
            for item in matched_chunks:
                start = item.get("start_time", 0)
                end = item.get("end_time", 0)
                ts = f"[{int(start // 60):02d}:{int(start % 60):02d} - {int(end // 60):02d}:{int(end % 60):02d}]"
                spk = item.get("speaker")
                spk_suffix = f" ({spk})" if spk else ""
                context_lines.append(f"{ts}{spk_suffix}:\n{item.get('text')}")
            context_str = "\n\n".join(context_lines)
        else:
            context_str = local_store.transcript_text_for_files(files)[:8000]

    # 2. Call Groq Llama 3.1 8B with Grounded System Prompt
    from app.config.config import settings
    if settings.groq_api_key:
        try:
            import ssl
            from urllib import request

            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ClarityAI/1.0",
            }

            if len(file_items) > 1:
                system_prompt = (
                    "You are an expert multilingual AI assistant analyzing multiple audio transcripts for a user.\n"
                    "CROSS-LINGUAL & MULTILINGUAL RULES:\n"
                    "1. Respond in the exact language that the user is querying in (e.g. Spanish, French, Hindi, German, Japanese, English, etc.).\n"
                    "2. Accurately analyze, compare, and synthesize facts from transcripts in any source language.\n"
                    "3. When answering prompts or comparing multiple files, structure your answer with separate, clear markdown sections for EACH file (e.g. '### 📄 [FileName 1]' and '### 📄 [FileName 2]').\n"
                    "4. Provide a distinct summary, topic breakdown, or speaker overview for each file individually, followed by a '### 💡 Key Cross-Transcript Takeaways & Comparisons' section.\n"
                    "5. Retain accurate timestamp citations [mm:ss] and speaker labels (e.g. Speaker 1, Speaker 2).\n"
                    "6. FORMATTING RULE: Do NOT use raw HTML tags like <br> inside markdown tables or lists."
                )
            elif is_general_summary:
                system_prompt = (
                    "You are an expert multilingual AI assistant helping a user analyze audio transcripts.\n"
                    "CROSS-LINGUAL & MULTILINGUAL RULES:\n"
                    "1. Respond in the exact language that the user is querying in (e.g. Spanish, French, Hindi, German, Japanese, English, etc.).\n"
                    "2. Provide a clear, high-quality, comprehensive summary, meeting notes, key issues, or next steps based on the provided diarized transcript context.\n"
                    "3. Reference speakers accurately (e.g. Speaker 1, Speaker 2) and structure the answer logically with markdown headings and bullet points.\n"
                    "4. FORMATTING RULE: Do NOT use raw HTML tags like <br> inside tables or lists."
                )
            else:
                system_prompt = (
                    "You are an expert multilingual AI assistant answering questions strictly grounded in the provided audio transcript context.\n"
                    "CROSS-LINGUAL & MULTILINGUAL RULES:\n"
                    "1. Respond in the exact language that the user is querying in (e.g. Spanish, French, Hindi, German, Japanese, English, etc.).\n"
                    "2. Use the supplied transcript context as your evidence, accurately extracting facts across any language.\n"
                    "3. If the answer is supported by the context, answer directly, clearly, and accurately.\n"
                    "4. Reference relevant timestamps [mm:ss] or speakers when helpful.\n"
                    "5. If the retrieved context does not contain enough evidence to answer, state clearly that the available transcript context does not provide sufficient information.\n"
                    "6. Do not invent facts."
                )

            user_message = (
                f"CONTEXT:\n"
                f"---\n{context_str}\n---\n\n"
                f"USER PROMPT / QUESTION: {question}"
            )

            payload_data = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.2,
            }

            # Determine primary model based on language:
            # If user selected English (en) -> use openai/gpt-oss-20b
            # Otherwise (auto-detect 'auto', Kannada, Hindi, Spanish, etc.) -> use qwen/qwen3.8-27b
            selected_language = payload.get("language")
            if not selected_language and files:
                for f in files:
                    if isinstance(f, dict) and f.get("jobId"):
                        job_row = local_store.get_job(f["jobId"])
                        if job_row and job_row.get("options_json"):
                            try:
                                opts = json.loads(job_row["options_json"]) if isinstance(job_row["options_json"], str) else job_row["options_json"]
                                selected_language = opts.get("language")
                                if selected_language:
                                    break
                            except Exception:
                                pass

            is_english = False
            if selected_language:
                lang_clean = str(selected_language).strip().lower()
                if lang_clean in {"en", "en-us", "en-gb", "english"}:
                    is_english = True

            if is_english:
                models_to_try = [
                    "openai/gpt-oss-20b",
                    "openai/gpt-oss-120b",
                    "qwen/qwen3.8-27b",
                    "qwen-2.5-32b-instruct",
                    "groq/compound-mini"
                ]
            else:
                # Primary is qwen/qwen3.8-27b; if rate-limited (429), automatically fails over to openai/gpt-oss-20b
                models_to_try = [
                    "qwen/qwen3.8-27b",
                    "openai/gpt-oss-20b",
                    "openai/gpt-oss-120b",
                    "qwen-2.5-32b-instruct",
                    "qwen/qwen-2.5-72b-instruct",
                    "groq/compound-mini"
                ]

            for model_name in models_to_try:
                payload_data["model"] = model_name
                body = json.dumps(payload_data).encode("utf-8")
                req = request.Request(url, data=body, headers=headers, method="POST")

                for attempt in range(1, 4):
                    try:
                        with request.urlopen(req, context=ssl.create_default_context(), timeout=30) as response:
                            res_data = json.loads(response.read().decode("utf-8"))
                            ans_text = res_data["choices"][0]["message"]["content"]
                            import re
                            ans_text = re.sub(r'<think>.*?</think>', '', ans_text, flags=re.DOTALL).strip()
                            return JSONResponse({"text": ans_text})
                    except Exception as groq_exc:
                        from urllib.error import HTTPError
                        if isinstance(groq_exc, HTTPError) and groq_exc.code == 429:
                            is_rate_limited = True
                            print(f"Groq {model_name} 429 rate limit (attempt {attempt}/3). Trying next model/retry...")
                            import time
                            time.sleep(2 * attempt)
                            continue
                        print(f"Groq chat error on {model_name}: {groq_exc}")
                        break

            if is_rate_limited:
                return JSONResponse({
                    "text": "⚠️ **Groq API Rate Limit Reached**\n\nThe Groq AI service is receiving high traffic right now. Please wait 5-10 seconds and try your request again.",
                    "is_rate_limited": True
                })
        except Exception as exc:
            print(f"Chat execution exception: {exc}")

    return JSONResponse({
        "text": "⚠️ Could not generate an AI response at this moment. Please try again shortly.",
        "is_rate_limited": is_rate_limited
    })
