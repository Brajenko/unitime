from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.domain import Constants as DomainConstants
from app.models import AppUser, Meeting, Team
from app.schemas import MeetingIn, MeetingOut
from app.services import meetings

router = APIRouter()


def _serialize(meeting: Meeting, team: Team, user: AppUser) -> MeetingOut:
    return MeetingOut(
        id=str(meeting.id),
        team_id=str(meeting.team_id),
        start=meeting.period.lower,
        end=meeting.period.upper,
        title=meeting.title,
        created_by_email=meeting.author.email or "",
        can_cancel=user.id in (meeting.created_by, team.owner_id),
    )


@router.post("/teams/{team_id}/meetings", response_model=MeetingOut, status_code=201)
def create_meeting(
    team_id: uuid.UUID, body: MeetingIn, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
):
    now = datetime.now(DomainConstants.DISPLAY_TZ)
    try:
        meeting = meetings.create_meeting(db, team_id, user.id, body.start, body.end, body.title, now)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Команда не найдена") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except meetings.MeetingConflict as error:
        raise HTTPException(status_code=409, detail="Это время уже занято другой встречей") from error
    return _serialize(meeting, db.get(Team, team_id), user)


@router.get("/teams/{team_id}/meetings", response_model=list[MeetingOut])
def list_meetings(team_id: uuid.UUID, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.now(DomainConstants.DISPLAY_TZ)
    try:
        items = meetings.list_meetings(db, team_id, user.id, now)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Команда не найдена") from error
    team = db.get(Team, team_id)
    return [_serialize(item, team, user) for item in items]


@router.delete("/meetings/{meeting_id}", status_code=204)
def cancel_meeting(meeting_id: uuid.UUID, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    try:
        meetings.cancel_meeting(db, meeting_id, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Встреча не найдена") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail="Отменить может автор встречи или владелец команды") from error
    return Response(status_code=204)
