from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    started_at: datetime
    ended_at: datetime | None
    created_at: datetime