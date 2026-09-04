# Clarity AI API Backend

FastAPI audio processing backend for transcribing, diarizing (speaker identification), and storing audio/video interactions using Groq Whisper, Pyannote Audio 3.1, Supabase PostgreSQL, and Supabase Storage.

## 🎙️ Speaker Diarization & Performance Tradeoffs

Clarity AI features a **dual-engine speaker diarization pipeline**:

### 1. Pyannote Audio 3.1 (Acoustic Waveform Diarization)
* **How it works**: Uses `pyannote/speaker-diarization-3.1` with PyTorch to analyze acoustic voice signatures.
* **Performance**:
  * **GPU (CUDA)**: ~10x–20x faster than real-time (a 10-minute audio file completes in ~30 seconds).
  * **CPU**: ~1:1 to 2:1 audio-length ratio on CPU. To maximize CPU speed, Clarity AI automatically converts audio to a **16kHz mono WAV** before running Pyannote.
* **Requirement**: Requires `HUGGINGFACE_TOKEN` set in your environment variables.

### 2. Groq LLM Diarization Fallback (`llama-3.1-8b-instant`)
* **How it works**: If Pyannote is unconfigured (`HUGGINGFACE_TOKEN=""`), times out on CPU (exceeds 120s limit), or encounters DLL/torch errors, Clarity AI **automatically falls back to Llama 3.1 8B on Groq**.
* **Performance**: Extremely fast (~2–3 seconds total runtime on Groq).
* **Configuration**: Set `HUGGINGFACE_TOKEN=""` in `.env` if you want to bypass Pyannote and use instant Groq LLM speaker diarization!

---

## ⚡ Background Worker (Celery + Redis)

* Long-running audio transcriptions execute in background workers to avoid HTTP 504 gateway timeouts.
* Set `REDIS_URL` in your environment (e.g. Upstash or Railway Redis) to dispatch background tasks via Celery.
* In local development without Redis, Clarity AI automatically falls back to FastAPI's built-in `BackgroundTasks`.

---

## 🗄️ Storage & Retention Policy

* **Supabase Storage**: Private bucket `audio-files` with 1-hour expiring signed download URLs.
* **Database**: PostgreSQL with `pgvector` enabled for RAG transcript embeddings.
* **20-File Retention Policy**: Automatically prunes older completed/failed recordings beyond the 20 most recent, protecting in-flight (`pending`, `processing`, `queued`, `transcribing`) uploads from race conditions.
