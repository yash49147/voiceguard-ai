from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertEventResponse(BaseModel):
    id: int
    analysis_id: int
    user_id: int
    alert_level: str
    trust_score: float
    ai_probability: float
    notified: bool
    acknowledged: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)