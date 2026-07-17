"""Fetch historical 1-min candles from Upstox's V3 historical-candle API and
save them in the CSV schema backtest.load_candles() already expects.

1-min data is only available in <=1-calendar-month spans per request (Upstox
limit), so a multi-month range is fetched in monthly chunks and merged.
"""
import argparse
import calendar
import csv
from datetime import date

import requests

import auth

BASE_URL = "https://api.upstox.com/v3/historical-candle"
INTRADAY_URL = "https://api.upstox.com/v3/historical-candle/intraday"
FIELDNAMES = ["timestamp", "open", "high", "low", "close", "volume"]


def _month_chunks(from_date: date, to_date: date) -> list[tuple[date, date]]:
    chunks = []
    cursor = from_date
    while cursor <= to_date:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        chunk_end = min(date(cursor.year, cursor.month, last_day), to_date)
        chunks.append((cursor, chunk_end))
        if chunk_end.month == 12:
            cursor = date(chunk_end.year + 1, 1, 1)
        else:
            cursor = date(chunk_end.year, chunk_end.month + 1, 1)
    return chunks


def fetch_month(instrument_key: str, from_date: date, to_date: date, access_token: str, unit: str = "minutes", interval: str = "1") -> list[dict]:
    url = f"{BASE_URL}/{instrument_key}/{unit}/{interval}/{to_date.isoformat()}/{from_date.isoformat()}"
    resp = requests.get(url, headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"})
    resp.raise_for_status()
    candles = resp.json()["data"]["candles"]
    return [
        {"timestamp": c[0], "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5]}
        for c in candles
    ]


def fetch_intraday(instrument_key: str, access_token: str, unit: str = "minutes", interval: str = "1") -> list[dict]:
    """Today's in-progress candles - historical-candle returns empty for today,
    only completed days. This is the only endpoint that has today's data."""
    url = f"{INTRADAY_URL}/{instrument_key}/{unit}/{interval}"
    resp = requests.get(url, headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"})
    resp.raise_for_status()
    candles = resp.json()["data"]["candles"]
    return [
        {"timestamp": c[0], "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5]}
        for c in candles
    ]


def fetch_candles(instrument_key: str, from_date: date, to_date: date, access_token: str, unit: str = "minutes", interval: str = "1") -> list[dict]:
    candles = []
    for chunk_start, chunk_end in _month_chunks(from_date, to_date):
        candles.extend(fetch_month(instrument_key, chunk_start, chunk_end, access_token, unit, interval))
    candles.sort(key=lambda c: c["timestamp"])
    return candles


def save_candles_csv(candles: list[dict], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(candles)


def main(argv=None) -> str:
    parser = argparse.ArgumentParser(description="Fetch Upstox 1-min historical candles and save as backtest.py's CSV schema.")
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--from-date", required=True, type=date.fromisoformat)
    parser.add_argument("--to-date", required=True, type=date.fromisoformat)
    parser.add_argument("--out", required=True)
    parser.add_argument("--unit", default="minutes")
    parser.add_argument("--interval", default="1")
    args = parser.parse_args(argv)

    token = auth.login()
    candles = fetch_candles(args.instrument, args.from_date, args.to_date, token, args.unit, args.interval)
    save_candles_csv(candles, args.out)
    print(f"wrote {len(candles)} candles to {args.out}")
    return args.out


if __name__ == "__main__":
    main()
