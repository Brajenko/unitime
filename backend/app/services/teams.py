from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Team, TeamMember


def create_team(session: Session, owner_id: uuid.UUID, name: str) -> Team:
    team = Team(name=name.strip()[:128] or "Команда", invite_token=secrets.token_urlsafe(Constants.INVITE_BYTES), owner_id=owner_id)
    team.members.append(TeamMember(user_id=owner_id))
    session.add(team)
    session.flush()
    return team


def list_teams(session: Session, user_id: uuid.UUID) -> list[Team]:
    return list(
        session.scalars(
            select(Team)
            .join(TeamMember)
            .where(TeamMember.user_id == user_id)
            .options(selectinload(Team.members).selectinload(TeamMember.user))
            .order_by(Team.created_at)
        )
    )


def get_team(session: Session, team_id: uuid.UUID, user_id: uuid.UUID) -> Team:
    team = session.scalars(
        select(Team)
        .join(TeamMember)
        .where(Team.id == team_id, TeamMember.user_id == user_id)
        .options(selectinload(Team.members).selectinload(TeamMember.user))
    ).first()
    if team is None:
        raise KeyError("team")
    return team


def join_team(session: Session, invite_token: str, user_id: uuid.UUID) -> Team:
    team = session.scalars(
        select(Team).where(Team.invite_token == invite_token).options(selectinload(Team.members).selectinload(TeamMember.user))
    ).first()
    if team is None:
        raise KeyError("team")
    if all(member.user_id != user_id for member in team.members):
        team.members.append(TeamMember(user_id=user_id))
        session.flush()
    return team


class Constants:
    INVITE_BYTES = 18
