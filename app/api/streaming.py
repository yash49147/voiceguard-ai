from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.database import SessionLocal
from app.db.models import Call
from app.services.streaming import StreamingSession


router = APIRouter(prefix="/api/ws", tags=["streaming"])


def get_user_id_from_token(token: str) -> int:
    user_id = decode_access_token(token)

    if user_id is None:
        raise ValueError("Invalid authentication token")

    try:
        return int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid authentication token") from exc


@router.websocket("/calls/{call_id}")
async def call_stream(websocket: WebSocket, call_id: int):
    token = websocket.query_params.get("token")

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

        await websocket.accept()

        session = StreamingSession(
            call_id=call.id,
            user_id=user_id,
        )

        await websocket.send_json(
            {
                "type": "connected",
                "call_id": call.id,
            }
        )

        try:
            while True:
                message = await websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    break

                if message.get("bytes") is not None:
                    buffered_bytes = session.add_frame(
                        message["bytes"]
                    )

                    await websocket.send_json(
                        {
                            "type": "frame_received",
                            "frame_count": session.frame_count,
                            "buffered_bytes": buffered_bytes,
                        }
                    )
                    continue

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