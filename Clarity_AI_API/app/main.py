import os
import uvicorn
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from app.api import health, jobs
from app.services.local_store import ensure_storage
from app.config.config import settings

app = FastAPI(title="Clarity AI API")

# Global exception handler to guarantee CORS headers on any error
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin") or "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin") or "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )

# Absolute path to sample test files directory
SAMPLE_FILES_DIR = Path(__file__).resolve().parents[1] / "data" / "sample_files"

ALLOWED_SAMPLE_FILES = {
    "2peopleDiscussionMP3.mp3": "audio/mpeg",
    "dune3.mp4": "video/mp4",
}


@app.on_event("startup")
def startup() -> None:
    ensure_storage()

# Enable CORS for frontend applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the specific routers
app.include_router(health.router, tags=["Health"])
app.include_router(jobs.router, tags=["Jobs"])

@app.get("/debug-env")
def debug_env():
    return {
        "has_database_url": bool(settings.database_url or os.getenv("DATABASE_URL")),
        "has_groq_key": bool(settings.groq_api_key or os.getenv("GROQ_API_KEY")),
        "has_supabase_url": bool(settings.supabase_url or os.getenv("SUPABASE_URL")),
        "has_supabase_key": bool(settings.supabase_key or os.getenv("SUPABASE_KEY")),
    }

@app.get("/")
def read_root():
    return {"message": "Welcome to Clarity AI API"}

@app.get("/sample-files")
def list_sample_files():
    """Return list of available sample test files."""
    files = []
    for name, mime in ALLOWED_SAMPLE_FILES.items():
        file_path = SAMPLE_FILES_DIR / name
        if file_path.exists():
            files.append({
                "filename": name,
                "mime_type": mime,
                "size_bytes": file_path.stat().st_size,
                "download_url": f"/sample-files/download/{name}"
            })
    return {"files": files}

@app.get("/sample-files/download/{filename}")
def download_sample_file(filename: str):
    """Stream a sample test file as a browser download."""
    if filename not in ALLOWED_SAMPLE_FILES:
        raise HTTPException(status_code=404, detail=f"Sample file '{filename}' not found.")
    file_path = SAMPLE_FILES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server.")
    mime_type = ALLOWED_SAMPLE_FILES[filename]
    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# Add helper endpoints to handle upload/transcribe targets from the frontend
@app.post("/upload")
@app.post("/api/upload")
@app.post("/transcribe")
@app.post("/api/transcribe")
async def upload_file(file: UploadFile = File(...)):
    # Verify file extension
    filename = file.filename
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    
    if ext not in ["mp3", "mp4", "wav", "m4a", "ogg"]:
        return {
            "status": "error",
            "message": f"Unsupported file extension: {ext}. Please upload mp3, mp4, or wav."
        }

    # Simulate saving or processing the file
    content = await file.read()
    file_size = len(content)

    # Enforce 25 MB file size limit
    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File '{filename}' exceeds the 25 MB size limit ({file_size / 1024 / 1024:.1f} MB). Please upload a file under 25 MB."
        )

    return {
        "status": "success",
        "message": "File uploaded successfully",
        "filename": filename,
        "size_bytes": file_size,
        "job_id": "mock-job-id-12345"
    }

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=5175, reload=True)
