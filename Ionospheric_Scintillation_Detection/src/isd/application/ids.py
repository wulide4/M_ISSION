from __future__ import annotations

import random
import string
import time
from datetime import datetime, timedelta


def make_id(prefix: str) -> str:
    ts = int(time.time() * 1000)
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}_{ts}_{rand}"


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def iter_dates(start: str, end: str) -> list[str]:
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    out: list[str] = []
    cur = start_dt
    while cur <= end_dt:
        out.append(cur.date().isoformat())
        cur += timedelta(days=1)
    return out
