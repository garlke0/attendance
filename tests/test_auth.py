from datetime import timedelta

from fastapi import Depends
from sqlalchemy import func, select

from app.auth import current_doctor
from app.main import app
from app.models import Doctor, LoginSession
from app.security import hash_password


# A test-only route to check that current_doctor protects endpoints.
@app.get("/api/_test/me")
def _me(doctor: Doctor = Depends(current_doctor)):
    return {"username": doctor.username}


def make_doctor(db, username="dr", password="secret123"):
    db.add(Doctor(username=username, password_hash=hash_password(password)))
    db.commit()


def login(client, username="dr", password="secret123"):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def test_login_success_sets_cookie(client, db):
    make_doctor(db)
    r = login(client)
    assert r.status_code == 200
    assert "session" in r.cookies
    assert "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/api/_test/me").json() == {"username": "dr"}


def test_wrong_password(client, db):
    make_doctor(db)
    r = login(client, password="nope")
    assert r.status_code == 401
    assert r.json()["detail"] == "اسم المستخدم أو كلمة السر غير صحيحة"


def test_unknown_user_same_message(client, db):
    r = login(client, username="ghost")
    assert r.status_code == 401
    assert r.json()["detail"] == "اسم المستخدم أو كلمة السر غير صحيحة"


def test_not_logged_in(client):
    r = client.get("/api/_test/me")
    assert r.status_code == 401


def test_bad_cookie(client):
    client.cookies.set("session", "fake")
    assert client.get("/api/_test/me").status_code == 401


def test_four_wrong_then_correct_works(client, db):
    make_doctor(db)
    for _ in range(4):
        assert login(client, password="x").status_code == 401
    assert login(client).status_code == 200
    # counter reset after success
    db.expire_all()
    assert db.scalars(select(Doctor)).one().failed_logins == 0


def test_fifth_wrong_locks_5_minutes(client, db):
    make_doctor(db)
    for _ in range(4):
        login(client, password="x")
    r = login(client, password="x")
    assert r.status_code == 429
    assert "5" in r.json()["detail"]
    # Even the correct password is refused while locked
    r = login(client)
    assert r.status_code == 429


def test_lock_expires(client, db):
    make_doctor(db)
    for _ in range(5):
        login(client, password="x")
    doctor = db.scalars(select(Doctor)).one()
    doctor.locked_until = db.scalar(select(func.now())) - timedelta(seconds=1)
    db.commit()
    assert login(client).status_code == 200


def test_logout_ends_session(client, db):
    make_doctor(db)
    login(client)
    assert client.get("/api/_test/me").status_code == 200
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert client.get("/api/_test/me").status_code == 401
    db.expire_all()
    assert db.scalars(select(LoginSession)).all() == []


def test_old_cookie_useless_after_logout(client, db):
    make_doctor(db)
    login(client)
    token = client.cookies.get("session")
    client.post("/api/auth/logout")
    client.cookies.set("session", token)
    assert client.get("/api/_test/me").status_code == 401


def test_logout_when_not_logged_in(client):
    assert client.post("/api/auth/logout").status_code == 200


def test_password_stored_hashed(db):
    make_doctor(db, password="secret123")
    stored = db.scalars(select(Doctor)).one().password_hash
    assert "secret123" not in stored
    assert stored.startswith("scrypt$")
