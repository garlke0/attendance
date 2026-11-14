from fastapi import FastAPI

from app import attend, auth, lectures

app = FastAPI()

app.include_router(auth.router)
app.include_router(lectures.router)
app.include_router(attend.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
