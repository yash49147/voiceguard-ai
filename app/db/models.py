from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, ForeignKey, Float, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    calls = relationship(
        "Call",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    alert_events = relationship(
        "AlertEvent",
        back_populates="user",
        cascade="all, delete-orphan",
    )

class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    audio_chunks = relationship(
        "AudioChunk",
        back_populates="call",
        cascade="all, delete-orphan",
    )
    
    user = relationship("User", back_populates="calls")

class AudioChunk(Base):
    __tablename__ = "audio_chunks"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    start_offset_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    end_offset_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    sample_rate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    channels: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    audio_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    call = relationship(
        "Call",
        back_populates="audio_chunks",
    )

    analysis = relationship(
        "AudioAnalysis",
        back_populates="chunk",
        uselist=False,
        cascade="all, delete-orphan",
    )

class AudioAnalysis(Base):
    __tablename__ = "audio_analyses"

    id = Column(Integer, primary_key=True, index=True)
    
    chunk_id = Column(
        Integer,
        ForeignKey(
            "audio_chunks.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    ai_probability = Column(
        Float,
        nullable=False,
    )

    human_probability = Column(
        Float,
        nullable=False,
    )

    synthetic_probability = Column(
        Float,
        nullable=False,
    )

    label = Column(
        String(32),
        nullable=False,
    )

    feature_count = Column(
        Integer,
        nullable=False,
    )

    trust_score = Column(Float, nullable=False)
    alert_level = Column(String(16), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    chunk = relationship(
        "AudioChunk",
        back_populates="analysis",
    )

    alert_event = relationship(
        "AlertEvent",
        back_populates="analysis",
        uselist=False,
        cascade="all, delete-orphan",
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, index=True)

    analysis_id = Column(
        Integer,
        ForeignKey("audio_analyses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    alert_level = Column(String(16), nullable=False)
    trust_score = Column(Float, nullable=False)
    ai_probability = Column(Float, nullable=False)

    notified = Column(Boolean, nullable=False, default=False)
    acknowledged = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    analysis = relationship("AudioAnalysis", back_populates="alert_event")
    user = relationship("User", back_populates="alert_events")