from datetime import datetime, timezone
from pathlib import Path
import wave

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.db.models import AudioChunk, Call, User
from app.schemas.audio_chunk import AudioChunkResponse


router = APIRouter(
    prefix="/api/calls",
    tags=["Audio"],
)


BASE_AUDIO_DIR = Path("data/calls")

MIN_CHUNK_DURATION_MS = 4900
MAX_CHUNK_DURATION_MS = 5100

MAX_AUDIO_FILE_SIZE = 10 * 1024 * 1024


def validate_wav_file(file_path: Path) -> tuple[int, int, int]:
    """
    Return:
        duration_ms,
        sample_rate,
        channels
    """

    try:
        with wave.open(str(file_path), "rb") as wav:
            sample_rate = wav.getframerate()
            channels = wav.getnchannels()
            frame_count = wav.getnframes()

            if sample_rate <= 0:
                raise ValueError("Invalid sample rate")

            if channels <= 0:
                raise ValueError("Invalid channel count")

            duration_ms = round(
                (frame_count / sample_rate) * 1000
            )

            return duration_ms, sample_rate, channels

    except (wave.Error, EOFError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid WAV audio file",
        ) from exc


@router.post(
    "/{call_id}/chunks",
    response_model=AudioChunkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_audio_chunk(
    call_id: int,
    sequence_number: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if sequence_number < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sequence_number must be greater than or equal to 1",
        )

    call = db.scalar(
        select(Call).where(
            Call.id == call_id,
            Call.user_id == current_user.id,
        )
    )

    if call is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found",
        )

    if call.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot upload audio to an ended call",
        )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio filename is required",
        )

    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only WAV audio files are supported",
        )

    existing_chunk = db.scalar(
        select(AudioChunk).where(
            AudioChunk.call_id == call_id,
            AudioChunk.sequence_number == sequence_number,
        )
    )

    if existing_chunk is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Audio chunk sequence number already exists",
        )

    call_dir = BASE_AUDIO_DIR / str(call_id)
    call_dir.mkdir(parents=True, exist_ok=True)

    final_path = call_dir / f"chunk_{sequence_number:06d}.wav"
    temp_path = call_dir / f".chunk_{sequence_number:06d}.tmp"

    total_bytes = 0

    try:
        with temp_path.open("wb") as output_file:
            while True:
                data = await file.read(1024 * 1024)

                if not data:
                    break

                total_bytes += len(data)

                if total_bytes > MAX_AUDIO_FILE_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Audio file is too large",
                    )

                output_file.write(data)

        if total_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Audio file is empty",
            )

        duration_ms, sample_rate, channels = validate_wav_file(
            temp_path
        )

        if not (
            MIN_CHUNK_DURATION_MS
            <= duration_ms
            <= MAX_CHUNK_DURATION_MS
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Audio chunk must be approximately 5 seconds "
                    f"(received {duration_ms} ms)"
                ),
            )

        start_offset_ms = (sequence_number - 1) * 5000
        end_offset_ms = start_offset_ms + duration_ms

        temp_path.replace(final_path)

        chunk = AudioChunk(
            call_id=call_id,
            sequence_number=sequence_number,
            start_offset_ms=start_offset_ms,
            end_offset_ms=end_offset_ms,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            channels=channels,
            audio_format="wav",
            file_path=str(final_path),
            file_size_bytes=total_bytes,
            created_at=datetime.now(timezone.utc),
        )

        db.add(chunk)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()

            if final_path.exists():
                final_path.unlink()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Audio chunk sequence number already exists",
            )

        db.refresh(chunk)

        return chunk

    except HTTPException:
        if temp_path.exists():
            temp_path.unlink()

        raise

    except Exception:
        if temp_path.exists():
            temp_path.unlink()

        if final_path.exists():
            final_path.unlink()

        raise

    finally:
        await file.close()