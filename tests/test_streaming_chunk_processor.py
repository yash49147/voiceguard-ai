
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import uuid

from app.db.database import Base, engine
from app.db.models import (
    AlertEvent,
    AudioAnalysis,
    AudioChunk,
    Call,
    User,
)
from app.services.streaming_chunk_processor import StreamingChunkProcessor
from app.services.streaming import CHUNK_SIZE_BYTES


@pytest.fixture
def processor_context(db_session, monkeypatch, tmp_path):
    # Ensure all application models are registered before creating tables.
    Base.metadata.create_all(bind=engine)

    user = User(
        email=f"processor-{uuid.uuid4().hex}@example.com",
        full_name="Processor Test",
        password_hash="test-hash",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    now = datetime.now(timezone.utc)
    call = Call(
        user_id=user.id,
        status="active",
        started_at=now,
        created_at=now,
    )
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)

    monkeypatch.setattr(
        "app.services.streaming_chunk_processor.CALL_AUDIO_DIR",
        tmp_path,
    )

    processor = StreamingChunkProcessor(db_session)
    processor.voice_analysis = Mock()

    return db_session, processor, call.id, user.id


def make_analysis_result(ai_probability=10.0):
    return SimpleNamespace(
        ai_probability=ai_probability,
        human_probability=100.0 - ai_probability,
        synthetic_probability=ai_probability,
        label="human" if ai_probability < 50 else "synthetic",
        feature_count=38,
    )


def test_process_chunk_persists_chunk_and_analysis(processor_context):
    db, processor, call_id, user_id = processor_context
    processor.voice_analysis.analyze.return_value = make_analysis_result()

    result = processor.process_chunk(
        call_id=call_id,
        user_id=user_id,
        sequence_number=1,
        pcm_audio=b"\x00\x00" * (CHUNK_SIZE_BYTES // 2),
    )

    assert result["sequence_number"] == 1
    assert result["duration_ms"] == 5000
    assert result["analysis_id"] is not None
    assert result["alert_level"] == "SAFE"
    assert result["should_notify"] is False

    chunk = db.query(AudioChunk).filter_by(id=result["chunk_id"]).one()
    analysis = (
        db.query(AudioAnalysis)
        .filter_by(id=result["analysis_id"])
        .one()
    )

    assert chunk.duration_ms == 5000
    assert chunk.sample_rate == 16000
    assert analysis.chunk_id == chunk.id
    processor.voice_analysis.analyze.assert_called_once()


def test_process_chunk_creates_alert_for_high_risk(processor_context):
    db, processor, call_id, user_id = processor_context
    processor.voice_analysis.analyze.return_value = make_analysis_result(
        ai_probability=90.0,
    )

    result = processor.process_chunk(
        call_id=call_id,
        user_id=user_id,
        sequence_number=1,
        pcm_audio=b"\x00\x00" * (CHUNK_SIZE_BYTES // 2),
    )

    assert result["alert_level"] == "HIGH"
    assert result["should_notify"] is True
    assert result["alert_event_id"] is not None

    alert = (
        db.query(AlertEvent)
        .filter_by(id=result["alert_event_id"])
        .one()
    )

    assert alert.user_id == user_id
    assert alert.analysis_id == result["analysis_id"]
    assert alert.notified is False


def test_process_chunk_rejects_empty_audio(db_session):
    processor = StreamingChunkProcessor(db_session)

    with pytest.raises(ValueError, match="cannot be empty"):
        processor.process_chunk(
            call_id=1,
            user_id=1,
            sequence_number=1,
            pcm_audio=b"",
        )


def test_process_chunk_rejects_invalid_sequence(db_session):
    processor = StreamingChunkProcessor(db_session)

    with pytest.raises(ValueError, match="sequence_number"):
        processor.process_chunk(
            call_id=1,
            user_id=1,
            sequence_number=0,
            pcm_audio=b"\x00\x00",
        )



def test_analysis_failure_preserves_chunk_without_analysis(
    processor_context,
):
    db, processor, call_id, user_id = processor_context
    processor.voice_analysis.analyze.side_effect = RuntimeError(
        "Model inference failed"
    )

    with pytest.raises(RuntimeError, match="Model inference failed"):
        processor.process_chunk(
            call_id=call_id,
            user_id=user_id,
            sequence_number=1,
            pcm_audio=b"\x00\x00" * (CHUNK_SIZE_BYTES // 2),
        )

    chunk = (
        db.query(AudioChunk)
        .filter_by(call_id=call_id, sequence_number=1)
        .one()
    )
    assert chunk is not None

    analysis = (
        db.query(AudioAnalysis)
        .filter_by(chunk_id=chunk.id)
        .one_or_none()
    )
    assert analysis is None


