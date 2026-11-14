"""Doctor edits the attendance list: add by hand, edit, delete.

Works on running, stopped and old lectures. Adding by hand does not extend
the 5-minute auto-stop, and is allowed even if the student ID is already
in the list.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.attend import MSG_DIGITS, MSG_MAJOR, MSG_NAME, normalize_digits
from app.auth import current_doctor
from app.db import get_db
from app.lectures import STATUS_PRESENT, get_own_lecture
from app.models import Attendance, Doctor, Lecture

router = APIRouter(prefix="/api")

MSG_ROW_NOT_FOUND = "الطالب غير موجود في القائمة"


def clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(422, MSG_NAME)
    return value


def clean_student_id(value: str) -> str:
    value = normalize_digits(value.strip())
    if not value or not (value.isascii() and value.isdigit()):
        raise HTTPException(422, MSG_DIGITS)
    return value


def clean_major(value: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(422, MSG_MAJOR)
    return value


def row_out(a: Attendance) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "student_id": a.student_id,
        "major": a.major,
        "status": STATUS_PRESENT,
    }


def get_own_row(db: Session, row_id: int, doctor: Doctor) -> Attendance:
    row = db.get(Attendance, row_id)
    if row is None:
        raise HTTPException(404, MSG_ROW_NOT_FOUND)
    lec = db.get(Lecture, row.lecture_id)
    if lec is None or lec.doctor_id != doctor.id:
        raise HTTPException(404, MSG_ROW_NOT_FOUND)
    return row


class AddIn(BaseModel):
    name: str = Field(max_length=200)
    student_id: str = Field(max_length=50)
    major: str = Field(max_length=200)


class EditIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    student_id: str | None = Field(default=None, max_length=50)
    major: str | None = Field(default=None, max_length=200)


@router.post("/lectures/{lecture_id}/attendance")
def add_student(
    lecture_id: int,
    body: AddIn,
    doctor: Doctor = Depends(current_doctor),
    db: Session = Depends(get_db),
):
    lec = get_own_lecture(db, lecture_id, doctor)
    row = Attendance(
        lecture_id=lec.id,
        name=clean_name(body.name),
        student_id=clean_student_id(body.student_id),
        major=clean_major(body.major),
        added_by_doctor=True,
    )
    db.add(row)
    db.commit()
    return row_out(row)


@router.patch("/attendance/{row_id}")
def edit_student(
    row_id: int,
    body: EditIn,
    doctor: Doctor = Depends(current_doctor),
    db: Session = Depends(get_db),
):
    row = get_own_row(db, row_id, doctor)
    if body.name is not None:
        row.name = clean_name(body.name)
    if body.student_id is not None:
        row.student_id = clean_student_id(body.student_id)
    if body.major is not None:
        row.major = clean_major(body.major)
    db.commit()
    return row_out(row)


@router.delete("/attendance/{row_id}")
def delete_student(
    row_id: int,
    doctor: Doctor = Depends(current_doctor),
    db: Session = Depends(get_db),
):
    row = get_own_row(db, row_id, doctor)
    db.delete(row)
    db.commit()
    return {"ok": True}
