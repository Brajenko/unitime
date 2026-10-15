from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CollectionOut(BaseModel):
    id: str
    name: str
    selected: bool


class ConnectionOut(BaseModel):
    id: str
    provider: str
    status: str
    account_email: str | None
    last_error: str | None
    collections: list[CollectionOut]


class SelectCollectionsIn(BaseModel):
    selected_ids: list[str]


class AppleConnectIn(BaseModel):
    email: str
    app_password: str = Field(min_length=8)


class GridCellOut(BaseModel):
    day_index: int
    day: str
    hour: int
    minute: int
    free_count: int
    total: int
    start: datetime
    end: datetime
    slot_start: bool
    in_slot: bool


class SourceOut(BaseModel):
    id: str
    connection_id: str
    name: str
    provider: str
    selected: bool
    status: str
    account_email: str | None = None
    last_error: str | None = None


class MemberOut(BaseModel):
    user_id: str
    email: str
    calendars: int
    last_synced_at: datetime | None
    in_overlay: bool


class GridOut(BaseModel):
    date_from: str
    date_to: str
    total: int
    cells: list[GridCellOut]
    slot_minutes: int
    step_minutes: int
    sources: list[SourceOut]
    members: list[MemberOut]
    team_id: str | None = None


class CredentialsIn(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: str
    email: str


class TeamCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class TeamJoinIn(BaseModel):
    invite_token: str


class TeamMemberOut(BaseModel):
    user_id: str
    email: str


class TeamOut(BaseModel):
    id: str
    name: str
    invite_token: str
    is_owner: bool
    members: list[TeamMemberOut]


class LinkConnectIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
