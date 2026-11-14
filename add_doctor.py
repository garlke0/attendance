"""Add a doctor, or change an existing doctor's password.

Usage:  python add_doctor.py <username>
The password is typed hidden (not shown on screen, not saved in history).
Changing the password also clears any login lockout.
"""

import sys
from getpass import getpass

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Doctor
from app.security import hash_password


def main():
    if len(sys.argv) != 2:
        print("Usage: python add_doctor.py <username>")
        sys.exit(1)
    username = sys.argv[1].strip()

    password = getpass("Password: ")
    if password != getpass("Repeat password: "):
        print("Passwords do not match. Nothing changed.")
        sys.exit(1)

    with SessionLocal() as db:
        doctor = db.scalars(select(Doctor).where(Doctor.username == username)).first()
        if doctor:
            doctor.password_hash = hash_password(password)
            doctor.failed_logins = 0
            doctor.locked_until = None
            action = "Password changed for"
        else:
            db.add(Doctor(username=username, password_hash=hash_password(password)))
            action = "Added doctor"
        db.commit()
    print(f"{action}: {username}")


if __name__ == "__main__":
    main()
