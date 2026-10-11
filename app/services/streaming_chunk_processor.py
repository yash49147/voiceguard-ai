from __future__ import annotations

import wave
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import AudioAnalysis, AudioChunk, AlertEvent
from app.services.alert_service import AlertService
from app.services.audio_features import TARGET_SAMPLE_RATE
from app.services.trust_score import TrustScoreService
from app.services.voice_analysis import VoiceAnalysisService
from app.ml.model_manager import ModelManager
from datetime import datetime, timezone


CALL_AUDIO_DIR = Path("data/calls")


class StreamingChunkProcessor:
    def __init__(self, db: Session):
        self.db = db
        self.voice_analysis = VoiceAnalysisService(ModelManager())

    def process_chunk(
        self,
        *,
        call_id: int,
        user_id: int,
        sequence_number: int,
        pcm_audio: bytes,
    ) -> dict:
        if len(pcm_audio) == 0:
            raise ValueError("Audio chunk cannot be empty")

        if sequence_number < 1:
            raise ValueError("sequence_number must be >= 1")

        call_dir = CALL_AUDIO_DIR / str(call_id)
        call_dir.mkdir(parents=True, exist_ok=True)

        audio_path = call_dir / f"chunk_{sequence_number}.wav"

        with wave.open(str(audio_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(TARGET_SAMPLE_RATE)
            wav_file.writeframes(pcm_audio)

        duration_ms = round(
            len(pcm_audio)
            / (TARGET_SAMPLE_RATE * 1 * 2)
            * 1000
        )

        start_offset_ms = (sequence_number - 1) * 5000
        end_offset_ms = start_offset_ms + duration_ms

        audio_chunk = AudioChunk(
            call_id=call_id,
            sequence_number=sequence_number,
            start_offset_ms=start_offset_ms,
            end_offset_ms=end_offset_ms,
            duration_ms=duration_ms,
            sample_rate=TARGET_SAMPLE_RATE,
            channels=1,
            audio_format="wav",
            file_path=str(audio_path),
            file_size_bytes=audio_path.stat().st_size,
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(audio_chunk)
        self.db.commit()
        self.db.refresh(audio_chunk)

        
        try:
            result = self.voice_analysis.analyze(str(audio_path))

            trust_result = TrustScoreService.calculate(
                result.ai_probability
            )
            alert_result = AlertService.evaluate(
                trust_result.alert_level
            )

            analysis = AudioAnalysis(
                chunk_id=audio_chunk.id,
                ai_probability=result.ai_probability,
                human_probability=result.human_probability,
                synthetic_probability=result.synthetic_probability,
                label=result.label,
                feature_count=result.feature_count,
                trust_score=trust_result.trust_score,
                alert_level=trust_result.alert_level,
            )
            self.db.add(analysis)
            self.db.flush()

            alert_event = None
            if alert_result.should_notify:
                alert_event = AlertEvent(
                    analysis_id=analysis.id,
                    user_id=user_id,
                    alert_level=alert_result.alert_level,
                    trust_score=trust_result.trust_score,
                    ai_probability=result.ai_probability,
                    notified=False,
                )
                self.db.add(alert_event)
                self.db.flush()

            self.db.commit()
            self.db.refresh(analysis)
            if alert_event is not None:
                self.db.refresh(alert_event)

        except Exception:
            self.db.rollback()
            raise

        return {
            "chunk_id": audio_chunk.id,
            "sequence_number": sequence_number,
            "duration_ms": duration_ms,
            "analysis_id": analysis.id,
            "ai_probability": result.ai_probability,
            "trust_score": trust_result.trust_score,
            "alert_level": trust_result.alert_level,
            "is_high_risk": alert_result.is_high_risk,
            "should_notify": alert_result.should_notify,
            "alert_event_id": (
                alert_event.id if alert_event is not None else None
            ),
        }


        trust_result = TrustScoreService.calculate(result.ai_probability)
        alert_result = AlertService.evaluate(trust_result.alert_level)

        analysis = AudioAnalysis(
            chunk_id=audio_chunk.id,
            ai_probability=result.ai_probability,
            human_probability=result.human_probability,
            synthetic_probability=result.synthetic_probability,
            label=result.label,
            feature_count=result.feature_count,
            trust_score=trust_result.trust_score,
            alert_level=trust_result.alert_level,
        )

        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)

        alert_event = None

        if alert_result.should_notify:
            alert_event = AlertEvent(
                analysis_id=analysis.id,
                user_id=user_id,
                alert_level=alert_result.alert_level,
                trust_score=trust_result.trust_score,
                ai_probability=result.ai_probability,
                notified=False,
            )

            self.db.add(alert_event)
            self.db.commit()
            self.db.refresh(alert_event)

        return {
            "chunk_id": audio_chunk.id,
            "sequence_number": sequence_number,
            "duration_ms": duration_ms,
            "analysis_id": analysis.id,
            "ai_probability": result.ai_probability,
            "trust_score": trust_result.trust_score,
            "alert_level": trust_result.alert_level,
            "is_high_risk": alert_result.is_high_risk,
            "should_notify": alert_result.should_notify,
            "alert_event_id": (
                alert_event.id if alert_event is not None else None
            ),
        }