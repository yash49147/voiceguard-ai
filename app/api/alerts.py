from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.db.models import AlertEvent, User
from app.schemas.alert_event import AlertEventResponse


router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
)


@router.get(
    "",
    response_model=list[AlertEventResponse],
)
def list_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(AlertEvent)
        .filter(AlertEvent.user_id == current_user.id)
        .order_by(AlertEvent.created_at.desc())
        .all()
    )


@router.get(
    "/{alert_id}",
    response_model=AlertEventResponse,
)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = (
        db.query(AlertEvent)
        .filter(
            AlertEvent.id == alert_id,
            AlertEvent.user_id == current_user.id,
        )
        .one_or_none()
    )

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert event not found",
        )

    return alert



@router.patch(
    "/{alert_id}/acknowledge",
    response_model=AlertEventResponse,
)
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = (
        db.query(AlertEvent)
        .filter(
            AlertEvent.id == alert_id,
            AlertEvent.user_id == current_user.id,
        )
        .one_or_none()
    )

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert event not found",
        )

    alert.acknowledged = True

    db.commit()
    db.refresh(alert)

    return alert