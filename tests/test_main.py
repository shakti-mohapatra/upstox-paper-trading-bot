import asyncio
import gzip
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

import main
from main import build_system
from strategy import ORBStrategy

INSTRUMENT = "NSE_EQ|TEST"


def test_build_system_archives_ticks_before_feeding_engine(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    trade_log_path = str(tmp_path / "trades.csv")
    ticks_dir = str(tmp_path / "ticks")

    engine, listener = build_system(
        "token-123", INSTRUMENT, params_path=path, trade_log_path=trade_log_path, ticks_dir=ticks_dir
    )

    asyncio.run(listener.on_tick({"instrument": INSTRUMENT, "ltp": 99.0, "ts": "2026-07-16T09:16:00+05:30"}))  # orb window
    asyncio.run(listener.on_tick({"instrument": INSTRUMENT, "ltp": 100.0, "ts": "2026-07-16T09:31:00+05:30"}))  # breakout

    archive_file = os.path.join(ticks_dir, "NSE_EQ_TEST_2026-07-16.csv.gz")
    with gzip.open(archive_file, "rt") as f:
        assert f.read() == "2026-07-16T09:16:00+05:30,99.0\n2026-07-16T09:31:00+05:30,100.0\n"
    assert engine.position is not None  # both ticks reached the engine after archiving


def test_build_system_wires_listener_ticks_into_engine(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    trade_log_path = str(tmp_path / "trades.csv")
    ticks_dir = str(tmp_path / "ticks")

    engine, listener = build_system(
        "token-123", INSTRUMENT, params_path=path, trade_log_path=trade_log_path, ticks_dir=ticks_dir
    )

    assert listener.instruments == [INSTRUMENT]
    assert engine.params["instrument"] == INSTRUMENT

    entry_price = 100.0  # any real (non-zero) price inside the stub's wide-open entry_zone
    asyncio.run(listener.on_tick({"instrument": INSTRUMENT, "ltp": entry_price}))

    assert engine.position is not None


def test_maybe_backfill_orb_sets_orb_high_from_candles_when_started_late(monkeypatch):
    strat = ORBStrategy()
    captured = {}

    def fake_fetch_intraday(instrument, access_token, unit="minutes", interval="1"):
        captured["args"] = (instrument, access_token)
        return [{"timestamp": "2026-07-16T09:20:00+05:30", "high": 101.5}]

    monkeypatch.setattr(main.historical_data, "fetch_intraday", fake_fetch_intraday)
    late = datetime(2026, 7, 16, 9, 58, tzinfo=main.IST)

    main.maybe_backfill_orb(strat, INSTRUMENT, "tok", now=late)

    assert strat.orb_high == 101.5
    assert captured["args"] == (INSTRUMENT, "tok")


def test_maybe_backfill_orb_is_noop_when_started_within_window(monkeypatch):
    strat = ORBStrategy()

    def fail_fetch_intraday(*a, **k):
        raise AssertionError("should not fetch candles when started on time")

    monkeypatch.setattr(main.historical_data, "fetch_intraday", fail_fetch_intraday)
    on_time = datetime(2026, 7, 16, 9, 20, tzinfo=main.IST)

    main.maybe_backfill_orb(strat, INSTRUMENT, "tok", now=on_time)

    assert strat.orb_high is None


def test_build_system_wires_trade_log_path(tmp_path):
    params_path = str(tmp_path / "strategy_params.json")
    trade_log_path = str(tmp_path / "trades.csv")

    engine, _ = build_system("token-123", INSTRUMENT, params_path=params_path, trade_log_path=trade_log_path)

    assert engine.trade_log_path == trade_log_path


def test_build_system_wires_injected_strategy_into_engine(tmp_path):
    params_path = str(tmp_path / "strategy_params.json")
    trade_log_path = str(tmp_path / "trades.csv")
    strat = ORBStrategy()
    strat.orb_high = 42.0

    engine, _ = build_system(
        "token-123", INSTRUMENT, params_path=params_path, trade_log_path=trade_log_path, strategy=strat
    )

    assert engine.strategy is strat


def test_run_backfills_orb_and_wires_strategy_into_build_system(monkeypatch):
    calls = {}

    class FakeListener:
        async def run_forever(self):
            calls["ran"] = True

    def fake_build_system(access_token, instrument, strategy=None):
        calls["strategy"] = strategy
        return object(), FakeListener()

    def fake_maybe_backfill_orb(strategy, instrument, access_token):
        calls["backfilled_strategy"] = strategy

    monkeypatch.setattr(main, "build_system", fake_build_system)
    monkeypatch.setattr(main, "maybe_backfill_orb", fake_maybe_backfill_orb)

    asyncio.run(main.run("tok", INSTRUMENT))

    assert isinstance(calls["strategy"], ORBStrategy)
    assert calls["backfilled_strategy"] is calls["strategy"]
    assert calls["ran"] is True


def test_main_logs_in_before_waiting_for_market_open(monkeypatch):
    calls = []

    monkeypatch.setattr(main.auth, "login", lambda: calls.append("login") or "tok")
    monkeypatch.setattr(
        main.tick_archiver, "seconds_until_market_open", lambda now: (calls.append("check_wait"), 120)[1]
    )
    monkeypatch.setattr(main.time_mod, "sleep", lambda s: calls.append(("sleep", s)))

    async def fake_run(token, instrument=main.DEFAULT_INSTRUMENT):
        calls.append(("run", token))

    monkeypatch.setattr(main, "run", fake_run)

    main.main()

    assert calls == ["login", "check_wait", ("sleep", 120), ("run", "tok")]
