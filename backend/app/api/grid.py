from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.domain import default_grid_spec, validate_grid_spec
from app.domain import Constants as DomainConstants
from app.models import AppUser
from app.schemas import GridCellOut, GridOut, MemberOut, SourceOut
from app.services import cache, teams
from app.services.grid import build_grid, list_selected_sources

router = APIRouter()


@router.get("/grid", response_model=GridOut)
def get_grid(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    step_minutes: int = Query(default=DomainConstants.DEFAULT_STEP_MINUTES),
    slot_minutes: int = Query(default=DomainConstants.DEFAULT_SLOT_MINUTES),
    time_from: str = Query(default="09:00"),
    time_to: str = Query(default="21:00"),
    team_id: uuid.UUID | None = None,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    today = datetime.now(DomainConstants.DISPLAY_TZ).date()
    fallback = default_grid_spec(today)
    start = date.fromisoformat(date_from) if date_from else fallback.date_from
    end = date.fromisoformat(date_to) if date_to else fallback.date_to
    try:
        spec = validate_grid_spec(start, end, time_from, time_to, step_minutes, slot_minutes)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    now = datetime.now(DomainConstants.DISPLAY_TZ)
    if team_id is None:
        user_ids = [user.id]
    else:
        try:
            team = teams.get_team(db, team_id, user.id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Команда не найдена") from error
        user_ids = [member.user_id for member in team.members]
    key = cache.grid_key(
        user_ids,
        {
            "from": spec.date_from,
            "to": spec.date_to,
            "step": spec.step_minutes,
            "slot": spec.slot_minutes,
            "tf": time_from,
            "tt": time_to,
            "team": team_id,
            "viewer": user.id,
            "minute": now.strftime("%Y-%m-%dT%H:%M"),
        },
    )
    etag = f'"{key}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    cached = cache.get(key)
    if cached is not None:
        return Response(cached, media_type="application/json", headers={"ETag": etag, "X-Cache": "HIT"})
    result, members = build_grid(db, now, spec, user_ids)
    cells = [
        GridCellOut(
            day_index=cell.day_index,
            day=cell.day,
            hour=cell.hour,
            minute=cell.minute,
            free_count=cell.free_count,
            total=cell.total,
            start=cell.start,
            end=cell.end,
            slot_start=cell.slot_start,
            in_slot=cell.in_slot,
        )
        for cell in result.cells
    ]
    payload = GridOut(
        date_from=spec.date_from.isoformat(),
        date_to=spec.date_to.isoformat(),
        total=result.total,
        cells=cells,
        slot_minutes=spec.slot_minutes,
        step_minutes=spec.step_minutes,
        sources=[SourceOut(**item) for item in list_selected_sources(db, user.id)],
        members=[
            MemberOut(
                user_id=str(item.user_id),
                email=item.email,
                calendars=item.calendars,
                last_synced_at=item.last_synced_at,
                in_overlay=item.in_overlay,
            )
            for item in members
        ],
        team_id=str(team_id) if team_id else None,
    )
    body = payload.model_dump_json()
    cache.put(key, body)
    return Response(body, media_type="application/json", headers={"ETag": etag, "X-Cache": "MISS"})
