
from datetime import datetime, timezone
import hmac
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.db.models import Call, ExotelCallMapping, User


router = APIRouter(
    prefix="/api/exotel",
    tags=["Exotel Calls"],
)


class OutboundCallRequest(BaseModel):
    destination_number: str = Field(
        pattern=r"^\+[1-9]\d{7,14}$",
        description="Destination phone number in E.164 format",
    )


def _add_query_params(
    url: str,
    params: dict[str, str],
    required_scheme: str,
) -> str:
    parts = urlsplit(url.strip())

    if (
        parts.scheme != required_scheme
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
    ):
        raise ValueError("Invalid configured callback or stream URL")

    query = [
        (key, value)
        for key, value in parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
        if key not in params
    ]
    query.extend(params.items())

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            "",
        )
    )


def _mark_call_failed(db: Session, call: Call) -> None:
    call.status = "failed"
    call.ended_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/calls", status_code=status.HTTP_201_CREATED)
async def initiate_exotel_call(
    payload: OutboundCallRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    required_settings = (
        settings.exotel_account_sid,
        settings.exotel_api_key,
        settings.exotel_api_token,
        settings.exotel_caller_id,
        settings.exotel_stream_url,
        settings.exotel_stream_token,
        settings.exotel_status_callback_url,
        settings.exotel_webhook_token,
    )

    if not settings.exotel_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Exotel integration is disabled",
        )

    if not all(
        isinstance(value, str) and value.strip()
        for value in required_settings
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Exotel configuration is incomplete",
        )

    try:
        stream_url = _add_query_params(
            settings.exotel_stream_url,
            {
                "token": settings.exotel_stream_token,
                "sample-rate": "16000",
            },
            "wss",
        )
        callback_url = _add_query_params(
            settings.exotel_status_callback_url,
            {"token": settings.exotel_webhook_token},
            "https",
        )

        base_url = settings.exotel_base_url.rstrip("/")
        base_parts = urlsplit(base_url)

        if (
            base_parts.scheme != "https"
            or not base_parts.hostname
            or base_parts.username
            or base_parts.password
            or base_parts.query
            or base_parts.fragment
        ):
            raise ValueError("Invalid Exotel API base URL")

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Exotel URL configuration is invalid",
        ) from exc

    call = Call(
        user_id=current_user.id,
        status="initiating",
        started_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    endpoint = (
        f"{base_url}/v1/Accounts/"
        f"{settings.exotel_account_sid}/Calls/connect"
    )

    form_data = {
        "From": payload.destination_number,
        "CallerId": settings.exotel_caller_id,
        "StreamUrl": stream_url,
        "StreamType": "bidirectional",
        "StatusCallback": callback_url,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as http_client:
            response = await http_client.post(
                endpoint,
                data=form_data,
                auth=(
                    settings.exotel_api_key,
                    settings.exotel_api_token,
                ),
            )
            response.raise_for_status()
            provider_response = response.json()

    except (httpx.HTTPError, ValueError):
        _mark_call_failed(db, call)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Exotel call initiation failed",
        ) from None

    provider_call = (
        provider_response.get("Call")
        if isinstance(provider_response, dict)
        else None
    )
    provider_call_id = (
        provider_call.get("Sid")
        if isinstance(provider_call, dict)
        else None
    )

    if (
        not isinstance(provider_call_id, str)
        or not provider_call_id.strip()
        or len(provider_call_id) > 128
    ):
        _mark_call_failed(db, call)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Exotel returned an invalid call identifier",
        )

    mapping = ExotelCallMapping(
        call_id=call.id,
        provider="exotel",
        provider_call_id=provider_call_id.strip(),
    )
    db.add(mapping)
    call.status = "active"

    try:
        db.commit()
    except Exception:
        db.rollback()
        _mark_call_failed(db, call)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the provider call mapping",
        ) from None

    return {
        "call_id": call.id,
        "provider": "exotel",
        "provider_call_id": provider_call_id.strip(),
        "status": provider_call.get("Status", "queued"),
    }
