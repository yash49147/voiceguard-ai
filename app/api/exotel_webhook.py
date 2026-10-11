import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Call, ExotelCallMapping


router = APIRouter(
    prefix="/api/webhooks/exotel",
    tags=["Exotel Webhooks"],
)

ACTIVE_STATUSES = {
    "queued",
    "ringing",
    "answered",
    "active",
    "in-progress",
    "in_progress",
}

TERMINAL_STATUSES = {
    "completed",
    "failed",
    "busy",
    "no-answer",
    "no_answer",
    "canceled",
    "cancelled",
    "rejected",
    "timeout",
    "not-connected",
    "not_connected",
}


async def _read_payload(request: Request) -> dict:
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON callback payload",
            ) from exc

        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Callback payload must be a JSON object",
            )

        return payload

    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported or invalid callback payload",
        ) from exc

    return dict(form)


def _extract_call_id(payload: dict) -> str | None:
    nested = payload.get("call_details")
    if not isinstance(nested, dict):
        nested = {}

    value = (
        payload.get("CallSid")
        or payload.get("call_sid")
        or payload.get("sid")
        or nested.get("sid")
        or nested.get("CallSid")
    )

    if value is None:
        return None

    value = str(value).strip()
    return value or None


def _extract_provider_status(payload: dict) -> str | None:
    nested = payload.get("call_details")
    if not isinstance(nested, dict):
        nested = {}

    value = (
        payload.get("CallStatus")
        or payload.get("Status")
        or payload.get("status")
        or nested.get("status")
        or nested.get("Status")
    )

    if value is None:
        return None

    value = str(value).strip().lower()
    return value or None


@router.post("/status")
async def exotel_status_callback(
    request: Request,
    token: str | None = None,
    db: Session = Depends(get_db),
):
    if not settings.exotel_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Exotel integration is disabled",
        )

    configured_token = settings.exotel_webhook_token
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Exotel webhook authentication is not configured",
        )

    if token is None or not hmac.compare_digest(
        token,
        configured_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )

    payload = await _read_payload(request)
    provider_call_id = _extract_call_id(payload)
    provider_status = _extract_provider_status(payload)

    if not provider_call_id or not provider_status:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Callback requires a call ID and status",
        )

    if (
        provider_status not in ACTIVE_STATUSES
        and provider_status not in TERMINAL_STATUSES
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported Exotel call status",
        )

    mapping = db.scalar(
        select(ExotelCallMapping).where(
            ExotelCallMapping.provider == "exotel",
            ExotelCallMapping.provider_call_id == provider_call_id,
        )
    )

    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown Exotel call ID",
        )

    call = db.scalar(
        select(Call).where(Call.id == mapping.call_id)
    )

    if call is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mapped VoiceGuard call not found",
        )

    # Never reopen a call that has already reached a terminal state.
    if call.status not in {"initiating", "active"}:
        return {
            "accepted": True,
            "status": call.status,
            "duplicate_or_stale": True,
        }

    if provider_status in TERMINAL_STATUSES:
        call.status = provider_status
        call.ended_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(call)

    elif call.status == "initiating":
        # The provider confirms that the call has entered an active state.
        call.status = "active"
        db.commit()
        db.refresh(call)

    return {
        "accepted": True,
        "status": call.status,
        "duplicate_or_stale": False,
    }
