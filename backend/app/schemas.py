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
    in_suggested: bool


class SuggestedSlotOut(BaseModel):
    start: datetime
    end: datetime


class SourceOut(BaseModel):
    id: str
    name: str
    provider: str
    selected: bool
    status: str
    account_email: str | None = None
    last_error: str | None = None


class GridOut(BaseModel):
    date_from: str
    date_to: str
    total: int
    cells: list[GridCellOut]
    suggested: SuggestedSlotOut | None
    slots: list[SuggestedSlotOut]
    sources: list[SourceOut]
