import os
from pathlib import Path

try:
    from pydantic_settings import BaseSettings
except ModuleNotFoundError:
    from pydantic.v1 import BaseSettings


class Settings(BaseSettings):
    app_name: str = "CLARITY API"
    debug: bool = True
    database_url: str = ""
    supabase_url: str = ""
    supabase_key: str = ""

    # MongoDB Configuration
    mongo_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "clarity-ai-db"
    mongodb_job_collection: str = "clarityJobStatus"

    # AWS Configuration
    is_local: bool = True
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    aws_region: str = "us-east-1"
    aws_endpoint_url: str = ""

    # File Upload Configuration
    allowed_mime_types: dict = {
        'audio/wav': 'wav',
        'audio/x-wav': 'wav',
        'audio/mpeg': 'mp3',
        'audio/mp3': 'mp3',
        'video/mp4': 'mp4',
        'audio/mp4': 'mp4'
    }
    max_file_size_mb: int = 25

    # S3 Configuration
    s3_source_bucket: str = "clarity-audio-bucket"
    s3_output_bucket: str = "clarity-audio-bucket"
    s3_upload_folder: str = "audio"
    s3_transcription_folder: str = "transcript"

    # SQS Configuration
    sqs_queue_name: str = "clarity_sqs_queue"
    sqs_queue_url: str = ""

    # Transcription & AI Configuration
    transcription_provider: str = "groq"
    groq_api_key: str = ""
    groq_transcribe_url: str = "https://api.groq.com/openai/v1/audio/transcriptions"
    groq_chat_url: str = "https://api.groq.com/openai/v1/chat/completions"
    groq_whisper_model: str = "whisper-large-v3"
    huggingface_token: str = ""

    # Protegrity Configuration
    protegrity_url: str = ""
    protegrity_cert_path: str = ""
    protegrity_key_path: str = ""
    protegrity_user: str = ""

    # Okta Configuration
    okta_issuer: str = ""
    okta_client_id: str = ""
    okta_client_secret: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
