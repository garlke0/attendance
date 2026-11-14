import os
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Doctor, LoginSession
from app.security import (
    DUMMY_HASH,
    hash_token,
    new_session_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth")

COOKIE_NAME = "session"
# Browsers cap cookie lifetime at about 400 days; the doctor stays logged in
# until he presses logout (or this limit is reached).
COOKIE_MAX_AGE = 400 * 24 * 60 * 60
# True on Vercel (HTTPS). Set COOKIE_SECURE=false in .env for local http.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() != "false"

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 5

MSG_WRONG = "اسم المستخدم أو كلمة السر غير صحيحة"
MSG_LOCKED = "تم إيقاف الدخول مؤقتاً بسبب محاولات خاطئة، حاول بعد {m} دقائق"
MSG_NOT_LOGGED_IN = "يجب تسجيل الدخول"


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    doctor = db.scalars(
        select(Doctor).where(Doctor.username == body.username).with_for_update()
    ).first()

    if doctor is None:
        verify_password(body.password, DUMMY_HASH)
        raise HTTPException(401, MSG_WRONG)

    now = db.scalar(select(func.now()))

    if doctor.locked_until and doctor.locked_until > now:
        remaining = doctor.locked_until - now
        minutes = max(1, -(-int(remaining.total_seconds()) // 60))
        db.rollback()
        raise HTTPException(429, MSG_LOCKED.format(m=minutes))

    if not verify_password(body.password, doctor.password_hash):
        doctor.failed_logins += 1
        if doctor.failed_logins >= MAX_FAILED_LOGINS:
            doctor.failed_logins = 0
            doctor.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            db.commit()
            raise HTTPException(429, MSG_LOCKED.format(m=LOCK_MINUTES))
        db.commit()
        raise HTTPException(401, MSG_WRONG)

    doctor.failed_logins = 0
    doctor.locked_until = None
    token = new_session_token()
    db.add(LoginSession(token_hash=hash_token(token), doctor_id=doctor.id))
    db.commit()

    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
def logout(
    response: Response,
    session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if session:
        row = db.get(LoginSession, hash_token(session))
        if row:
            db.delete(row)
            db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


def current_doctor(
    session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Doctor:
    """Use as a dependency on every doctor endpoint."""
    if not session:
        raise HTTPException(401, MSG_NOT_LOGGED_IN)
    row = db.get(LoginSession, hash_token(session))
    if row is None:
        raise HTTPException(401, MSG_NOT_LOGGED_IN)
    return db.get(Doctor, row.doctor_id)
