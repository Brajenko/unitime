from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Provider(StrEnum):
    GOOGLE = "google"
    YANDEX = "yandex"
    APPLE = "apple"
    LINK = "link"


class AuthKind(StrEnum):
    OAUTH = "oauth"
    APP_PASSWORD = "app_password"
    PUBLIC_LINK = "public_link"


class ConnectionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    AUTH_FAILED = "auth_failed"
    SYNCING = "syncing"


class SyncStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    connections: Mapped[list[CalendarConnection]] = relationship(back_populates="user")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    invite_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    members: Mapped[list[TeamMember]] = relationship(back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    team: Mapped[Team] = relationship(back_populates="members")
    user: Mapped[AppUser] = relationship()


class CalendarConnection(Base):
    __tablename__ = "calendar_connections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    auth_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ConnectionStatus.PENDING)
    encrypted_secret: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    account_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    principal_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[AppUser] = relationship(back_populates="connections")
    collections: Mapped[list[CalendarCollection]] = relationship(
        back_populates="connection",
        cascade="all, delete-orphan",
    )


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (Index("ix_sync_jobs_dispatch", "status", "available_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calendar_connections.id", ondelete="CASCADE"), index=True
    )
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default=SyncStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    process_count: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class CalendarCollection(Base):
    __tablename__ = "calendar_collections"
    __table_args__ = (UniqueConstraint("connection_id", "external_id", name="uq_collection_external"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calendar_connections.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    connection: Mapped[CalendarConnection] = relationship(back_populates="collections")
    busy_intervals: Mapped[list[BusyIntervalRow]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
    )


class BusyIntervalRow(Base):
    __tablename__ = "busy_intervals"
    __table_args__ = (
        UniqueConstraint("collection_id", "uid", "occurrence_start", name="uq_busy_occurrence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calendar_collections.id"), nullable=False)
    uid: Mapped[str] = mapped_column(String(1024), nullable=False)
    occurrence_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period = mapped_column(TSTZRANGE, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")

    collection: Mapped[CalendarCollection] = relationship(back_populates="busy_intervals")


class Meeting(Base):
    """Зафиксированная встреча команды. Пересечение встреч одной команды запрещено ограничением в БД."""

    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    period = mapped_column(TSTZRANGE, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author: Mapped[AppUser] = relationship()
    team: Mapped[Team] = relationship()


class AvailabilityWindow(Base):
    """Свободное окно, отмеченное вручную участником без календаря (US-07)."""

    __tablename__ = "availability_windows"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id"), nullable=False, index=True)
    period = mapped_column(TSTZRANGE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
