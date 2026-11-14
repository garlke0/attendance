from datetime import timedelta

from sqlalchemy import select

from app.models import Attendance, Lecture


def new_lecture(c, name="Net"):
    return c.post("/api/lectures", json={"name": name, "major": "IT"}).json()["id"]


def add(c, lid, name="سارة", sid="2023005"):
    return c.post(
        f"/api/lectures/{lid}/attendance",
        json={"name": name, "student_id": sid},
    )


def live_list(c, lid):
    return c.get(f"/api/lectures/{lid}/live").json()["attendance"]


def test_add_by_hand(doctor_client, db):
    lid = new_lecture(doctor_client)
    r = add(doctor_client, lid)
    assert r.status_code == 200
    assert r.json()["status"] == "حاضر"
    assert [(a["name"], a["student_id"]) for a in live_list(doctor_client, lid)] == [
        ("سارة", "2023005")
    ]
    db.expire_all()
    assert db.scalars(select(Attendance)).one().added_by_doctor is True


def test_add_works_on_stopped_and_old_lecture(doctor_client):
    lid = new_lecture(doctor_client)  # never started
    assert add(doctor_client, lid).status_code == 200


def test_add_allows_duplicate_id(doctor_client):
    lid = new_lecture(doctor_client)
    add(doctor_client, lid, sid="1")
    assert add(doctor_client, lid, sid="1").status_code == 200
    assert len(live_list(doctor_client, lid)) == 2


def test_add_does_not_extend_auto_stop(doctor_client, db):
    lid = new_lecture(doctor_client)
    doctor_client.post(f"/api/lectures/{lid}/start")
    add(doctor_client, lid)
    db.expire_all()
    assert db.get(Lecture, lid).last_success_at is None


def test_add_validation(doctor_client):
    lid = new_lecture(doctor_client)
    assert add(doctor_client, lid, sid="12a").json()["detail"] == "الرقم الجامعي لازم يكون أرقام فقط"
    assert add(doctor_client, lid, name=" ").json()["detail"] == "الاسم مطلوب"
    assert add(doctor_client, lid, sid="٢٠٢٣").json()["student_id"] == "2023"


def test_edit_all_fields(doctor_client):
    lid = new_lecture(doctor_client)
    rid = add(doctor_client, lid).json()["id"]
    r = doctor_client.patch(
        f"/api/attendance/{rid}",
        json={"name": "سارة محمد", "student_id": "٩٩", "major": "CS"},
    )
    assert r.status_code == 200
    row = live_list(doctor_client, lid)[0]
    assert (row["name"], row["student_id"], row["major"]) == ("سارة محمد", "99", "CS")


def test_edit_one_field_only(doctor_client):
    lid = new_lecture(doctor_client)
    rid = add(doctor_client, lid).json()["id"]
    doctor_client.patch(f"/api/attendance/{rid}", json={"major": "SE"})
    row = live_list(doctor_client, lid)[0]
    assert (row["name"], row["student_id"], row["major"]) == ("سارة", "2023005", "SE")


def test_edit_validation(doctor_client):
    lid = new_lecture(doctor_client)
    rid = add(doctor_client, lid).json()["id"]
    r = doctor_client.patch(f"/api/attendance/{rid}", json={"student_id": "abc"})
    assert r.status_code == 422
    assert live_list(doctor_client, lid)[0]["student_id"] == "2023005"


def test_delete_row(doctor_client):
    lid = new_lecture(doctor_client)
    rid = add(doctor_client, lid).json()["id"]
    assert doctor_client.delete(f"/api/attendance/{rid}").status_code == 200
    assert live_list(doctor_client, lid) == []


def test_deleted_student_can_register_again(doctor_client, client, db):
    from tests.test_attend import good_code, send

    lid = new_lecture(doctor_client)
    doctor_client.post(f"/api/lectures/{lid}/start")
    send(client, good_code(db, lid), sid="77")
    rid = live_list(doctor_client, lid)[0]["id"]
    doctor_client.delete(f"/api/attendance/{rid}")
    assert send(client, good_code(db, lid), sid="77").status_code == 200


def test_other_doctor_cannot_touch(doctor_client, other_doctor_client):
    lid = new_lecture(doctor_client)
    rid = add(doctor_client, lid).json()["id"]
    assert add(other_doctor_client, lid).status_code == 404
    r = other_doctor_client.patch(f"/api/attendance/{rid}", json={"name": "x"})
    assert r.status_code == 404
    assert other_doctor_client.delete(f"/api/attendance/{rid}").status_code == 404
    assert live_list(doctor_client, lid)[0]["name"] == "سارة"


def test_missing_row_404(doctor_client):
    r = doctor_client.delete("/api/attendance/9999")
    assert r.status_code == 404 and r.json()["detail"] == "الطالب غير موجود في القائمة"


def test_logged_out_401(client):
    assert client.post("/api/lectures/1/attendance", json={"name": "a", "student_id": "1", "major": "m"}).status_code == 401
    assert client.patch("/api/attendance/1", json={"name": "a"}).status_code == 401
    assert client.delete("/api/attendance/1").status_code == 401


def test_add_by_hand_gets_lecture_major(doctor_client):
    lid = new_lecture(doctor_client)
    assert add(doctor_client, lid).json()["major"] == "IT"


def test_edit_major_empty_rejected(doctor_client):
    lid = new_lecture(doctor_client)
    rid = add(doctor_client, lid).json()["id"]
    r = doctor_client.patch(f"/api/attendance/{rid}", json={"major": " "})
    assert r.json()["detail"] == "التخصص مطلوب"
