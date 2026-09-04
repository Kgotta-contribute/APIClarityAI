from app.celery_app import celery_app
from app.services import local_store

@celery_app.task(name="tasks.process_file_task", bind=True, max_retries=3)
def process_file_task(self, job_id: str, file_id: str):
    """
    Asynchronous Celery task worker for processing & transcribing audio files.
    Moves long-running Whisper model execution off the main FastAPI request thread.
    """
    try:
        print(f"Starting Celery background processing for job {job_id}, file {file_id}")
        local_store.process_file(job_id, file_id)
        print(f"Completed Celery background processing for job {job_id}, file {file_id}")
    except Exception as exc:
        print(f"Celery task failed for job {job_id}, file {file_id}: {exc}")
        self.retry(exc=exc, countdown=10)
