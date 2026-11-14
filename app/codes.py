"""The 3-digit code and the session timer.

Nothing runs in the background (Vercel has no always-on process).
Everything is calculated from the clock at the moment of each request:

- The code changes every 60 seconds, counted from when the doctor pressed start.
- The previous code is still accepted for 15 seconds after it changes.
- The session stops by itself 5 minutes after the last successful student
  registration (or 5 minutes after start if nobody registered).
"""

import hashlib
import hmac
from datetime import datetime, timedelta

from app.models import Lecture

CODE_SECONDS = 60
GRACE_SECONDS = 15
AUTO_STOP = timedelta(minutes=5)


def code_window(lec: Lecture, now: datetime) -> int:
    """Which code we are on: 0 for the first minute, 1 for the second, ..."""
    elapsed = (now - lec.started_at).total_seconds()
    return max(0, int(elapsed // CODE_SECONDS))


def code_for(secret: str, window: int) -> str:
    digest = hmac.new(secret.encode(), str(window).encode(), hashlib.sha256).digest()
    return f"{int.from_bytes(digest[:8], 'big') % 1000:03d}"


def current_code(lec: Lecture, now: datetime) -> str:
    return code_for(lec.code_secret, code_window(lec, now))


def accepted_codes(lec: Lecture, now: datetime) -> dict[str, int]:
    """Codes a student may type right now -> the window each belongs to."""
    window = code_window(lec, now)
    codes = {code_for(lec.code_secret, window): window}
    seconds_into_window = (now - lec.started_at).total_seconds() - window * CODE_SECONDS
    if window > 0 and seconds_into_window < GRACE_SECONDS:
        codes.setdefault(code_for(lec.code_secret, window - 1), window - 1)
    return codes


def stop_time(lec: Lecture) -> datetime:
    last = lec.started_at
    if lec.last_success_at and lec.last_success_at > last:
        last = lec.last_success_at
    return last + AUTO_STOP


def refresh_running(lec: Lecture, now: datetime) -> bool:
    """Apply the 5-minute auto-stop. Returns True if the session is running.
    The caller commits."""
    if lec.is_running and lec.started_at and now >= stop_time(lec):
        lec.is_running = False
    return lec.is_running
