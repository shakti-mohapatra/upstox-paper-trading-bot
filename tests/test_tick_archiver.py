import asyncio
import gzip
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tick_archiver import append_tick, archive_path, make_on_tick, seconds_until_market_open

IST = timezone(timedelta(hours=5, minutes=30))


def test_archive_path_is_gzip_csv_per_instrument_per_day():
    path = archive_path("NSE_EQ|INE002A01018", "2026-07-16", dir="ticks")

    assert path == os.path.join("ticks", "NSE_EQ_INE002A01018_2026-07-16.csv.gz")


def test_append_tick_writes_compact_row_to_gzip_file(tmp_path):
    path = str(tmp_path / "ticks" / "test.csv.gz")

    append_tick(path, "09:15:03", 2456.7)
    append_tick(path, "09:15:04", 2457.0)

    with gzip.open(path, "rt") as f:
        assert f.read() == "09:15:03,2456.7\n09:15:04,2457.0\n"


def test_seconds_until_market_open_before_915_waits():
    now = datetime(2026, 7, 16, 8, 0, 0, tzinfo=IST)

    assert seconds_until_market_open(now) == 75 * 60


def test_seconds_until_market_open_after_915_is_zero():
    now = datetime(2026, 7, 16, 9, 20, 0, tzinfo=IST)

    assert seconds_until_market_open(now) == 0.0


def test_make_on_tick_appends_to_dated_archive_file(tmp_path):
    dir = str(tmp_path / "ticks")
    on_tick = make_on_tick("NSE_EQ|TEST", dir=dir)

    asyncio.run(on_tick({"instrument": "NSE_EQ|TEST", "ltp": 100.5, "ts": "2026-07-16T09:15:03+05:30"}))

    with gzip.open(os.path.join(dir, "NSE_EQ_TEST_2026-07-16.csv.gz"), "rt") as f:
        assert f.read() == "2026-07-16T09:15:03+05:30,100.5\n"
