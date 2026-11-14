import os

from dotenv import load_dotenv

# Tests use their own database so they never touch your real data.
load_dotenv()
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["COOKIE_SECURE"] = "false"

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
