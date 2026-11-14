import secrets
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth import current_doctor
from app.db import get_db
from app.models import CodeAttempt, Doctor, Lecture

router = APIRouter(prefix="/api/lectures")

YEMEN_TZ = ZoneInfo("Asia/Aden")

MSG_NOT_FOUND = "المحاضرة غير موجودة"


def yemen_today() -> date:
    return datetime.now(YEMEN_TZ).date()


class LectureIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lecture_time: str | None = Field(default=None, max_length=20)


def lecture_out(lec: Lecture) -> dict:
    return {
        "id": lec.id,
        "name": lec.name,
        "lecture_date": lec.lecture_date.isoformat(),
        "lecture_time": lec.lecture_time,
        "is_running": lec.is_running,
    }


def get_own_lecture(db: Session, lecture_id: int, doctor: Doctor) -> Lecture:
    lec = db.get(Lecture, lecture_id)
    if lec is None or lec.doctor_id != doctor.id:
        raise HTTPException(404, MSG_NOT_FOUND)
    return lec


@router.get("")
def list_lectures(
    doctor: Doctor = Depends(current_doctor), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(Lecture)
        .where(Lecture.doctor_id == doctor.id)
        .order_by(Lecture.lecture_date.desc(), Lecture.id.desc())
    ).all()
    return [lecture_out(lec) for lec in rows]


@router.post("")
def create_lecture(
    body: LectureIn,
    doctor: Doctor = Depends(current_doctor),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "اسم المحاضرة مطلوب")
    time_text = (body.lecture_time or "").strip() or None
    lec = Lecture(
        doctor_id=doctor.id,
        name=name,
        lecture_date=yemen_today(),
        lecture_time=time_text,
        code_secret=secrets.token_hex(32),
        is_running=False,
    )
    db.add(lec)
    db.commit()
    return lecture_out(lec)


@router.delete("/{lecture_id}")
def delete_lecture(
    lecture_id: int,
    doctor: Doctor = Depends(current_doctor),
    db: Session = Depends(get_db),
):
    lec = get_own_lecture(db, lecture_id, doctor)
    db.delete(lec)  # attendance and attempts are deleted with it (CASCADE)
    db.commit()
    return {"ok": True}


@router.post("/{lecture_id}/start")
def start_lecture(
    lecture_id: int,
    doctor: Doctor = Depends(current_doctor),
    db: Session = Depends(get_db),
):
    """Start, or restart after a stop. The attendance list is kept."""
    lec = get_own_lecture(db, lecture_id, doctor)
    lec.is_running = True
    lec.started_at = db.scalar(select(func.now()))
    lec.code_secret = secrets.token_hex(32)  # new code sequence on every start
    # Code numbers restart from 0, so old wrong-code counters must not carry over.
    db.execute(delete(CodeAttempt).where(CodeAttempt.lecture_id == lec.id))
    db.commit()
    return lecture_out(lec)


@router.post("/{lecture_id}/stop")
def stop_lecture(
    lecture_id: int,
    doctor: Doctor = Depends(current_doctor),
    db: Session = Depends(get_db),
):
    lec = get_own_lecture(db, lecture_id, doctor)
    lec.is_running = False
    db.commit()
    return lecture_out(lec)
