from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppUser
from app.services.auth import user_id_for_session


def current_user(session: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> AppUser:
    user_id = user_id_for_session(session)
    user = db.get(AppUser, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user
