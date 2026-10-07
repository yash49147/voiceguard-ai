from dataclasses import dataclass


@dataclass(frozen=True)
class TrustScoreResult:
    trust_score: float
    alert_level: str
    is_high_risk: bool


class TrustScoreService:
    """
    Converts AI probability into a user-facing trust score,
    alert level, and high-risk decision.

    AI probability:
        0.0   -> human
        100.0 -> synthetic/AI
    """

    @staticmethod
    def calculate(ai_probability: float) -> TrustScoreResult:
        if not 0.0 <= ai_probability <= 100.0:
            raise ValueError("ai_probability must be between 0 and 100")

        trust_score = round(100.0 - ai_probability, 2)

        if ai_probability < 20.0:
            alert_level = "SAFE"
        elif ai_probability < 50.0:
            alert_level = "LOW"
        elif ai_probability < 75.0:
            alert_level = "MEDIUM"
        else:
            alert_level = "HIGH"

        is_high_risk = alert_level == "HIGH"

        return TrustScoreResult(
            trust_score=trust_score,
            alert_level=alert_level,
            is_high_risk=is_high_risk,
        )