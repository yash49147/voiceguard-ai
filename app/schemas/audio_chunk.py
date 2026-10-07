from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AudioChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_id: int
    sequence_number: int
    start_offset_ms: int
    end_offset_ms: int
    duration_ms: int
    sample_rate: int
    channels: int
    audio_format: str
    file_size_bytes: int
    created_at: datetime