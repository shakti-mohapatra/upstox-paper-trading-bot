"""Phase 0 proof (SONNET_BUILD_PLAN.md §3): a scripted intraday tick sequence
through the real engine, proving in one continuous session that: fills are
logged net-of-cost, the daily-max-loss kill switch fires, the 15:15
square-off flattens an open position, and no further entries happen once
halted / after hours.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution_engine import ExecutionEngine

INSTRUMENT = "NSE_EQ|TEST"


class FakeBroker:
    def __init__(self):
        self.calls = []

    def place_order(self, instrument, side, qty, price=None):
        self.calls.append((instrument, side, qty, price))
        return f"order-{len(self.calls)}"


def write_params(path):
    import json

    params = {
        "version": 1,
        "instrument": INSTRUMENT,
        "enabled": True,
        "regime": "range",
        "entry_zone": {"low": 0.0, "high": 1_000_000.0},  # stub wide-open; ORB gate is the real filter
        "target_pct": 1.0,
        "stop_loss_pct": 0.5,
        "trail_pct": 0.3,
        "max_position_qty": 100000,  # generous ceiling; risk-based sizing is the active constraint
    }
    with open(path, "w") as f:
        json.dump(params, f)


def tick(ltp, ts):
    return {"instrument": INSTRUMENT, "ltp": ltp, "ts": f"2026-07-16T{ts}+05:30"}


def test_scripted_session_proves_net_of_cost_pnl_square_off_and_kill_switch(tmp_path):
    params_path = str(tmp_path / "strategy_params.json")
    write_params(params_path)
    log_path = str(tmp_path / "trades.csv")
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=params_path, daily_max_loss=700.0, trade_log_path=log_path)
    engine.load_params()

    engine.on_tick(tick(99.0, "09:16:00"))  # ORB window, sets orb_high=99.0

    engine.on_tick(tick(100.0, "09:31:00"))  # breakout entry, trade 1
    engine.on_tick(tick(99.5, "09:35:00"))  # hits hard stop -> exit, loss
    assert engine.halted is False, "single small loss must not breach the 700 threshold yet"

    engine.on_tick(tick(100.0, "09:40:00"))  # breakout entry, trade 2
    engine.on_tick(tick(100.0, "12:00:00"))  # flat midday tick, no exit trigger
    engine.on_tick(tick(99.8, "15:15:00"))  # forced square-off, not target/stop
    assert engine.halted is True, "cumulative loss across both trades must breach 700 at square-off"

    entries_before_late_attempt = len(broker.calls)
    engine.on_tick(tick(100.5, "15:20:00"))  # breakout again, but halted + after hours
    assert len(broker.calls) == entries_before_late_attempt, "no new entry once halted / after hours"

    with open(log_path, newline="") as f:
        rows = list(csv.DictReader(f))

    assert [r["reason"] for r in rows] == ["entry", "stop_loss", "entry", "square_off"]
    # net is genuinely cost-inclusive: raw gross on the stop-loss leg is -500, net is more negative
    stop_loss_row = rows[1]
    assert float(stop_loss_row["gross"]) == -500.0
    assert float(stop_loss_row["net"]) < float(stop_loss_row["gross"])
    assert float(stop_loss_row["cost"]) > 0
