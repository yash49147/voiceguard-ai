import pytest

from app.services.trust_score import TrustScoreService


def test_zero_ai_probability_is_fully_trusted():
    result = TrustScoreService.calculate(0)

    assert result.trust_score == 100.0
    assert result.alert_level == "SAFE"
    assert result.is_high_risk is False


def test_safe_boundary():
    result = TrustScoreService.calculate(19.99)

    assert result.trust_score == 80.01
    assert result.alert_level == "SAFE"


def test_low_boundary():
    result = TrustScoreService.calculate(20)

    assert result.trust_score == 80.0
    assert result.alert_level == "LOW"


def test_medium_boundary():
    result = TrustScoreService.calculate(50)

    assert result.trust_score == 50.0
    assert result.alert_level == "MEDIUM"


def test_high_boundary():
    result = TrustScoreService.calculate(75)

    assert result.trust_score == 25.0
    assert result.alert_level == "HIGH"


def test_hundred_ai_probability_is_zero_trust():
    result = TrustScoreService.calculate(100)

    assert result.trust_score == 0.0
    assert result.alert_level == "HIGH"
    assert result.is_high_risk is True


@pytest.mark.parametrize("value", [-0.01, 100.01, -10, 150])
def test_invalid_ai_probability_is_rejected(value):
    with pytest.raises(ValueError, match="between 0 and 100"):
        TrustScoreService.calculate(value)