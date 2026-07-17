"""Tick-archiving helpers, used by main.py's build_system() to archive every
live tick to local per-day gzip CSV before it reaches the execution engine.

Not routed through execution_engine - this is data collection only.
"""
import gzip
import os
from datetime import datetime, time as dtime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_INSTRUMENT = "NSE_EQ|INE002A01018"  # RELIANCE, matches main.py's default


def seconds_until_market_open(now: datetime, market_open: dtime = dtime(9, 15)) -> float:
    open_dt = datetime.combine(now.date(), market_open, tzinfo=now.tzinfo)
    return max(0.0, (open_dt - now).total_seconds())


def archive_path(instrument: str, date: str, dir: str = "ticks") -> str:
    safe = instrument.replace("|", "_").replace("/", "_")
    return os.path.join(dir, f"{safe}_{date}.csv.gz")


def append_tick(path: str, ts: str, ltp: float) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "at") as f:
        f.write(f"{ts},{ltp}\n")


def make_on_tick(instrument: str, dir: str = "ticks"):
    async def on_tick(tick):
        ts = tick.get("ts", datetime.now(IST).isoformat())
        append_tick(archive_path(instrument, ts[:10], dir), ts, tick["ltp"])

    return on_tick
