"""Campus location check for student attendance.

The campus point and radius come from environment variables, so they can be
changed on Vercel without touching the code:

    CAMPUS_LAT        latitude of the campus  (default: APU, Kuala Lumpur)
    CAMPUS_LNG        longitude of the campus
    CAMPUS_RADIUS_M   allowed distance in metres (default: 500)

The student's location is only used for this check; it is not saved.
"""

import math
import os

CAMPUS_LAT = float(os.getenv("CAMPUS_LAT", "3.0550753"))
CAMPUS_LNG = float(os.getenv("CAMPUS_LNG", "101.7005763"))
CAMPUS_RADIUS_M = float(os.getenv("CAMPUS_RADIUS_M", "500"))

_EARTH_RADIUS_M = 6_371_000


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def valid_coords(lat: float | None, lng: float | None) -> bool:
    return (
        lat is not None and lng is not None
        and math.isfinite(lat) and math.isfinite(lng)
        and -90 <= lat <= 90 and -180 <= lng <= 180
    )


def on_campus(lat: float, lng: float) -> bool:
    return distance_m(lat, lng, CAMPUS_LAT, CAMPUS_LNG) <= CAMPUS_RADIUS_M
