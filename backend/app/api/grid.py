from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain import default_grid_spec, validate_grid_spec
from app.domain import Constants as DomainConstants
from app.schemas import GridCellOut, GridOut, SourceOut, SuggestedSlotOut
from app.services.grid import build_grid, list_selected_sources

router = APIRouter()


@router.get("/grid", response_model=GridOut)
def get_grid(
    date_from: str | None = None,
    date_to: str | None = None,
    step_minutes: int = Query(default=DomainConstants.DEFAULT_STEP_MINUTES),
    slot_minutes: int = Query(default=DomainConstants.DEFAULT_SLOT_MINUTES),
    time_from: str = Query(default="09:00"),
    time_to: str = Query(default="21:00"),
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
    result = build_grid(db, now, spec)
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
            in_suggested=False,
        )
        for cell in result.cells
    ]
    slots = [SuggestedSlotOut(start=item.start, end=item.end) for item in result.slots]
    return GridOut(
        date_from=spec.date_from.isoformat(),
        date_to=spec.date_to.isoformat(),
        total=result.total,
        cells=cells,
        suggested=slots[0] if slots else None,
        slots=slots,
        sources=[SourceOut(**item) for item in list_selected_sources(db)],
    )
