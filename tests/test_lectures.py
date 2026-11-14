from datetime import date

from sqlalchemy import select

from app import lectures
from app.models import Attendance, CodeAttempt, Lecture


def create(client, name="Networking", time=None):
    body = {"name": name}
    if time is not None:
        body["lecture_time"] = time
    return client.post("/api/lectures", json=body)


def test_create_lecture_sets_yemen_date(doctor_client, monkeypatch):
    monkeypatch.setattr(lectures, "yemen_today", lambda: date(2026, 11, 20))
    r = create(doctor_client, time="10:00")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Networking"
    assert data["lecture_date"] == "2026-11-20"
    assert data["lecture_time"] == "10:00"
    assert data["is_running"] is False


def test_time_is_optional(doctor_client):
    r = create(doctor_client)
    assert r.status_code == 200
    assert r.json()["lecture_time"] is None


def test_empty_name_rejected(doctor_client):
    assert create(doctor_client, name="   ").status_code == 422
    assert create(doctor_client, name="").status_code == 422


def test_yemen_today_uses_aden_timezone():
    assert lectures.YEMEN_TZ.key == "Asia/Aden"


def test_list_newest_first(doctor_client):
    create(doctor_client, name="A")
    create(doctor_client, name="B")
    names = [x["name"] for x in doctor_client.get("/api/lectures").json()]
    assert names == ["B", "A"]


def test_list_shows_only_own(doctor_client, other_doctor_client):
    create(doctor_client, name="Mine")
    create(other_doctor_client, name="Theirs")
    names = [x["name"] for x in doctor_client.get("/api/lectures").json()]
    assert names == ["Mine"]


def test_start_and_stop(doctor_client, db):
    lid = create(doctor_client).json()["id"]
    r = doctor_client.post(f"/api/lectures/{lid}/start")
    assert r.json()["is_running"] is True
    db.expire_all()
    assert db.get(Lecture, lid).started_at is not None
    r = doctor_client.post(f"/api/lectures/{lid}/stop")
    assert r.json()["is_running"] is False


def test_restart_keeps_list_and_clears_attempts(doctor_client, db):
    lid = create(doctor_client).json()["id"]
    doctor_client.post(f"/api/lectures/{lid}/start")
    db.add(Attendance(lecture_id=lid, name="Ali", student_id="1", major="CS"))
    db.add(CodeAttempt(lecture_id=lid, student_id="2", code_window=0, failures=3))
    db.commit()
    old_secret = db.get(Lecture, lid).code_secret
    doctor_client.post(f"/api/lectures/{lid}/stop")
    doctor_client.post(f"/api/lectures/{lid}/start")
    db.expire_all()
    assert db.scalars(select(Attendance)).all() != []
    assert db.scalars(select(CodeAttempt)).all() == []
    assert db.get(Lecture, lid).code_secret != old_secret


def test_delete_removes_lecture_and_attendance(doctor_client, db):
    lid = create(doctor_client).json()["id"]
    db.add(Attendance(lecture_id=lid, name="Ali", student_id="1", major="CS"))
    db.commit()
    r = doctor_client.delete(f"/api/lectures/{lid}")
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Lecture, lid) is None
    assert db.scalars(select(Attendance)).all() == []


def test_other_doctor_gets_404(doctor_client, other_doctor_client, db):
    lid = create(doctor_client).json()["id"]
    for method, path in [
        ("post", f"/api/lectures/{lid}/start"),
        ("post", f"/api/lectures/{lid}/stop"),
        ("delete", f"/api/lectures/{lid}"),
    ]:
        r = getattr(other_doctor_client, method)(path)
        assert r.status_code == 404
        assert r.json()["detail"] == "المحاضرة غير موجودة"
    db.expire_all()
    assert db.get(Lecture, lid) is not None


def test_missing_lecture_404(doctor_client):
    assert doctor_client.post("/api/lectures/9999/start").status_code == 404


def test_logged_out_gets_401(client):
    assert client.get("/api/lectures").status_code == 401
    assert client.post("/api/lectures", json={"name": "x"}).status_code == 401
    assert client.post("/api/lectures/1/start").status_code == 401
    assert client.delete("/api/lectures/1").status_code == 401


def test_empty_name_message_is_arabic_text(doctor_client):
    r = create(doctor_client, name="")
    assert r.json()["detail"] == "اسم المحاضرة مطلوب"
