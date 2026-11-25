import os
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.codes import accepted_codes, code_window, refresh_running
from app.db import get_db
from app.location import on_campus, valid_coords
from app.security import hash_token, new_session_token
from app.models import Attendance, CodeAttempt, Lecture

router = APIRouter(prefix="/api")

MAX_TRIES = 5

MSG_OK = "تم التحضير"
MSG_DIGITS = "الرقم الجامعي لازم يكون أرقام فقط"
MSG_NAME = "الاسم مطلوب"
MSG_MAJOR = "التخصص مطلوب"
MSG_ENDED = "انتهى وقت التحضير"
MSG_ALREADY = "تم تسجيل حضورك مسبقاً"
MSG_NO_TRIES = "استنفدت المحاولات لهذا الكود"
MSG_WRONG = "الكود غير صحيح، باقي لك {n} محاولات"
MSG_LOCATION_NEEDED = "شغّل الموقع وحدّث الصفحة عشان تتحضّر"
MSG_NOT_ON_CAMPUS = "انت لست في الجامعة، لم يتم تحضيرك"
MSG_DEVICE_LOCKED = "تم تحضير طالب من هذا الجهاز، حاول بعد ١٥ دقيقة"

# One device (browser) can register only one student per lecture
# within 15 minutes of its last successful registration.
DEVICE_COOKIE = "device"
DEVICE_LOCK = timedelta(minutes=15)
DEVICE_COOKIE_MAX_AGE = 400 * 24 * 60 * 60
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() != "false"

# Arabic (٠-٩) and Persian (۰-۹) digits -> 0-9
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_digits(value: str) -> str:
    return value.translate(_DIGITS)


class AttendIn(BaseModel):
    name: str = Field(max_length=200)
    student_id: str = Field(max_length=50)
    code: str = Field(max_length=10)
    # Student's phone location (not saved; only checked against the campus)
    lat: float | None = None
    lng: float | None = None


@router.post("/attend")
def attend(
    body: AttendIn,
    response: Response,
    device: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    student_id = normalize_digits(body.student_id.strip())
    code = normalize_digits(body.code.strip())

    if not name:
        raise HTTPException(422, MSG_NAME)
    if not student_id or not (student_id.isascii() and student_id.isdigit()):
        raise HTTPException(422, MSG_DIGITS)
    now = db.scalar(select(func.now()))

    # The running session (starting a new one stops the others).
    lec = db.scalars(
        select(Lecture)
        .where(Lecture.is_running.is_(True))
        .order_by(Lecture.started_at.desc())
    ).first()
    if lec is None or not refresh_running(lec, now):
        db.commit()  # saves an auto-stop if it just happened
        raise HTTPException(410, MSG_ENDED)

    # Location: checked before the code, so it never uses up a code try.
    if not valid_coords(body.lat, body.lng):
        db.rollback()
        raise HTTPException(422, MSG_LOCATION_NEEDED)
    if not on_campus(body.lat, body.lng):
        db.rollback()
        raise HTTPException(403, MSG_NOT_ON_CAMPUS)

    # Device lock: same browser, same lecture, a different student,
    # within 15 minutes of that browser's last successful registration.
    device_hash = hash_token(device) if device else None
    if device_hash:
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"device:{lec.id}:{device_hash}"},
        )
        locked = db.scalar(
            select(Attendance.id).where(
                Attendance.lecture_id == lec.id,
                Attendance.device_hash == device_hash,
                Attendance.student_id != student_id,
                Attendance.created_at > now - DEVICE_LOCK,
            )
        )
        if locked:
            db.rollback()
            raise HTTPException(429, MSG_DEVICE_LOCKED)

    # One request at a time per student per lecture (stops double-taps
    # registering twice); different students are not blocked.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lid, hashtext(:sid))"),
        {"lid": lec.id, "sid": student_id},
    )

    already = db.scalar(
        select(Attendance.id).where(
            Attendance.lecture_id == lec.id, Attendance.student_id == student_id
        )
    )
    if already:
        db.rollback()
        raise HTTPException(409, MSG_ALREADY)

    window = code_window(lec, now)
    attempt = db.get(CodeAttempt, (lec.id, student_id, window))
    failures = attempt.failures if attempt else 0
    if failures >= MAX_TRIES:
        db.rollback()
        raise HTTPException(429, MSG_NO_TRIES)

    if code not in accepted_codes(lec, now):
        db.execute(
            insert(CodeAttempt)
            .values(lecture_id=lec.id, student_id=student_id, code_window=window, failures=1)
            .on_conflict_do_update(
                index_elements=["lecture_id", "student_id", "code_window"],
                set_={"failures": CodeAttempt.failures + 1},
            )
        )
        db.commit()
        left = MAX_TRIES - (failures + 1)
        if left <= 0:
            raise HTTPException(429, MSG_NO_TRIES)
        raise HTTPException(400, MSG_WRONG.format(n=left))

    if not device:
        # First registration from this browser: give it a device cookie.
        device = new_session_token()
        device_hash = hash_token(device)
        response.set_cookie(
            DEVICE_COOKIE, device, max_age=DEVICE_COOKIE_MAX_AGE,
            httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/",
        )
    db.add(
        # The student does not type the major: it comes from the lecture.
        Attendance(lecture_id=lec.id, name=name, student_id=student_id,
                   major=lec.major, device_hash=device_hash, created_at=now)
    )
    db.execute(
        update(Lecture)
        .where(Lecture.id == lec.id)
        .values(last_success_at=func.greatest(func.coalesce(Lecture.last_success_at, now), now))
    )
    db.commit()
    return {"message": MSG_OK}
