from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import AppUser, Team
from app.schemas import TeamCreateIn, TeamJoinIn, TeamMemberOut, TeamOut
from app.services import teams

router = APIRouter()


def _serialize(team: Team, user: AppUser) -> TeamOut:
    return TeamOut(
        id=str(team.id),
        name=team.name,
        invite_token=team.invite_token,
        is_owner=team.owner_id == user.id,
        members=[TeamMemberOut(user_id=str(item.user_id), email=item.user.email or "") for item in team.members],
    )


@router.get("/teams", response_model=list[TeamOut])
def my_teams(user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return [_serialize(item, user) for item in teams.list_teams(db, user.id)]


@router.post("/teams", response_model=TeamOut)
def create_team(body: TeamCreateIn, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    team = teams.create_team(db, user.id, body.name)
    db.refresh(team)
    return _serialize(teams.get_team(db, team.id, user.id), user)


@router.post("/teams/join", response_model=TeamOut)
def join_team(body: TeamJoinIn, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    try:
        team = teams.join_team(db, body.invite_token, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Приглашение недействительно") from error
    db.refresh(team)
    return _serialize(teams.get_team(db, team.id, user.id), user)


@router.get("/teams/{team_id}", response_model=TeamOut)
def team_detail(team_id: uuid.UUID, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return _serialize(teams.get_team(db, team_id, user.id), user)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Команда не найдена") from error
