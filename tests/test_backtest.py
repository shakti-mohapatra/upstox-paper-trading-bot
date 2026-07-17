import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import json

import pytest

from backtest import STRATEGIES, candle_to_tick, load_candles, main, run_backtest, run_backtest_on_candles, summarize
from strategy import MACrossoverStrategy

INSTRUMENT = "NSE_EQ|TEST"


def write_params(path):
    params = {
        "version": 1,
        "instrument": INSTRUMENT,
        "enabled": True,
        "regime": "range",
        "entry_zone": {"low": 0.0, "high": 1_000_000.0},
        "target_pct": 1.0,
        "stop_loss_pct": 0.5,
        "trail_pct": 0.3,
        "max_position_qty": 100000,
    }
    with open(path, "w") as f:
        json.dump(params, f)


def write_candles(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def test_strategies_registry_includes_ma_crossover():
    assert STRATEGIES["ma_crossover"] is MACrossoverStrategy


def test_strategies_registry_includes_orb_v2():
    from strategy import ORBv2Strategy

    assert STRATEGIES["orb_v2"] is ORBv2Strategy


def test_candle_to_tick_maps_close_and_timestamp():
    candle = {"timestamp": "2026-07-16T09:16:00+05:30", "open": "99.0", "high": "99.5", "low": "98.5", "close": "99.2", "volume": "1000"}

    result = candle_to_tick(candle, "NSE_EQ|TEST")

    assert result == {"instrument": "NSE_EQ|TEST", "ltp": 99.2, "ts": "2026-07-16T09:16:00+05:30"}


def test_load_candles_reads_csv_rows(tmp_path):
    path = tmp_path / "candles.csv"
    path.write_text("timestamp,open,high,low,close,volume\n2026-07-16T09:16:00+05:30,99.0,99.5,98.5,99.2,1000\n")

    rows = load_candles(str(path))

    assert rows == [{"timestamp": "2026-07-16T09:16:00+05:30", "open": "99.0", "high": "99.5", "low": "98.5", "close": "99.2", "volume": "1000"}]


def test_run_backtest_replays_candles_through_engine_and_writes_trade_log(tmp_path):
    params_path = str(tmp_path / "params.json")
    write_params(params_path)
    data_path = str(tmp_path / "candles.csv")
    write_candles(
        data_path,
        [
            {"timestamp": "2026-07-16T09:16:00+05:30", "open": "99.0", "high": "99.0", "low": "99.0", "close": "99.0", "volume": "0"},
            {"timestamp": "2026-07-16T09:31:00+05:30", "open": "100.0", "high": "100.0", "low": "100.0", "close": "100.0", "volume": "0"},
            {"timestamp": "2026-07-16T09:32:00+05:30", "open": "99.5", "high": "99.5", "low": "99.5", "close": "99.5", "volume": "0"},
        ],
    )
    trade_log_path = str(tmp_path / "trades.csv")

    run_backtest(data_path, params_path, trade_log_path, INSTRUMENT)

    with open(trade_log_path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["reason"] for r in rows] == ["entry", "stop_loss"]


def test_summarize_computes_net_pnl_cost_pct_win_rate_and_drawdown(tmp_path):
    log_path = str(tmp_path / "trades.csv")
    with open(log_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ts", "symbol", "strategy", "side", "qty", "intended", "fill", "gross", "cost", "net", "reason"])
        writer.writeheader()
        writer.writerow({"ts": "t1", "symbol": INSTRUMENT, "strategy": "orb", "side": "BUY", "qty": 10, "intended": 100.0, "fill": 100.0, "gross": 0.0, "cost": 5.0, "net": -5.0, "reason": "entry"})
        writer.writerow({"ts": "t2", "symbol": INSTRUMENT, "strategy": "orb", "side": "SELL", "qty": 10, "intended": 99.5, "fill": 99.5, "gross": -5.0, "cost": 5.0, "net": -10.0, "reason": "stop_loss"})

    summary = summarize(log_path)

    assert summary["num_trades"] == 1
    assert summary["net_pnl"] == pytest.approx(-15.0)
    assert summary["cost_pct"] == pytest.approx(10 / 1995 * 100)
    assert summary["win_rate"] == pytest.approx(0.0)
    assert summary["max_drawdown"] == pytest.approx(15.0)


def test_main_runs_backtest_from_cli_args_and_prints_summary(tmp_path, capsys):
    params_path = str(tmp_path / "params.json")
    write_params(params_path)
    data_path = str(tmp_path / "candles.csv")
    write_candles(
        data_path,
        [
            {"timestamp": "2026-07-16T09:16:00+05:30", "open": "99.0", "high": "99.0", "low": "99.0", "close": "99.0", "volume": "0"},
            {"timestamp": "2026-07-16T09:31:00+05:30", "open": "100.0", "high": "100.0", "low": "100.0", "close": "100.0", "volume": "0"},
            {"timestamp": "2026-07-16T09:32:00+05:30", "open": "99.5", "high": "99.5", "low": "99.5", "close": "99.5", "volume": "0"},
        ],
    )
    trade_log_path = str(tmp_path / "trades.csv")

    summary = main(["--strategy", "orb", "--data", data_path, "--params", params_path, "--trade-log", trade_log_path])

    assert summary["num_trades"] == 1
    assert "net_pnl" in capsys.readouterr().out


def test_run_backtest_on_candles_replays_an_in_memory_candle_list(tmp_path):
    params_path = str(tmp_path / "params.json")
    write_params(params_path)
    candles = [
        {"timestamp": "2026-07-16T09:16:00+05:30", "open": "99.0", "high": "99.0", "low": "99.0", "close": "99.0", "volume": "0"},
        {"timestamp": "2026-07-16T09:31:00+05:30", "open": "100.0", "high": "100.0", "low": "100.0", "close": "100.0", "volume": "0"},
        {"timestamp": "2026-07-16T09:32:00+05:30", "open": "99.5", "high": "99.5", "low": "99.5", "close": "99.5", "volume": "0"},
    ]
    trade_log_path = str(tmp_path / "trades.csv")

    run_backtest_on_candles(candles, params_path, trade_log_path, INSTRUMENT)

    with open(trade_log_path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["reason"] for r in rows] == ["entry", "stop_loss"]
