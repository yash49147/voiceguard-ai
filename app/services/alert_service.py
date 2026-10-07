from dataclasses import dataclass


@dataclass(frozen=True)
class AlertDecision:
    alert_level: str
    is_high_risk: bool
    should_notify: bool


class AlertService:
    """
    Applies alert policy to an already-calculated alert level.

    This service intentionally does not calculate AI probability
    or trust score. Those responsibilities remain in TrustScoreService.
    """

    HIGH_RISK_LEVEL = "HIGH"

    @classmethod
    def evaluate(cls, alert_level: str) -> AlertDecision:
        normalized_level = alert_level.strip().upper()

        valid_levels = {
            "SAFE",
            "LOW",
            "MEDIUM",
            "HIGH",
        }

        if normalized_level not in valid_levels:
            raise ValueError(
                f"Invalid alert level: {alert_level}"
            )

        is_high_risk = normalized_level == cls.HIGH_RISK_LEVEL

        return AlertDecision(
            alert_level=normalized_level,
            is_high_risk=is_high_risk,
            should_notify=is_high_risk,
        )