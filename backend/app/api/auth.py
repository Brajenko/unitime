from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import AppUser
from app.schemas import CredentialsIn, UserOut
from app.services import auth

router = APIRouter()


def _set_cookie(response: Response, user: AppUser) -> None:
    response.set_cookie(
        "session",
        auth.create_session(user.id),
        max_age=auth.Constants.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.post("/auth/register", response_model=UserOut)
def register(body: CredentialsIn, response: Response, db: Session = Depends(get_db)):
    try:
        user = auth.register(db, body.email, body.password)
    except auth.AuthError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    db.commit()
    _set_cookie(response, user)
    return UserOut(id=str(user.id), email=user.email or "")


@router.post("/auth/login", response_model=UserOut)
def login(body: CredentialsIn, request: Request, response: Response, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    try:
        user = auth.authenticate(db, body.email, body.password, client_ip)
    except auth.AuthError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    _set_cookie(response, user)
    return UserOut(id=str(user.id), email=user.email or "")


@router.post("/auth/logout", status_code=204)
def logout(response: Response, session: str | None = Cookie(default=None)):
    auth.destroy_session(session)
    response.delete_cookie("session", path="/")


@router.get("/me", response_model=UserOut)
def me(user: AppUser = Depends(current_user)):
    return UserOut(id=str(user.id), email=user.email or "")
