from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.codes import (
    accepted_codes,
    code_for,
    code_window,
    current_code,
    refresh_running,
)
from app.models import Attendance, Lecture

T0 = datetime(2026, 11, 20, 8, 0, 0, tzinfo=timezone.utc)


def lec(**kw):
    base = dict(code_secret="s" * 64, is_running=True, started_at=T0, last_success_at=None)
    base.update(kw)
    return Lecture(**base)


def at(seconds):
    return T0 + timedelta(seconds=seconds)


# ---- code ----

def test_code_is_three_digits():
    for w in range(200):
        c = code_for("abc", w)
        assert len(c) == 3 and c.isdigit()


def test_code_changes_every_minute():
    lecture = lec()
    assert code_window(lecture, at(0)) == 0
    assert code_window(lecture, at(59)) == 0
    assert code_window(lecture, at(60)) == 1
    assert current_code(lecture, at(10)) == current_code(lecture, at(59))
    # over many minutes the code is not stuck on one value
    codes = {current_code(lecture, at(60 * m)) for m in range(20)}
    assert len(codes) > 10


def test_different_secret_different_codes():
    a = [code_for("a", w) for w in range(20)]
    b = [code_for("b", w) for w in range(20)]
    assert a != b


def test_grace_15_seconds_for_previous_code():
    lecture = lec()
    prev = code_for(lecture.code_secret, 0)
    cur = code_for(lecture.code_secret, 1)
    assert prev in accepted_codes(lecture, at(60 + 14))  # 14s after change: ok
    assert prev not in accepted_codes(lecture, at(60 + 15)) or prev == cur  # 15s: no
    assert cur in accepted_codes(lecture, at(60 + 15))


def test_first_minute_only_one_code():
    assert len(accepted_codes(lec(), at(5))) == 1


# ---- auto-stop ----

def test_auto_stop_5_minutes_after_start_if_nobody_registered():
    lecture = lec()
    assert refresh_running(lecture, at(299)) is True
    assert refresh_running(lecture, at(300)) is False
    assert lecture.is_running is False


def test_auto_stop_counts_from_last_success():
    lecture = lec(last_success_at=at(240))
    assert refresh_running(lecture, at(500)) is True   # 4:20 after last success
    assert refresh_running(lecture, at(540)) is False  # 5:00 after last success


def test_stopped_stays_stopped():
    lecture = lec(is_running=False)
    assert refresh_running(lecture, at(10)) is False


# ---- /live endpoint ----

def make_running(doctor_client, db):
    lid = doctor_client.post("/api/lectures", json={"name": "Net"}).json()["id"]
    doctor_client.post(f"/api/lectures/{lid}/start")
    return lid


def test_live_shows_code_and_list(doctor_client, db):
    lid = make_running(doctor_client, db)
    db.add(Attendance(lecture_id=lid, name="علي", student_id="123", major="CS"))
    db.commit()
    data = doctor_client.get(f"/api/lectures/{lid}/live").json()
    assert data["is_running"] is True
    assert len(data["code"]) == 3
    assert data["attendance"] == [
        {"id": data["attendance"][0]["id"], "name": "علي",
         "student_id": "123", "major": "CS", "status": "حاضر"}
    ]


def test_live_code_matches_server_calculation(doctor_client, db):
    lid = make_running(doctor_client, db)
    data = doctor_client.get(f"/api/lectures/{lid}/live").json()
    db.expire_all()
    lecture = db.get(Lecture, lid)
    now = db.scalar(select(func.now()))
    assert data["code"] in accepted_codes(lecture, now)


def test_live_no_code_when_stopped(doctor_client, db):
    lid = make_running(doctor_client, db)
    doctor_client.post(f"/api/lectures/{lid}/stop")
    data = doctor_client.get(f"/api/lectures/{lid}/live").json()
    assert data["is_running"] is False
    assert data["code"] is None


def test_live_auto_stops_after_5_minutes(doctor_client, db):
    lid = make_running(doctor_client, db)
    lecture = db.get(Lecture, lid)
    lecture.started_at = lecture.started_at - timedelta(minutes=5, seconds=1)
    db.commit()
    data = doctor_client.get(f"/api/lectures/{lid}/live").json()
    assert data["is_running"] is False and data["code"] is None
    # and the list of lectures shows it stopped too
    assert doctor_client.get("/api/lectures").json()[0]["is_running"] is False


def test_restart_after_auto_stop(doctor_client, db):
    lid = make_running(doctor_client, db)
    lecture = db.get(Lecture, lid)
    lecture.started_at = lecture.started_at - timedelta(minutes=10)
    db.commit()
    doctor_client.get(f"/api/lectures/{lid}/live")
    doctor_client.post(f"/api/lectures/{lid}/start")
    assert doctor_client.get(f"/api/lectures/{lid}/live").json()["is_running"] is True


def test_live_other_doctor_404(doctor_client, other_doctor_client, db):
    lid = make_running(doctor_client, db)
    assert other_doctor_client.get(f"/api/lectures/{lid}/live").status_code == 404


def test_live_logged_out_401(client):
    assert client.get("/api/lectures/1/live").status_code == 401
