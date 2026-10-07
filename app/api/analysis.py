from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.services.alert_service import AlertService
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import AudioAnalysis, AudioChunk, Call, User, AlertEvent
from app.ml.model_manager import ModelManager
from app.schemas.audio_analysis import AudioAnalysisResponse
from app.services.voice_analysis import VoiceAnalysisService
from app.services.trust_score import TrustScoreService



router = APIRouter(
    prefix="/api/calls",
    tags=["analysis"],
)


@router.post(
    "/{call_id}/chunks/{chunk_id}/analyze",
    response_model=AudioAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
def analyze_chunk(
    call_id: int,
    chunk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chunk = (
        db.query(AudioChunk)
        .join(Call, AudioChunk.call_id == Call.id)
        .filter(
            AudioChunk.id == chunk_id,
            AudioChunk.call_id == call_id,
            Call.user_id == current_user.id,
        )
        .first()
    )

    if chunk is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio chunk not found",
        )

    existing_analysis = (
        db.query(AudioAnalysis)
        .filter(
            AudioAnalysis.chunk_id == chunk.id
        )
        .first()
    )

    if existing_analysis is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Audio chunk has already been analyzed",
        )

    model_manager = ModelManager()

    try:
        analysis_service = VoiceAnalysisService(
            model_manager
        )

        result = analysis_service.analyze(
            chunk.file_path
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    trust_result = TrustScoreService.calculate(
        result.ai_probability
    )

    alert_result = AlertService.evaluate(
        trust_result.alert_level
    )

    analysis = AudioAnalysis(
        chunk_id=chunk.id,
        ai_probability=result.ai_probability,
        human_probability=result.human_probability,
        synthetic_probability=result.synthetic_probability,
        label=result.label,
        feature_count=result.feature_count,
        trust_score=trust_result.trust_score,
        alert_level=trust_result.alert_level,
    )

    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    if alert_result.should_notify:
        alert_event = AlertEvent(
            analysis_id=analysis.id,
            user_id=current_user.id,
            alert_level=alert_result.alert_level,
            trust_score=trust_result.trust_score,
            ai_probability=result.ai_probability,
            notified=False,
        )

        db.add(alert_event)
        db.commit()
        db.refresh(alert_event)

    return {
        "id": analysis.id,
        "chunk_id": analysis.chunk_id,
        "ai_probability": analysis.ai_probability,
        "human_probability": analysis.human_probability,
        "synthetic_probability": analysis.synthetic_probability,
        "label": analysis.label,
        "feature_count": analysis.feature_count,
        "trust_score": analysis.trust_score,
        "alert_level": analysis.alert_level,
        "is_high_risk": alert_result.is_high_risk,
        "should_notify": alert_result.should_notify,
        "created_at": analysis.created_at,
    }