import os

from dotenv import load_dotenv

# Tests use their own database so they never touch your real data.
load_dotenv()
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["COOKIE_SECURE"] = "false"
# Tests always use the APU point, whatever campus is set in .env for demos.
os.environ["CAMPUS_LAT"] = "3.0550753"
os.environ["CAMPUS_LNG"] = "101.7005763"
os.environ["CAMPUS_RADIUS_M"] = "500"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def clean_db():
    with engine.begin() as conn:
        names = ", ".join(Base.metadata.tables)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def doctor_client(db):
    """A client already logged in as doctor 'dr'."""
    from app.models import Doctor
    from app.security import hash_password

    db.add(Doctor(username="dr", password_hash=hash_password("secret123")))
    db.commit()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "dr", "password": "secret123"})
    assert r.status_code == 200
    return c


@pytest.fixture
def other_doctor_client(db):
    """A second doctor, to check one doctor cannot touch another's data."""
    from app.models import Doctor
    from app.security import hash_password

    db.add(Doctor(username="other", password_hash=hash_password("secret123")))
    db.commit()
    c = TestClient(app)
    c.post("/api/auth/login", json={"username": "other", "password": "secret123"})
    return c
