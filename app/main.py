from fastapi import FastAPI

from app import auth, lectures

app = FastAPI()

app.include_router(auth.router)
app.include_router(lectures.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
