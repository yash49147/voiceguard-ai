from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Call, User
from app.schemas.call import CallResponse
from app.api.auth import get_current_user


router = APIRouter(
    prefix="/api/calls",
    tags=["Calls"],
)


@router.post(
    "",
    response_model=CallResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_call(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)

    call = Call(
        user_id=current_user.id,
        status="active",
        started_at=now,
        created_at=now,
    )

    db.add(call)
    db.commit()
    db.refresh(call)

    return call


@router.patch(
    "/{call_id}/end",
    response_model=CallResponse,
)
def end_call(
    call_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
            detail="Call is already ended",
        )

    call.status = "completed"
    call.ended_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(call)

    return call


@router.get(
    "",
    response_model=list[CallResponse],
)
def list_calls(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    calls = db.scalars(
        select(Call)
        .where(Call.user_id == current_user.id)
        .order_by(Call.created_at.desc())
    ).all()

    return list(calls)


@router.get(
    "/{call_id}",
    response_model=CallResponse,
)
def get_call(
    call_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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

    return call