
from pydantic import BaseModel, Field, validator

from typing import List, Optional

from datetime import datetime

from enum import Enum




class JobStatusEnum(str, Enum):

    Received = "Received"

    Uploaded = "Uploaded"

    Processing = "Processing"

    Completed = "Completed"

    Failed = "Failed"

   

    @classmethod

    def _missing_(cls, value):

        if isinstance(value, str):

            for member in cls:

                if member.value.lower() == value.lower():

                    return member

        return None

 

class UploadStatusEnum(str, Enum):

    success = "success"

    failed = "failed"

 

class TranscriptionOptions(BaseModel):

    enableTimeStamp: bool = False

 

##### API Related schemas

class CreateJobRequest(BaseModel):

    fileDetails: List[str] = Field(..., max_length=5)

    businessGroup: str

    options: TranscriptionOptions

   

    @validator('fileDetails')

    def validate_file_details(cls, v):

        if len(v) == 0:

            raise ValueError('At least one file is required')

        if len(v) > 5:

            raise ValueError('Maximum 5 files allowed')

        return v

 

class CreateJobResponse(BaseModel):

    jobID: str

    fileID: List[str]

 

class FileProgressStatus(str, Enum):

    extracting_audio = "extracting_audio"

    queued = "queued"

    chunking = "chunking"

    transcribing = "transcribing"

    merging = "merging"

    completed = "completed"

    failed = "failed"

    received = "received"

    uploaded = "uploaded"

    processing = "processing"

   

    @classmethod

    def _missing_(cls, value):

        if isinstance(value, str):

            for member in cls:

                if member.value.lower() == value.lower():

                    return member

        return None

 

class FileProgress(BaseModel):

    stage: str = "queued"

    currentChunk: int

    totalChunks: int

    percentage: float

 

class FileUploadResponse(BaseModel):

    jobID: str

    fileID: str

    FileName: str

    uploadStatus: UploadStatusEnum

 

class FileStatusResponse(BaseModel):

    fileID: str

    fileName: str

    status: str

    progress: FileProgress

    errorDetails: Optional[str] = None

 

class JobStatusResponse(BaseModel):

    jobID: str

    status: JobStatusEnum

    files: List[FileStatusResponse]

 

#### Mongo Related schemas

class UserDetails(BaseModel):

    userName: str

    domainID: str

    emailID: str

    businessGroup: str

 

class TimeDetails(BaseModel):

    receivedAt: datetime

    uploadedAt: Optional[datetime] = None

    startedProcessingAt: Optional[datetime] = None

    processedAt: Optional[datetime] = None

 

class S3Details(BaseModel):

    sourceFileName: str

    transcriptFileName: str

 

class ProgressDetails(BaseModel):

    currentChunk: int

    totalChunks: int

    percentage: float

 

class FileDetails(BaseModel):

    fileID: str

    fileName: str

    status: JobStatusEnum

    sizeBytes: int

    fileType: str

    s3Details: S3Details

    timeDetails: TimeDetails

    progress: ProgressDetails

    errorDetails: Optional[str] = None

    duration: Optional[str] = None

 

class JobDocument(BaseModel):

    jobID: str

    userDetails: UserDetails

    timeDetails: TimeDetails

    status: JobStatusEnum

    files: List[FileDetails]

    options: TranscriptionOptions

 

#### SQS Related schemas

class SQSMessage(BaseModel):

    jobID: str

    fileID: str

    source_bucket: str

    source_key: str

    output_bucket: str

    output_key: str

 

#### AllData endpoint schemas

class AllDataRecord(BaseModel):

    jobID: str

    fileID: str

    fileName: str

    sizeBytes: int

    fileStatus: str

    userName: str

    domainID: Optional[str] = None

    businessGroup: Optional[str] = None

    status: str

    receivedAt: datetime

    sourceFileName: Optional[str] = None

    duration: Optional[str] = None

    startedProcessingAt: Optional[datetime] = None

    processedAt: Optional[datetime] = None

 

class PaginationInfo(BaseModel):

    page: int

    limit: int

    total: int

    totalPages: int

 

class AllDataResponse(BaseModel):

    records: List[AllDataRecord]

    pagination: PaginationInfo

 

#### Chat endpoint schemas

class ConversationMessage(BaseModel):

    user: str

    agent: str

 

class FileReference(BaseModel):

    fileId: str

    jobId: str

 

class ChatRequest(BaseModel):

    conversationHistory: List[ConversationMessage] = []

    userQuestion: str

    files: List[FileReference]

 

class ChatResponse(BaseModel):

    text: Optional[str] = None

    error: Optional[str] = None

    details: Optional[str] = None

 

#### Transcript Segments endpoint schemas

class TranscriptSegment(BaseModel):

    type: str

    text: str

    speaker: str

    start: float

    end: float

    id: str

 

class TranscriptMetadata(BaseModel):

    totalDuration: float

    speakerCount: int

    processingDate: Optional[datetime] = None

 

class TranscriptSegmentsResponse(BaseModel):

    segments: List[TranscriptSegment]

    metadata: TranscriptMetadata

 

#### Audio Metadata endpoint schemas

class AudioMetadataResponse(BaseModel):

    fileId: str

    fileName: str

    duration: float

    fileSize: int

    streamingURL: str

    downloadURL: str

 

#### Simplified AllData endpoint schemas

class SimplifiedDataRecord(BaseModel):

    jobID: str

    fileID: str

    fileName: str

    receivedAt: datetime

 

class SimplifiedDataResponse(BaseModel):

    records: List[SimplifiedDataRecord]

    pagination: PaginationInfo

 

#### Interactions endpoint schema

class InteractionsResponse(BaseModel):

    totalCount: int

    fromDate: Optional[str] = None

    toDate: Optional[str] = None

 

#### Audio Chunks endpoint schemas

class AudioChunkSegment(BaseModel):

    start: float

    end: float

    text: str

    speaker: Optional[str] = None

 

class AudioChunkInfo(BaseModel):

    chunkNumber: int

    totalChunks: int

    startByte: int

    endByte: int

    sizeBytes: int

    startTime: float

    endTime: float

    transcriptSegments: List[AudioChunkSegment]

 

class AudioChunksResponse(BaseModel):

    jobID: str

    fileID: str

    fileName: str

    totalSize: int

    chunks: List[AudioChunkInfo]

 