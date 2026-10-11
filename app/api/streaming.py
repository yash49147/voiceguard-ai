from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.services.streaming_chunk_processor import StreamingChunkProcessor
from app.core.security import decode_access_token
from app.db.database import SessionLocal
from app.db.models import Call
from app.services.streaming import StreamingSession
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ws", tags=["streaming"])


def get_user_id_from_token(token: str) -> int:
    """
    Validate the JWT and return the authenticated user ID.

    IMPORTANT:
    decode_access_token() already returns the JWT subject
    (user ID) as a string. Do not change that helper.
    """
    user_id = decode_access_token(token)

    if user_id is None:
        raise ValueError("Invalid authentication token")

    try:
        return int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid authentication token") from exc


@router.websocket("/calls/{call_id}")
async def call_stream(websocket: WebSocket, call_id: int):
    """
    Real-time audio streaming endpoint.

    Step 9 pipeline:

        WebSocket binary frames
                ↓
        StreamingSession
                ↓
        5-second completed chunks
                ↓
        StreamingChunkProcessor
                ↓
        Existing audio analysis pipeline
                ↓
        Trust score / alert processing
                ↓
        chunk_processed WebSocket event
    """

    token = websocket.query_params.get("token")

    # ---------------------------------------------------------
    # Authentication
    # ---------------------------------------------------------
    if not token:
        await websocket.close(code=1008)
        return

    try:
        user_id = get_user_id_from_token(token)
    except ValueError:
        await websocket.close(code=1008)
        return

    db: Session = SessionLocal()

    try:
        # -----------------------------------------------------
        # Call ownership + active-call validation
        # -----------------------------------------------------
        call = (
            db.query(Call)
            .filter(
                Call.id == call_id,
                Call.user_id == user_id,
            )
            .one_or_none()
        )

        if call is None:
            await websocket.close(code=1008)
            return

        if call.status != "active":
            await websocket.close(code=1008)
            return

        # -----------------------------------------------------
        # Accept WebSocket connection
        # -----------------------------------------------------
        await websocket.accept()

        # -----------------------------------------------------
        # Create streaming session
        # -----------------------------------------------------
        session = StreamingSession(
            call_id=call.id,
            user_id=user_id,
        )

        # -----------------------------------------------------
        # Create Step 9 chunk processor
        # -----------------------------------------------------
        processor = StreamingChunkProcessor(db)

        # -----------------------------------------------------
        # Connection confirmation
        # -----------------------------------------------------
        await websocket.send_json(
            {
                "type": "connected",
                "call_id": call.id,
            }
        )

        # -----------------------------------------------------
        # Streaming loop
        # -----------------------------------------------------
        try:
            while True:
                message = await websocket.receive()

                # -------------------------------------------------
                # Client disconnected
                # -------------------------------------------------
                if message.get("type") == "websocket.disconnect":
                    break

                # -------------------------------------------------
                # Binary audio frame
                # -------------------------------------------------
                if message.get("bytes") is not None:
                    # Capture the first sequence number before add_frame()
                    # increments the session counter for completed chunks.
                    first_sequence_number = session.chunk_sequence + 1

                    completed_chunks = session.add_frame(
                        message["bytes"]
                    )

                    await websocket.send_json(
                        {
                            "type": "frame_received",
                            "frame_count": session.frame_count,
                            "buffered_bytes": session.buffered_bytes,
                        }
                    )

                    # Give every completed chunk its own sequence number.
                    for sequence_number, chunk_audio in enumerate(
                        completed_chunks,
                        start=first_sequence_number,
                    ):
                        try:
                            result = processor.process_chunk(
                                call_id=call.id,
                                user_id=user_id,
                                sequence_number=sequence_number,
                                pcm_audio=chunk_audio,
                            )

                        except Exception:
                            db.rollback()

                            logger.exception(
                                "Failed to process audio chunk "
                                "(call_id=%s, sequence_number=%s)",
                                call.id,
                                sequence_number,
                            )

                            await websocket.send_json(
                                {
                                    "type": "chunk_processing_error",
                                    "sequence_number": sequence_number,
                                    "message": (
                                        "Unable to process audio chunk. "
                                        "Streaming will continue."
                                    ),
                                    "buffered_bytes": session.buffered_bytes,
                                }
                            )
                            continue

                        await websocket.send_json(
                            {
                                "type": "chunk_processed",
                                **result,
                                "buffered_bytes": session.buffered_bytes,
                            }
                        )

                    continue

                # -------------------------------------------------
                # Text message
                # -------------------------------------------------
                if message.get("text") is not None:
                    if message["text"] == "ping":
                        await websocket.send_json(
                            {
                                "type": "pong",
                            }
                        )
                    else:
                        await websocket.send_json(
                            {
                                "type": "ignored",
                            }
                        )

        except WebSocketDisconnect:
            pass

    finally:
        db.close()