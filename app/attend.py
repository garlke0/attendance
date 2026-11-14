from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.codes import accepted_codes, code_window, refresh_running
from app.db import get_db
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

# Arabic (٠-٩) and Persian (۰-۹) digits -> 0-9
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_digits(value: str) -> str:
    return value.translate(_DIGITS)


class AttendIn(BaseModel):
    name: str = Field(max_length=200)
    student_id: str = Field(max_length=50)
    major: str = Field(max_length=200)
    code: str = Field(max_length=10)


@router.post("/attend")
def attend(body: AttendIn, db: Session = Depends(get_db)):
    name = body.name.strip()
    student_id = normalize_digits(body.student_id.strip())
    major = body.major.strip()
    code = normalize_digits(body.code.strip())

    if not name:
        raise HTTPException(422, MSG_NAME)
    if not student_id or not (student_id.isascii() and student_id.isdigit()):
        raise HTTPException(422, MSG_DIGITS)
    if not major:
        raise HTTPException(422, MSG_MAJOR)

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

    db.add(
        Attendance(lecture_id=lec.id, name=name, student_id=student_id, major=major)
    )
    db.execute(
        update(Lecture)
        .where(Lecture.id == lec.id)
        .values(last_success_at=func.greatest(func.coalesce(Lecture.last_success_at, now), now))
    )
    db.commit()
    return {"message": MSG_OK}
