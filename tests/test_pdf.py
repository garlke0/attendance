from urllib.parse import quote

from app.pdf import content_disposition, pdf_filename


def setup_lecture(c, name="شبكات الحاسوب", time=None):
    body = {"name": name}
    if time:
        body["lecture_time"] = time
    lid = c.post("/api/lectures", json=body).json()["id"]
    c.post(f"/api/lectures/{lid}/attendance",
           json={"name": "أحمد علي", "student_id": "2023001", "major": "علوم الحاسوب"})
    c.post(f"/api/lectures/{lid}/attendance",
           json={"name": "Sara Ahmed", "student_id": "2023002", "major": "Computer Science"})
    return lid


def test_pdf_download(doctor_client):
    lid = setup_lecture(doctor_client, time="10:00")
    r = doctor_client.get(f"/api/lectures/{lid}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    date = doctor_client.get("/api/lectures").json()[0]["lecture_date"]
    expected = quote(f"شبكات الحاسوب {date}.pdf")
    assert f"filename*=UTF-8''{expected}" in r.headers["content-disposition"]


def test_pdf_empty_list_and_no_time(doctor_client):
    lid = doctor_client.post("/api/lectures", json={"name": "Empty"}).json()["id"]
    r = doctor_client.get(f"/api/lectures/{lid}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_pdf_many_rows(doctor_client):
    lid = doctor_client.post("/api/lectures", json={"name": "Big"}).json()["id"]
    for i in range(300):
        doctor_client.post(f"/api/lectures/{lid}/attendance",
                           json={"name": f"طالب {i}", "student_id": str(i), "major": "CS"})
    r = doctor_client.get(f"/api/lectures/{lid}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_pdf_other_doctor_404(doctor_client, other_doctor_client):
    lid = setup_lecture(doctor_client)
    assert other_doctor_client.get(f"/api/lectures/{lid}/pdf").status_code == 404


def test_pdf_logged_out_401(client):
    assert client.get("/api/lectures/1/pdf").status_code == 401


def test_filename_removes_forbidden_chars():
    assert pdf_filename('Net/Sec: "1"?', "2026-11-20") == "Net Sec 1 2026-11-20.pdf"
    assert pdf_filename("///", "2026-11-20") == "attendance 2026-11-20.pdf"


def test_content_disposition_ascii_fallback():
    h = content_disposition("شبكات 2026-11-20.pdf")
    assert 'filename="attendance.pdf"' in h or 'filename="2026-11-20.pdf"' in h
    assert "filename*=UTF-8''" in h
