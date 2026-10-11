import base64
import binascii
import hmac
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import Call, ExotelCallMapping
from app.services.streaming import StreamingSession
from app.services.streaming_chunk_processor import StreamingChunkProcessor


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/ws",
    tags=["Exotel Streaming"],
)

SAMPLE_RATE = 16_000
SAMPLE_WIDTH_BYTES = 2


def _valid_start_event(event: dict) -> tuple[str, str] | None:
    start = event.get("start")
    if not isinstance(start, dict):
        return None

    call_sid = start.get("call_sid")
    account_sid = start.get("account_sid")
    media_format = start.get("media_format")

    if not isinstance(call_sid, str) or not call_sid.strip():
        return None

    if not isinstance(account_sid, str) or not account_sid.strip():
        return None

    if not isinstance(media_format, dict):
        return None

    if media_format.get("encoding") != "audio/x-raw":
        return None

    try:
        sample_rate = int(media_format.get("sample_rate", 0))
        bit_rate = int(media_format.get("bit_rate", 0))
    except (TypeError, ValueError):
        return None

    if sample_rate != SAMPLE_RATE or bit_rate != 16:
        return None

    return call_sid.strip(), account_sid.strip()


@router.websocket("/exotel")
async def exotel_audio_stream(websocket: WebSocket):
    # Provider authentication is separate from user JWT authentication.
    supplied_token = websocket.query_params.get("token")
    configured_token = settings.exotel_stream_token
    configured_account_sid = settings.exotel_account_sid

    if (
        not settings.exotel_enabled
        or not configured_token
        or not configured_account_sid
        or not supplied_token
        or not hmac.compare_digest(supplied_token, configured_token)
    ):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    db: Session = SessionLocal()
    session = None
    processor = None
    call = None
    started = False

    try:
        while True:
            raw_message = await websocket.receive_text()

            try:
                event = json.loads(raw_message)
            except (json.JSONDecodeError, TypeError):
                await websocket.close(code=1003)
                return

            if not isinstance(event, dict):
                await websocket.close(code=1003)
                return

            event_type = event.get("event")

            if event_type == "connected":
                continue

            if event_type == "start":
                if started:
                    await websocket.close(code=1008)
                    return

                start_details = _valid_start_event(event)
                if start_details is None:
                    await websocket.close(code=1008)
                    return

                provider_call_id, account_sid = start_details

                if not hmac.compare_digest(
                    account_sid,
                    configured_account_sid,
                ):
                    await websocket.close(code=1008)
                    return

                mapping = db.scalar(
                    select(ExotelCallMapping).where(
                        ExotelCallMapping.provider == "exotel",
                        ExotelCallMapping.provider_call_id
                        == provider_call_id,
                    )
                )

                if mapping is None:
                    await websocket.close(code=1008)
                    return

                call = db.scalar(
                    select(Call).where(Call.id == mapping.call_id)
                )

                if call is None or call.status != "active":
                    await websocket.close(code=1008)
                    return

                session = StreamingSession(
                    call_id=call.id,
                    user_id=call.user_id,
                )
                processor = StreamingChunkProcessor(db)
                started = True
                continue

            if event_type == "media":
                if not started or session is None or processor is None:
                    await websocket.close(code=1008)
                    return

                media = event.get("media")
                if not isinstance(media, dict):
                    await websocket.close(code=1003)
                    return

                payload = media.get("payload")
                if not isinstance(payload, str) or not payload:
                    await websocket.close(code=1003)
                    return

                try:
                    pcm_audio = base64.b64decode(
                        payload,
                        validate=True,
                    )
                except (binascii.Error, ValueError):
                    await websocket.close(code=1003)
                    return

                if (
                    not pcm_audio
                    or len(pcm_audio) % SAMPLE_WIDTH_BYTES != 0
                ):
                    await websocket.close(code=1003)
                    return

                first_sequence_number = session.chunk_sequence + 1
                completed_chunks = session.add_frame(pcm_audio)

                for sequence_number, chunk_audio in enumerate(
                    completed_chunks,
                    start=first_sequence_number,
                ):
                    try:
                        processor.process_chunk(
                            call_id=call.id,
                            user_id=call.user_id,
                            sequence_number=sequence_number,
                            pcm_audio=chunk_audio,
                        )
                    except Exception:
                        db.rollback()
                        logger.exception(
                            "Exotel chunk processing failed "
                            "(call_id=%s, sequence_number=%s)",
                            call.id,
                            sequence_number,
                        )
                        # Continue receiving later chunks.
                continue

            if event_type == "stop":
                break

            # Do not interpret unexpected events as audio.
            await websocket.close(code=1003)
            return

    except WebSocketDisconnect:
        pass
    finally:
        db.close()
