# Student Attendance System

A web system for taking class attendance with a short code, in the style of APU's attendance system. Built as a trial for a university in Yemen.

The doctor starts a session and a 3-digit code appears on the screen. Students open one fixed link on their phones, enter their details and the code, and appear on the doctor's live list. The doctor can then edit the list and download it as a PDF.

The interface is Arabic and right-to-left.

## How it works

**Doctor**
- Logs in. Accounts are added manually by the admin (see below).
- Creates a lecture: the name and the major are required, the time is optional, and the date is set automatically (Yemen time, `Asia/Aden`).
- Starts the session. A random 3-digit code appears and changes every minute until the session stops.
- The session stops when the doctor presses Stop, or by itself 5 minutes after the last successful student registration (or 5 minutes after start if nobody registered).
- Starting a lecture stops any other running lecture.
- Sees the attendance list refresh every 5 seconds (name, student ID, major, status "حاضر").
- Can add a student by hand (name and ID; the major comes from the lecture; duplicates allowed), edit name, ID or major, delete a student, reopen old lectures, delete a lecture permanently, and download the list as a PDF named `<lecture name> <date>.pdf`.

**Student** (one fixed link)
1. Enters name and student ID. The major is not typed by the student: every student gets the lecture's major, and the doctor can edit it per student.
2. Enters the code and sees "تم التحضير".

**Rules enforced by the server**

| Case | Message |
|---|---|
| Student ID is not digits only (Arabic ٠-٩ and Persian ۰-۹ digits are converted) | الرقم الجامعي لازم يكون أرقام فقط |
| Wrong code | الكود غير صحيح، باقي لك X محاولات |
| 5 wrong tries on the current code (a new code gives new tries) | استنفدت المحاولات لهذا الكود |
| Already registered in this lecture | تم تسجيل حضورك مسبقاً |
| No running session | انتهى وقت التحضير |
| Location not allowed or not available on the phone | شغّل الموقع وحدّث الصفحة عشان تتحضّر |
| More than 500 m from campus | انت لست في الجامعة، لم يتم تحضيرك |

The previous code is still accepted for 15 seconds after it changes, to allow for slow connections.

**Campus location.** When the student submits the code, the page asks the phone for its location and the server checks it is within the campus radius. The location is only checked, never saved, and a location refusal does not use up a code try. The phone's location can be faked with spoofing apps, so this check stops casual cheating, not a determined student. Browsers only share location over HTTPS (or `localhost`).

The campus point is set with environment variables (defaults: APU, Kuala Lumpur, 500 m):

```
CAMPUS_LAT=3.0550753
CAMPUS_LNG=101.7005763
CAMPUS_RADIUS_M=500
```

Doctor login locks for 5 minutes after 5 wrong passwords. The doctor stays logged in until he logs out.

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy 2, PostgreSQL (psycopg 3)
- **Frontend:** plain HTML, CSS and JavaScript in `public/`. No framework, and no external CDNs.
- **PDF:** reportlab with arabic-reshaper and python-bidi, using the Noto Naskh Arabic font (SIL Open Font License, see `app/fonts/OFL.txt`).
- **Passwords:** scrypt (Python standard library). Login sessions are an HttpOnly cookie, and only a hash of the token is stored.
- **Hosting target:** Vercel, with the frontend and API in one project on one URL, and Postgres on Neon.

Nothing runs in the background. The current code and the auto-stop are calculated from the clock on each request, so the app works on serverless hosting.

## Project structure

```
app/
  main.py        FastAPI app (Vercel entrypoint)
  db.py          database connection
  models.py      tables
  auth.py        doctor login / logout
  lectures.py    lectures, start/stop, live screen, PDF download
  codes.py       3-digit code, 15 s grace, 5-minute auto-stop
  attend.py      student registration
  manage.py      doctor add / edit / delete students
  pdf.py         Arabic PDF
  security.py    password hashing, session tokens
  fonts/         Noto Naskh Arabic + license
public/          the 5 pages (index, code, login, lectures, lecture) + css/js
tests/           pytest suite
create_tables.py create the database tables
add_doctor.py    add a doctor or change a password
dev_server.py    local only: serves public/ and the API together
loadtest.py      simulate many students registering at once
```

## Run locally (Windows / PowerShell)

Requirements: Python 3.12+, Docker Desktop.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

Create a `.env` file in the project root. Never commit it; it is already in `.gitignore`.

```
POSTGRES_USER=attendance
POSTGRES_PASSWORD=<choose a password>
POSTGRES_DB=attendance
DATABASE_URL=postgresql+psycopg://attendance:<password>@localhost:5433/attendance
TEST_DATABASE_URL=postgresql+psycopg://attendance:<password>@localhost:5433/attendance_test
COOKIE_SECURE=false
```

`COOKIE_SECURE=false` is for local http only. Leave it unset in production (HTTPS).

Start the database, create the tables, and add a doctor:

```powershell
docker compose up -d
python create_tables.py
"CREATE DATABASE attendance_test;" | docker compose exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'
python add_doctor.py doctor1
```

Run the pages and the API together:

```powershell
uvicorn dev_server:app --reload
```

- Student: http://localhost:8000
- Doctor: http://localhost:8000/login.html
- API docs: http://localhost:8000/docs

## Admin tasks

- **Add a doctor, or change a password** (this also clears a login lock): `python add_doctor.py <username>`

## Tests

```powershell
python -m pytest -q
```

The tests use the separate `attendance_test` database, so they never touch real data.

Load test (fake students only; the test lecture is deleted afterwards):

```powershell
python loadtest.py http://localhost:8000 doctor1 --students 300
```

## API

All errors return `{"detail": "<Arabic message>"}`. Doctor endpoints return 401 when not logged in.

| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/login`, `/api/auth/logout` | doctor |
| GET, POST | `/api/lectures` | doctor |
| DELETE | `/api/lectures/{id}` | doctor |
| POST | `/api/lectures/{id}/start`, `/api/lectures/{id}/stop` | doctor |
| GET | `/api/lectures/{id}/live` | doctor (polled every 5 s) |
| GET | `/api/lectures/{id}/pdf` | doctor |
| POST | `/api/lectures/{id}/attendance` | doctor (add by hand) |
| PATCH, DELETE | `/api/attendance/{id}` | doctor (edit / delete) |
| POST | `/api/attend` | student (no login) |

Full request and response details are at `/docs` while the server runs.
