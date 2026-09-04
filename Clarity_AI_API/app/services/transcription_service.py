import json
import mimetypes
import os
import re
import ssl
import subprocess
import sys
import time
import uuid
import wave
from pathlib import Path
from typing import Any, Callable, Optional
from urllib import request
from urllib.error import HTTPError, URLError

import imageio_ffmpeg

from app.config.config import settings


class TranscriptionConfigError(RuntimeError):
    pass


class TranscriptionProviderError(RuntimeError):
    pass


def _multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----ClarityAI{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode(),
                b"\r\n",
            ]
        )

    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode(),
            f"Content-Type: {mime_type}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "ClarityAI/1.0",
            "Content-Type": "application/json",
            **(headers or {}),
        },
        method="POST",
    )
    try:
        with request.urlopen(req, context=ssl.create_default_context(), timeout=30) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise TranscriptionProviderError(f"Groq API returned HTTP {exc.code}: {detail[:150]}") from exc
    except URLError as exc:
        raise TranscriptionProviderError(f"Network connection failed to Groq: {exc.reason}") from exc


def _post_multipart(url: str, headers: dict[str, str], fields: dict[str, str], file_path: Path, max_retries: int = 4) -> dict[str, Any]:
    body, content_type = _multipart_body(fields, "file", file_path)
    for attempt in range(1, max_retries + 1):
        req = request.Request(
            url,
            data=body,
            headers={
                "User-Agent": "ClarityAI/1.0",
                **headers,
                "Content-Type": content_type,
                "Content-Length": str(len(body)),
            },
            method="POST",
        )
        try:
            with request.urlopen(req, context=ssl.create_default_context(), timeout=900) as response:
                return json.loads(response.read().decode())
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            if exc.code == 429 and attempt < max_retries:
                wait_time = 6.0 * attempt
                print(f"Groq API 429 Rate Limit hit. Backing off for {wait_time}s (attempt {attempt}/{max_retries})...")
                time.sleep(wait_time)
                continue
            raise TranscriptionProviderError(f"Groq API returned HTTP {exc.code}: {detail[:150]}") from exc
        except URLError as exc:
            if attempt < max_retries:
                time.sleep(2.0)
                continue
            raise TranscriptionProviderError(f"Network connection failed to Groq: {exc.reason}") from exc


def _normalise_segments(result: dict[str, Any], time_offset: float = 0.0, start_chunk_num: int = 1) -> list[dict[str, Any]]:
    source_segments = result.get("segments") or result.get("diarized_segments") or result.get("chunks") or []
    segments: list[dict[str, Any]] = []

    for index, segment in enumerate(source_segments, start=start_chunk_num):
        text = str(segment.get("text") or segment.get("transcript") or "").strip()
        if not text:
            continue

        speaker = (
            segment.get("speaker")
            or segment.get("speaker_label")
            or segment.get("speakerLabel")
            or segment.get("role")
            or "Speaker 1"
        )
        start = float(segment.get("start") or segment.get("start_time") or segment.get("startTime") or 0) + time_offset
        end = float(segment.get("end") or segment.get("end_time") or segment.get("endTime") or start) + time_offset
        if end <= start:
            end = start + max(2.0, len(text.split()) * 0.45)

        segments.append(
            {
                "chunk_number": index,
                "speaker": str(speaker),
                "text": text,
                "start_time": start,
                "end_time": end,
            }
        )

    if segments:
        return segments

    text = str(result.get("text") or result.get("transcript") or "").strip()
    if not text:
        return []

    return [
        {
            "chunk_number": start_chunk_num,
            "speaker": "Speaker 1",
            "text": text,
            "start_time": time_offset,
            "end_time": time_offset + max(2.0, len(text.split()) * 0.45),
        }
    ]


def _diarize_segments_with_pyannote(file_path: Path, segments: list[dict[str, Any]], timeout_seconds: int = 15) -> list[dict[str, Any]]:
    if not settings.huggingface_token:
        print("HuggingFace token not configured. Skipping Pyannote diarization.")
        return segments

    python_exe = sys.executable
    script_path = str(Path(__file__).parent / "run_pyannote.py")

    print(f"Launching Pyannote OS subprocess on {file_path.name} with {timeout_seconds}s timeout...")
    proc = subprocess.Popen(
        [python_exe, script_path, str(file_path), settings.huggingface_token],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        print(f"Pyannote OS process timed out after {timeout_seconds}s on CPU. Killing subprocess...")
        proc.kill()
        proc.communicate()
        raise RuntimeError(f"Pyannote timed out after {timeout_seconds}s")

    if "PYANNOTE_JSON_START" not in stdout:
        raise RuntimeError(f"Pyannote output notice: {stderr[:150]}")

    json_str = stdout.split("PYANNOTE_JSON_START")[1].split("PYANNOTE_JSON_END")[0].strip()
    data = json.loads(json_str)

    if "error" in data:
        raise RuntimeError(data["error"])

    raw_turns = data.get("turns", [])
    if not raw_turns:
        print("Pyannote returned no turns, keeping existing segments.")
        return segments

    print(f"Pyannote returned {len(raw_turns)} acoustic speaker turns. Aligning timestamps...")
    for seg in segments:
        seg_start = seg["start_time"]
        seg_end = seg["end_time"]
        best_overlap = 0.0
        best_speaker = seg["speaker"]

        for turn in raw_turns:
            t_start = turn["start"]
            t_end = turn["end"]
            overlap = max(0.0, min(seg_end, t_end) - max(seg_start, t_start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = turn["speaker"]

        seg["speaker"] = best_speaker

    return segments


def _linguistic_diarize_fallback(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_speaker = "Speaker 1"
    speakers = ["Speaker 1", "Speaker 2"]

    for i, seg in enumerate(segments):
        text = seg["text"].strip()
        gap = 0.0
        if i > 0:
            gap = seg["start_time"] - segments[i - 1]["end_time"]

        is_question = (
            i > 0
            and (
                segments[i - 1]["text"].rstrip().endswith("?")
                or segments[i - 1]["text"].rstrip().endswith(";")
                or "?" in segments[i - 1]["text"]
            )
        )
        is_long_turn = len(text.split()) > 25
        long_silence = gap > 2.0

        if (is_question or long_silence) and not is_long_turn:
            current_speaker = speakers[1] if current_speaker == speakers[0] else speakers[0]

        seg["speaker"] = current_speaker

    return segments


def _diarize_segments_with_llm(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not settings.groq_api_key or not segments:
        return _linguistic_diarize_fallback(segments)

    if len(segments) <= 1:
        return segments

    lines = []
    for s in segments:
        lines.append(f"[{s['chunk_number']}] ({s['start_time']:.1f}s - {s['end_time']:.1f}s): {s['text']}")
    transcript_block = "\n".join(lines)

    prompt = (
        "You are an expert audio diarization analysis system.\n"
        "Analyze the following transcript with timestamps and assign distinct speakers ('Speaker 1', 'Speaker 2', etc.) "
        "to each segment based on conversational context, dialogue structure, Q&A turns, and timing gaps.\n\n"
        "IMPORTANT RULES:\n"
        "1. Return ONLY valid JSON in this exact structure: {\"speaker_turns\": [{\"chunk_number\": 1, \"speaker\": \"Speaker 1\"}, ...]}\n"
        "2. If multiple speakers are engaged in discussion, alternate appropriately.\n"
        "3. Output no explanation or markdown formatting, just the raw JSON object.\n\n"
        f"TRANSCRIPT TO DIARIZE:\n{transcript_block}"
    )

    models_to_try = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ]

    speaker_map: dict[int, str] = {}
    for model_name in models_to_try:
        try:
            print(f"Calling Groq LLM ({model_name}) for speaker diarization...")
            res = _post_json(
                settings.groq_chat_url,
                {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
                {"Authorization": f"Bearer {settings.groq_api_key}"},
            )
            content = res.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            data = json.loads(content)
            turns = data.get("speaker_turns", [])
            for turn in turns:
                c_num = turn.get("chunk_number")
                spk = turn.get("speaker")
                if c_num is not None and spk:
                    speaker_map[int(c_num)] = str(spk)

            if speaker_map and len(set(speaker_map.values())) > 1:
                print(f"Groq LLM diarization succeeded with {model_name}: {len(set(speaker_map.values()))} speakers.")
                break
        except Exception as e:
            print(f"Groq LLM diarization notice ({model_name}): {e}")
            time.sleep(0.5)

    if speaker_map and len(set(speaker_map.values())) > 1:
        current_spk = "Speaker 1"
        for seg in segments:
            num = seg["chunk_number"]
            if num in speaker_map:
                current_spk = speaker_map[num]
            seg["speaker"] = current_spk
        return segments

    return _linguistic_diarize_fallback(segments)


def _get_smart_silence_splits(ffmpeg_exe: str, wav_path: Path, total_dur: float, target_sec: int = 60) -> list[float]:
    """
    Finds natural breath/silence pauses in the audio to slice chunks at natural pauses
    rather than cutting words in half mid-sentence.
    """
    try:
        res = subprocess.run(
            [ffmpeg_exe, "-i", str(wav_path), "-af", "silencedetect=noise=-30dB:d=0.25", "-f", "null", "-"],
            capture_output=True,
            text=True,
        )
        silences: list[float] = []
        for line in res.stderr.splitlines():
            if "silence_end" in line:
                m = re.search(r"silence_end:\s*([0-9.]+)", line)
                if m:
                    silences.append(float(m.group(1)))

        splits: list[float] = []
        current_time = 0.0
        min_win = max(35, int(target_sec * 0.6))
        max_win = int(target_sec * 1.35)

        while current_time + max_win < total_dur:
            target_time = current_time + target_sec
            candidates = [s for s in silences if current_time + min_win <= s <= current_time + max_win]
            if candidates:
                best_split = min(candidates, key=lambda s: abs(s - target_time))
            else:
                best_split = target_time

            splits.append(best_split)
            current_time = best_split

        return splits
    except Exception as e:
        print(f"Silencedetect notice ({e}), using regular intervals...")
        splits = []
        c = target_sec
        while c < total_dur:
            splits.append(float(c))
            c += target_sec
        return splits


def _transcribe_chunked(file_path: Path, language: Optional[str] = None) -> list[dict[str, Any]]:
    """
    Extracts 16kHz mono audio and slices at natural silence pauses (target ~60s chunks).
    Completely eliminates Whisper attention drift, boundary word clipping, and hallucinated repetition loops.
    """
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    temp_full_wav = file_path.parent / f"extracted_{uuid.uuid4().hex[:8]}.wav"

    try:
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", str(file_path), "-vn", "-ar", "16000", "-ac", "1", str(temp_full_wav)],
            check=True,
            capture_output=True,
        )

        with wave.open(str(temp_full_wav), "rb") as wf:
            total_duration = wf.getnframes() / float(wf.getframerate())

        print(f"Audio extracted successfully: {total_duration:.2f}s ({total_duration/60:.2f} mins).")

        fields_base: dict[str, Any] = {
            "model": settings.groq_whisper_model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }
        if language and str(language).strip().lower() != "auto":
            fields_base["language"] = str(language).strip().lower()
            print(f"Transcribing audio with explicit language: '{fields_base['language']}'")

        # If audio is very short (< 75s), transcribe in single call
        if total_duration <= 75.0:
            result = _post_multipart(
                settings.groq_transcribe_url,
                {"Authorization": f"Bearer {settings.groq_api_key}"},
                fields_base,
                temp_full_wav,
            )
            return _normalise_segments(result)

        # For longer files, find natural silence split points (~55-65s chunks)
        splits = _get_smart_silence_splits(ffmpeg_exe, temp_full_wav, total_duration, target_sec=60)
        split_boundaries = splits + [total_duration]
        print(f"Divided into {len(split_boundaries)} silence-aware chunks: {[round(s, 1) for s in split_boundaries]}")

        all_segments: list[dict[str, Any]] = []
        current_start = 0.0

        for chunk_idx, chunk_end in enumerate(split_boundaries, 1):
            chunk_wav = file_path.parent / f"chunk_{chunk_idx}_{uuid.uuid4().hex[:6]}.wav"

            subprocess.run(
                [
                    ffmpeg_exe,
                    "-y",
                    "-ss",
                    str(current_start),
                    "-to",
                    str(chunk_end),
                    "-i",
                    str(temp_full_wav),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(chunk_wav),
                ],
                check=True,
                capture_output=True,
            )

            try:
                result = _post_multipart(
                    settings.groq_transcribe_url,
                    {"Authorization": f"Bearer {settings.groq_api_key}"},
                    fields_base,
                    chunk_wav,
                )
                chunk_segs = _normalise_segments(
                    result,
                    time_offset=current_start,
                    start_chunk_num=len(all_segments) + 1,
                )
                all_segments.extend(chunk_segs)
            finally:
                chunk_wav.unlink(missing_ok=True)

            current_start = chunk_end

        return all_segments

    finally:
        temp_full_wav.unlink(missing_ok=True)


def transcribe_audio_file(file_path: str, progress_cb: Optional[Callable[[str, float, int], None]] = None, language: Optional[str] = None) -> list[dict[str, Any]]:
    path = Path(file_path)
    if not settings.groq_api_key:
        raise TranscriptionConfigError("GROQ_API_KEY is not configured.")

    if progress_cb:
        progress_cb("extracting_audio", 25.0, 1)

    if progress_cb:
        progress_cb("transcribing", 45.0, 2)

    try:
        segments = _transcribe_chunked(path, language=language)
    except Exception as e:
        print(f"Chunked extraction encountered error ({e}), falling back to direct upload...")
        fields: dict[str, Any] = {
            "model": settings.groq_whisper_model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }
        if language and str(language).strip().lower() != "auto":
            fields["language"] = str(language).strip().lower()

        result = _post_multipart(
            settings.groq_transcribe_url,
            {"Authorization": f"Bearer {settings.groq_api_key}"},
            fields,
            path,
        )
        segments = _normalise_segments(result)

    if progress_cb:
        progress_cb("diarizing", 65.0, 3)

    pyannote_succeeded = False
    if settings.huggingface_token:
        try:
            segments = _diarize_segments_with_pyannote(path, segments, timeout_seconds=15)
            unique_speakers = set(seg["speaker"] for seg in segments)
            if len(unique_speakers) > 1:
                pyannote_succeeded = True
                print(f"Pyannote diarization succeeded: {len(unique_speakers)} speakers found.")
        except Exception as e:
            print(f"Pyannote diarization notice ({e}), falling back to Groq LLM Diarization...")

    if not pyannote_succeeded:
        print("Executing fast Groq LLM Diarization fallback...")
        segments = _diarize_segments_with_llm(segments)

    if progress_cb:
        progress_cb("generating_chunks", 85.0, 4)

    return segments
