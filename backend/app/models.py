from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Provider(StrEnum):
    GOOGLE = "google"
    YANDEX = "yandex"
    APPLE = "apple"


class AuthKind(StrEnum):
    OAUTH = "oauth"
    APP_PASSWORD = "app_password"


class ConnectionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    AUTH_FAILED = "auth_failed"
    SYNCING = "syncing"


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    connections: Mapped[list[CalendarConnection]] = relationship(back_populates="user")


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
