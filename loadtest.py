"""Load test: N fake students register at the same time while the doctor's
screen refreshes every 5 seconds. Uses fake names only; the test lecture is
deleted at the end.

Usage:
  python loadtest.py http://localhost:8000 doctor1
  python loadtest.py https://your-app.vercel.app doctor1 --students 300
The doctor password is typed hidden.
"""

import argparse
import asyncio
import statistics
import time
from getpass import getpass

import httpx


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("username")
    ap.add_argument("--students", type=int, default=300)
    ap.add_argument("--concurrency", type=int, default=100,
                    help="how many students submit at the exact same moment")
    args = ap.parse_args()
    password = getpass("Doctor password: ")
    base = args.base_url.rstrip("/")

    async with httpx.AsyncClient(base_url=base, timeout=60) as doctor:
        r = await doctor.post("/api/auth/login",
                              json={"username": args.username, "password": password})
        r.raise_for_status()
        lid = (await doctor.post("/api/lectures", json={"name": "LOAD TEST"})).json()["id"]
        await doctor.post(f"/api/lectures/{lid}/start")
        print(f"Lecture {lid} started. Sending {args.students} students...")

        done = asyncio.Event()

        async def doctor_screen():
            polls = []
            while not done.is_set():
                t = time.perf_counter()
                await doctor.get(f"/api/lectures/{lid}/live")
                polls.append(time.perf_counter() - t)
                try:
                    await asyncio.wait_for(done.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            return polls

        sem = asyncio.Semaphore(args.concurrency)
        results = []

        async def student(i, client):
            async with sem:
                # The student reads the code off the doctor's screen
                code = (await doctor.get(f"/api/lectures/{lid}/live")).json()["code"]
                t = time.perf_counter()
                try:
                    resp = await client.post("/api/attend", json={
                        "name": f"طالب {i}", "student_id": str(900000 + i),
                        "major": "Load test", "code": code,
                    })
                    results.append((resp.status_code, time.perf_counter() - t,
                                    resp.json().get("detail")))
                except Exception as e:  # network error, timeout
                    results.append((0, time.perf_counter() - t, repr(e)))

        start = time.perf_counter()
        screen = asyncio.create_task(doctor_screen())
        limits = httpx.Limits(max_connections=args.concurrency)
        async with httpx.AsyncClient(base_url=base, timeout=60, limits=limits) as client:
            await asyncio.gather(*(student(i, client) for i in range(1, args.students + 1)))
        total = time.perf_counter() - start
        done.set()
        polls = await screen

        live = (await doctor.get(f"/api/lectures/{lid}/live")).json()
        saved = len(live["attendance"])
        await doctor.delete(f"/api/lectures/{lid}")  # clean up

    ok = [d for s, d, _ in results if s == 200]
    errors = {}
    for s, _, detail in results:
        if s != 200:
            errors[f"{s} {detail}"] = errors.get(f"{s} {detail}", 0) + 1
    times = sorted(d for _, d, _ in results)

    def pct(p):
        return times[min(len(times) - 1, int(len(times) * p))]

    print()
    print(f"Students sent:        {args.students}")
    print(f"Registered OK (200):  {len(ok)}")
    print(f"Saved in the list:    {saved}")
    print(f"Total time:           {total:.1f} s")
    print(f"Response time median: {statistics.median(times):.2f} s")
    print(f"Response time 95%:    {pct(0.95):.2f} s")
    print(f"Response time max:    {times[-1]:.2f} s")
    if polls:
        print(f"Doctor screen max:    {max(polls):.2f} s")
    print("Errors:" if errors else "Errors:               none")
    for k, v in errors.items():
        print(f"  {v} x {k}")
    print("Test lecture deleted.")


if __name__ == "__main__":
    asyncio.run(main())
