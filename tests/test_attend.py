from datetime import timedelta

from sqlalchemy import func, select

from app.codes import accepted_codes, code_for, code_window
from app.models import Attendance, Lecture


def start_lecture(doctor_client, name="Net"):
    lid = doctor_client.post("/api/lectures", json={"name": name, "major": "Computer Science"}).json()["id"]
    doctor_client.post(f"/api/lectures/{lid}/start")
    return lid


def good_code(db, lid):
    db.expire_all()
    lec = db.get(Lecture, lid)
    now = db.scalar(select(func.now()))
    return code_for(lec.code_secret, code_window(lec, now))


def wrong_code(db, lid):
    db.expire_all()
    lec = db.get(Lecture, lid)
    now = db.scalar(select(func.now()))
    ok = accepted_codes(lec, now)
    return next(f"{i:03d}" for i in range(1000) if f"{i:03d}" not in ok)


CAMPUS = (3.0550753, 101.7005763)


def send(client, code, sid="2023001", name="أحمد علي", loc=CAMPUS, same_device=False):
    # Each call is a new phone unless same_device=True (the device lock
    # is tested separately below).
    if not same_device:
        client.cookies.clear()
    return client.post(
        "/api/attend",
        json={"name": name, "student_id": sid, "code": code,
              **({"lat": loc[0], "lng": loc[1]} if loc else {})},
    )


def test_correct_code_registers(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    r = send(client, good_code(db, lid))
    assert r.status_code == 200
    assert r.json() == {"message": "تم التحضير"}
    live = doctor_client.get(f"/api/lectures/{lid}/live").json()
    assert [(a["name"], a["student_id"], a["major"], a["status"]) for a in live["attendance"]] == [
        ("أحمد علي", "2023001", "Computer Science", "حاضر")
    ]


def test_success_extends_auto_stop(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    send(client, good_code(db, lid))
    db.expire_all()
    assert db.get(Lecture, lid).last_success_at is not None


def test_wrong_code_not_saved_and_counts_down(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    bad = wrong_code(db, lid)
    msgs = [send(client, bad).json()["detail"] for _ in range(4)]
    assert msgs == [
        "الكود غير صحيح، باقي لك 4 محاولات",
        "الكود غير صحيح، باقي لك 3 محاولات",
        "الكود غير صحيح، باقي لك 2 محاولات",
        "الكود غير صحيح، باقي لك 1 محاولات",
    ]
    assert db.scalars(select(Attendance)).all() == []


def test_fifth_wrong_then_blocked_even_with_right_code(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    bad = wrong_code(db, lid)
    for _ in range(4):
        send(client, bad)
    r = send(client, bad)
    assert r.status_code == 429 and r.json()["detail"] == "استنفدت المحاولات لهذا الكود"
    r = send(client, good_code(db, lid))
    assert r.status_code == 429
    assert db.scalars(select(Attendance)).all() == []


def test_tries_are_per_student_id(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    bad = wrong_code(db, lid)
    for _ in range(5):
        send(client, bad, sid="111")
    assert send(client, good_code(db, lid), sid="222").status_code == 200


def test_new_code_gives_new_tries(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    bad = wrong_code(db, lid)
    for _ in range(5):
        send(client, bad)
    # move the session 70 seconds into the past -> we are on the next code
    lec = db.get(Lecture, lid)
    lec.started_at = lec.started_at - timedelta(seconds=70)
    db.commit()
    assert send(client, good_code(db, lid)).status_code == 200


def test_previous_code_accepted_within_15_seconds(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    lec = db.get(Lecture, lid)
    lec.started_at = lec.started_at - timedelta(seconds=65)  # 5s into 2nd code
    db.commit()
    prev = code_for(lec.code_secret, 0)
    assert send(client, prev).status_code == 200


def test_previous_code_rejected_after_15_seconds(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    lec = db.get(Lecture, lid)
    lec.started_at = lec.started_at - timedelta(seconds=80)  # 20s into 2nd code
    db.commit()
    prev = code_for(lec.code_secret, 0)
    cur = code_for(lec.code_secret, 1)
    if prev != cur:
        assert send(client, prev).status_code == 400


def test_register_only_once_per_lecture(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    assert send(client, good_code(db, lid)).status_code == 200
    r = send(client, good_code(db, lid))
    assert r.status_code == 409 and r.json()["detail"] == "تم تسجيل حضورك مسبقاً"
    assert len(db.scalars(select(Attendance)).all()) == 1


def test_same_student_can_attend_next_lecture(doctor_client, client, db):
    lid1 = start_lecture(doctor_client, "L1")
    send(client, good_code(db, lid1))
    lid2 = start_lecture(doctor_client, "L2")
    assert send(client, good_code(db, lid2)).status_code == 200


def test_student_id_digits_only(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    for sid in ["12a3", "TP123", "12-3", " "]:
        r = send(client, good_code(db, lid), sid=sid)
        assert r.status_code == 422
        assert r.json()["detail"] == "الرقم الجامعي لازم يكون أرقام فقط"


def test_name_required(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    assert send(client, good_code(db, lid), name="  ").json()["detail"] == "الاسم مطلوب"


def test_major_comes_from_lecture(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    # even if an old page still sends a major, the lecture's major is used
    r = client.post("/api/attend", json={"name": "a", "student_id": "5",
                                         "major": "Other", "code": good_code(db, lid),
                                         "lat": CAMPUS[0], "lng": CAMPUS[1]})
    assert r.status_code == 200
    db.expire_all()
    assert db.scalars(select(Attendance)).one().major == "Computer Science"


def test_no_running_lecture(client):
    r = send(client, "123")
    assert r.status_code == 410 and r.json()["detail"] == "انتهى وقت التحضير"


def test_stopped_lecture_refuses(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    code = good_code(db, lid)
    doctor_client.post(f"/api/lectures/{lid}/stop")
    assert send(client, code).status_code == 410


def test_auto_stopped_lecture_refuses(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    lec = db.get(Lecture, lid)
    lec.started_at = lec.started_at - timedelta(minutes=6)
    db.commit()
    assert send(client, "000").status_code == 410
    db.expire_all()
    assert db.get(Lecture, lid).is_running is False


def test_starting_new_lecture_stops_old(doctor_client, client, db):
    lid1 = start_lecture(doctor_client, "Old")
    lid2 = start_lecture(doctor_client, "New")
    lectures = {x["id"]: x["is_running"] for x in doctor_client.get("/api/lectures").json()}
    assert lectures == {lid1: False, lid2: True}
    send(client, good_code(db, lid2))
    db.expire_all()
    assert db.scalars(select(Attendance)).one().lecture_id == lid2


def test_arabic_and_persian_digits_converted(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    to_ar = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
    code_ar = good_code(db, lid).translate(to_ar)
    assert send(client, code_ar, sid="٢٠٢٣٠٠١").status_code == 200
    db.expire_all()
    assert db.scalars(select(Attendance)).one().student_id == "2023001"
    to_fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    code_fa = good_code(db, lid).translate(to_fa)
    assert send(client, code_fa, sid="۲۰۲۳۰۰۲").status_code == 200


def test_arabic_duplicate_detected(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    send(client, good_code(db, lid), sid="2023001")
    r = send(client, good_code(db, lid), sid="٢٠٢٣٠٠١")
    assert r.status_code == 409


# ---- campus location ----

def test_inside_500m_accepted(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    # about 300 m north of campus
    assert send(client, good_code(db, lid), loc=(3.0577753, 101.7005763)).status_code == 200


def test_outside_500m_refused(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    # about 700 m north of campus
    r = send(client, good_code(db, lid), loc=(3.0613753, 101.7005763))
    assert r.status_code == 403
    assert r.json()["detail"] == "انت لست في الجامعة، لم يتم تحضيرك"
    assert db.scalars(select(Attendance)).all() == []


def test_far_away_refused(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    r = send(client, good_code(db, lid), loc=(15.3694, 44.1910))  # Sana'a
    assert r.json()["detail"] == "انت لست في الجامعة، لم يتم تحضيرك"


def test_no_location_refused(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    r = send(client, good_code(db, lid), loc=None)
    assert r.status_code == 428
    assert r.json()["detail"] == "شغّل الموقع وحدّث الصفحة عشان تتحضّر"


def test_invalid_location_refused(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    r = send(client, good_code(db, lid), loc=(999, 101.7))
    assert r.json()["detail"] == "شغّل الموقع وحدّث الصفحة عشان تتحضّر"


def test_location_refusal_does_not_use_a_try(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    bad = wrong_code(db, lid)
    for _ in range(5):
        send(client, bad, loc=(15.3694, 44.1910))  # far away: refused before the code
    assert send(client, good_code(db, lid)).status_code == 200


def test_distance_function():
    from app.location import distance_m
    d = distance_m(3.0550753, 101.7005763, 3.0595753, 101.7005763)
    assert 495 < d < 505  # 0.0045 degrees of latitude is about 500 m


# ---- device lock (15 minutes, same lecture) ----

LOCK_MSG = "تم تحضير طالب من هذا الجهاز، حاول بعد ١٥ دقيقة"


def test_device_cookie_set_on_success(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    r = send(client, good_code(db, lid), sid="1")
    assert r.status_code == 200
    set_cookie = r.headers["set-cookie"].lower()
    assert "device=" in set_cookie and "httponly" in set_cookie
    db.expire_all()
    row = db.scalars(select(Attendance)).one()
    assert row.device_hash and row.device_hash != client.cookies.get("device")  # only the hash is stored


def test_same_device_other_student_same_lecture_refused(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    assert send(client, good_code(db, lid), sid="1").status_code == 200
    r = send(client, good_code(db, lid), sid="2", same_device=True)
    assert r.status_code == 429 and r.json()["detail"] == LOCK_MSG
    assert len(db.scalars(select(Attendance)).all()) == 1


def test_same_device_same_student_gets_already_registered(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    send(client, good_code(db, lid), sid="1")
    r = send(client, good_code(db, lid), sid="1", same_device=True)
    assert r.json()["detail"] == "تم تسجيل حضورك مسبقاً"


def test_same_device_allowed_after_15_minutes(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    send(client, good_code(db, lid), sid="1")
    row = db.scalars(select(Attendance)).one()
    row.created_at = row.created_at - timedelta(minutes=15, seconds=1)
    db.commit()
    assert send(client, good_code(db, lid), sid="2", same_device=True).status_code == 200


def test_same_device_other_lecture_allowed(doctor_client, client, db):
    lid1 = start_lecture(doctor_client, "L1")
    send(client, good_code(db, lid1), sid="1")
    lid2 = start_lecture(doctor_client, "L2")
    assert send(client, good_code(db, lid2), sid="2", same_device=True).status_code == 200


def test_other_device_not_affected(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    send(client, good_code(db, lid), sid="1")
    assert send(client, good_code(db, lid), sid="2").status_code == 200  # new phone


def test_device_lock_does_not_use_a_try(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    send(client, good_code(db, lid), sid="1")
    bad = wrong_code(db, lid)
    for _ in range(5):
        r = send(client, bad, sid="2", same_device=True)
        assert r.json()["detail"] == LOCK_MSG
    assert send(client, good_code(db, lid), sid="2").status_code == 200  # from another phone


def test_doctor_deleting_row_unlocks_device(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    send(client, good_code(db, lid), sid="1")
    rid = db.scalars(select(Attendance)).one().id
    doctor_client.delete(f"/api/attendance/{rid}")
    assert send(client, good_code(db, lid), sid="2", same_device=True).status_code == 200


def test_doctor_manual_add_not_affected(doctor_client, client, db):
    lid = start_lecture(doctor_client)
    send(client, good_code(db, lid), sid="1")
    r = doctor_client.post(f"/api/lectures/{lid}/attendance", json={"name": "x", "student_id": "2"})
    assert r.status_code == 200


# ---- online lectures (no location) ----

def start_online(doctor_client, name="Online"):
    lid = doctor_client.post("/api/lectures", json={"name": name, "major": "CS", "is_online": True}).json()["id"]
    doctor_client.post(f"/api/lectures/{lid}/start")
    return lid


def test_online_lecture_needs_no_location(doctor_client, client, db):
    lid = start_online(doctor_client)
    assert send(client, good_code(db, lid), loc=None).status_code == 200


def test_online_lecture_accepts_far_location(doctor_client, client, db):
    lid = start_online(doctor_client)
    assert send(client, good_code(db, lid), loc=(15.3694, 44.1910)).status_code == 200


def test_online_lecture_keeps_other_rules(doctor_client, client, db):
    lid = start_online(doctor_client)
    bad = wrong_code(db, lid)
    assert send(client, bad, loc=None).json()["detail"] == "الكود غير صحيح، باقي لك 4 محاولات"
    send(client, good_code(db, lid), sid="1", loc=None)
    r = send(client, good_code(db, lid), sid="2", loc=None, same_device=True)
    assert r.json()["detail"] == LOCK_MSG


def test_in_person_is_default(doctor_client):
    r = doctor_client.post("/api/lectures", json={"name": "x", "major": "CS"})
    assert r.json()["is_online"] is False
