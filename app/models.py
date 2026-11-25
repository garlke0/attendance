from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # Login lockout: 5 wrong passwords -> locked for 5 minutes
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginSession(Base):
    """Doctor stays logged in until logout. The cookie holds a random token;
    only its SHA-256 hash is stored here."""

    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctors.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Lecture(Base):
    __tablename__ = "lectures"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctors.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))
    lecture_date: Mapped[date] = mapped_column(Date)  # set automatically, Yemen time
    lecture_time: Mapped[str | None] = mapped_column(String(20))  # optional
    major: Mapped[str] = mapped_column(String(200))  # set by the doctor
    # Secret used to generate the 3-digit code for each minute
    code_secret: Mapped[str] = mapped_column(String(64))
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    # When the session was (re)started; the code changes every minute from here
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Last successful student registration (auto-stop after 5 minutes)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(primary_key=True)
    lecture_id: Mapped[int] = mapped_column(
        ForeignKey("lectures.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    student_id: Mapped[str] = mapped_column(String(50))  # digits only
    major: Mapped[str] = mapped_column(String(200))
    # True when the doctor added the student by hand
    added_by_doctor: Mapped[bool] = mapped_column(Boolean, default=False)
    # SHA-256 of the browser's device cookie (empty for rows added by the doctor)
    device_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CodeAttempt(Base):
    """Wrong-code counter: 5 tries per student ID, per lecture, per code."""

    __tablename__ = "code_attempts"

    lecture_id: Mapped[int] = mapped_column(
        ForeignKey("lectures.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    # Which code (minute number since the session started)
    code_window: Mapped[int] = mapped_column(Integer, primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
