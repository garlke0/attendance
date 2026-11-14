from fastapi import FastAPI

from app import auth

app = FastAPI()

app.include_router(auth.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
