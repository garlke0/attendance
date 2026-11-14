"""Create all tables. Safe to run more than once (existing tables are kept)."""

from app import models  # noqa: F401  (registers the tables)
from app.db import Base, engine

Base.metadata.create_all(engine)
print("Tables:", ", ".join(sorted(Base.metadata.tables)))
