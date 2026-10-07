import pytest

from app.services.alert_service import AlertService


@pytest.mark.parametrize(
    "alert_level",
    ["SAFE", "LOW", "MEDIUM"],
)
def test_non_high_alerts_do_not_notify(alert_level):
    result = AlertService.evaluate(alert_level)

    assert result.alert_level == alert_level
    assert result.is_high_risk is False
    assert result.should_notify is False


def test_high_alert_is_high_risk_and_notifiable():
    result = AlertService.evaluate("HIGH")

    assert result.alert_level == "HIGH"
    assert result.is_high_risk is True
    assert result.should_notify is True


def test_alert_level_is_normalized():
    result = AlertService.evaluate(" high ")

    assert result.alert_level == "HIGH"
    assert result.is_high_risk is True
    assert result.should_notify is True


@pytest.mark.parametrize(
    "alert_level",
    ["", "UNKNOWN", "CRITICAL", "123"],
)
def test_invalid_alert_level_is_rejected(alert_level):
    with pytest.raises(ValueError, match="Invalid alert level"):
        AlertService.evaluate(alert_level)