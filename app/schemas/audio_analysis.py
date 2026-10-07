from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AudioAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_id: int

    ai_probability: float
    human_probability: float
    synthetic_probability: float

    label: str
    feature_count: int

    trust_score: float
    alert_level: str

    is_high_risk: bool
    should_notify: bool
    created_at: datetime