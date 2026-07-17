import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import historical_data
from backtest import load_candles


def test_month_chunks_splits_multi_month_range_into_calendar_months():
    chunks = historical_data._month_chunks(date(2026, 5, 15), date(2026, 7, 10))

    assert chunks == [
        (date(2026, 5, 15), date(2026, 5, 31)),
        (date(2026, 6, 1), date(2026, 6, 30)),
        (date(2026, 7, 1), date(2026, 7, 10)),
    ]


def test_month_chunks_single_month_returns_one_chunk():
    chunks = historical_data._month_chunks(date(2026, 7, 1), date(2026, 7, 15))

    assert chunks == [(date(2026, 7, 1), date(2026, 7, 15))]


def test_fetch_month_parses_candle_arrays_and_calls_v3_url(monkeypatch):
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "success", "data": {"candles": [["2026-07-15T09:16:00+05:30", 99.0, 99.5, 98.5, 99.2, 1000, 0]]}}

    def fake_get(url, headers=None):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResp()

    monkeypatch.setattr(historical_data.requests, "get", fake_get)

    result = historical_data.fetch_month("NSE_EQ|TEST", date(2026, 7, 1), date(2026, 7, 15), "tok123")

    assert result == [{"timestamp": "2026-07-15T09:16:00+05:30", "open": 99.0, "high": 99.5, "low": 98.5, "close": 99.2, "volume": 1000}]
    assert captured["url"] == "https://api.upstox.com/v3/historical-candle/NSE_EQ|TEST/minutes/1/2026-07-15/2026-07-01"
    assert captured["headers"]["Authorization"] == "Bearer tok123"


def test_fetch_candles_merges_and_sorts_chunks_across_months(monkeypatch):
    def fake_get(url, headers=None):
        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                if "/2026-06-30/2026-06-01" in url:
                    return {"data": {"candles": [["2026-06-15T09:16:00+05:30", 1, 1, 1, 1, 1, 0]]}}
                return {"data": {"candles": [["2026-07-01T09:16:00+05:30", 2, 2, 2, 2, 2, 0]]}}

        return FakeResp()

    monkeypatch.setattr(historical_data.requests, "get", fake_get)

    result = historical_data.fetch_candles("NSE_EQ|TEST", date(2026, 6, 1), date(2026, 7, 1), "tok")

    assert [c["timestamp"] for c in result] == ["2026-06-15T09:16:00+05:30", "2026-07-01T09:16:00+05:30"]


def test_fetch_intraday_parses_candles_and_calls_v3_intraday_url(monkeypatch):
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "success", "data": {"candles": [["2026-07-16T09:15:00+05:30", 1295.5, 1301.3, 1295.5, 1299.9, 270574, 0]]}}

    def fake_get(url, headers=None):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResp()

    monkeypatch.setattr(historical_data.requests, "get", fake_get)

    result = historical_data.fetch_intraday("NSE_EQ|TEST", "tok123")

    assert result == [{"timestamp": "2026-07-16T09:15:00+05:30", "open": 1295.5, "high": 1301.3, "low": 1295.5, "close": 1299.9, "volume": 270574}]
    assert captured["url"] == "https://api.upstox.com/v3/historical-candle/intraday/NSE_EQ|TEST/minutes/1"
    assert captured["headers"]["Authorization"] == "Bearer tok123"


def test_save_candles_csv_is_reloadable_via_backtest_load_candles(tmp_path):
    candles = [{"timestamp": "2026-07-16T09:16:00+05:30", "open": 99.0, "high": 99.5, "low": 98.5, "close": 99.2, "volume": 1000}]
    path = str(tmp_path / "out.csv")

    historical_data.save_candles_csv(candles, path)
    rows = load_candles(path)

    assert rows == [{"timestamp": "2026-07-16T09:16:00+05:30", "open": "99.0", "high": "99.5", "low": "98.5", "close": "99.2", "volume": "1000"}]
