from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Meeting, Team
from app.services import teams


class MeetingConflict(Exception):
    """Время пересекается с уже зафиксированной встречей команды."""


def validate_meeting_window(start: datetime, end: datetime, now: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Время должно быть с часовым поясом")
    if end <= start:
        raise ValueError("Конец встречи должен быть позже начала")
    if start <= now:
        raise ValueError("Встречу нельзя зафиксировать в прошлом")
    if end - start > Constants.MAX_DURATION:
        raise ValueError("Встреча не может быть длиннее 8 часов")
    for value in (start, end):
        if value.second or value.microsecond or value.minute % Constants.MINUTE_STEP:
            raise ValueError("Время должно быть кратно 5 минутам")


def create_meeting(
    session: Session,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
    title: str | None,
    now: datetime,
) -> Meeting:
    teams.get_team(session, team_id, user_id)
    validate_meeting_window(start, end, now)
    meeting = Meeting(
        team_id=team_id,
        created_by=user_id,
        period=Range(start, end, bounds="[)"),
        title=(title or "").strip()[: Constants.TITLE_MAX] or None,
    )
    session.add(meeting)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        if "ex_meeting_overlap" in str(error.orig):
            raise MeetingConflict() from error
        raise
    return meeting


def list_meetings(session: Session, team_id: uuid.UUID, user_id: uuid.UUID, since: datetime) -> list[Meeting]:
    teams.get_team(session, team_id, user_id)
    rows = session.scalars(select(Meeting).where(Meeting.team_id == team_id).order_by(Meeting.created_at))
    return sorted((item for item in rows if item.period.upper > since), key=lambda item: item.period.lower)


def cancel_meeting(session: Session, meeting_id: uuid.UUID, user_id: uuid.UUID) -> None:
    meeting = session.get(Meeting, meeting_id)
    if meeting is None:
        raise KeyError("meeting")
    teams.get_team(session, meeting.team_id, user_id)
    team = session.get(Team, meeting.team_id)
    if user_id not in (meeting.created_by, team.owner_id):
        raise PermissionError("meeting")
    session.delete(meeting)
    session.flush()


class Constants:
    MAX_DURATION = timedelta(hours=8)
    MINUTE_STEP = 5
    TITLE_MAX = 200
