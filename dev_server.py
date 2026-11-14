"""Local testing only: serves the pages in public/ and the API together,
the same way Vercel does online.

    uvicorn dev_server:app --reload

Then open http://localhost:8000 (student) or http://localhost:8000/login.html (doctor).
Vercel does not use this file; it serves public/ by itself.
"""

from fastapi.staticfiles import StaticFiles

from app.main import app

app.mount("/", StaticFiles(directory="public", html=True), name="public")
