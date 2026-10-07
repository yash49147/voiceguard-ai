from datetime import datetime

from pydantic import BaseModel, ConfigDict
from app.db.models import AlertEvent


class AlertEventResponse(BaseModel):
    id: int
    analysis_id: int
    user_id: int
    alert_level: str
    trust_score: float
    ai_probability: float
    notified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


def test_alert_event_model_defaults():
    alert_event = AlertEvent(
        analysis_id=999,
        user_id=999,
        alert_level="HIGH",
        trust_score=10.0,
        ai_probability=90.0,
        notified=False,
    )

    assert alert_event.alert_level == "HIGH"
    assert alert_event.trust_score == 10.0
    assert alert_event.ai_probability == 90.0
    assert alert_event.notified is False