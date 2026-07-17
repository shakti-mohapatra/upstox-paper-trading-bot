import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv

import pytest

from costs import costs
from execution_engine import ExecutionEngine
from strategy import ORBStrategy

INSTRUMENT = "NSE_EQ|TEST"


def write_params(path, **overrides):
    params = {
        "version": 1,
        "instrument": INSTRUMENT,
        "enabled": True,
        "regime": "range",
        "entry_zone": {"low": 100.0, "high": 101.0},
        "target_pct": 1.0,
        "stop_loss_pct": 0.5,
        "trail_pct": 0.3,
        "max_position_qty": 150,  # binds below the sizer's own ~200 cap at this toy price scale, high enough to clear MIN_TURNOVER
    }
    params.update(overrides)
    with open(path, "w") as f:
        json.dump(params, f)
    return params


def test_stores_broker_and_default_params_path():
    engine = ExecutionEngine(broker="fake-broker")
    assert engine.broker == "fake-broker"
    assert engine.params_path == "strategy_params.json"


def test_stores_injected_strategy():
    fake_strategy = object()
    engine = ExecutionEngine(broker="fake-broker", strategy=fake_strategy)
    assert engine.strategy is fake_strategy


def test_defaults_to_orb_strategy_when_none_given():
    from strategy import ORBStrategy

    engine = ExecutionEngine(broker="fake-broker")
    assert isinstance(engine.strategy, ORBStrategy)


def test_load_params_reads_json_file_and_caches_it(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    expected = write_params(path)
    engine = ExecutionEngine(broker="fake-broker", params_path=path)

    result = engine.load_params()

    assert result == expected
    assert engine.params == expected


def test_load_params_rejects_wrong_schema_version(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path, version=2)
    engine = ExecutionEngine(broker="fake-broker", params_path=path)

    try:
        engine.load_params()
        assert False, "expected ValueError"
    except ValueError:
        pass


class FakeBroker:
    def __init__(self):
        self.calls = []

    def place_order(self, instrument, side, qty, price=None):
        self.calls.append((instrument, side, qty, price))
        return f"order-{len(self.calls)}"


def test_on_tick_does_nothing_without_loaded_params():
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker)

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5})

    assert broker.calls == []


def test_on_tick_ignores_ticks_for_other_instruments(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    engine.on_tick({"instrument": "NSE_EQ|OTHER", "ltp": 100.5})

    assert broker.calls == []


def test_on_tick_skips_entry_when_disabled(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path, enabled=False)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5})

    assert broker.calls == []


def test_on_tick_skips_entry_when_regime_is_avoid(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path, regime="avoid")
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5})

    assert broker.calls == []


def test_on_tick_skips_entry_when_price_outside_entry_zone(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 105.0})

    assert broker.calls == []


def test_on_tick_enters_long_when_price_inside_entry_zone(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5})

    assert broker.calls == [(INSTRUMENT, "BUY", 150, 100.5)]
    assert engine.position["qty"] == 150
    assert engine.position["entry_price"] == 100.5


class FakeStrategy:
    """Enters unconditionally with a caller-supplied stop_loss_pct override,
    so tests can prove the engine actually uses it for sizing instead of the
    frozen params value."""

    def __init__(self, stop_loss_pct):
        self.stop_loss_pct = stop_loss_pct

    def new_day(self):
        pass

    def signal(self, tick, params, position):
        if position is not None:
            return {"action": "hold"}
        return {"action": "enter", "stop_loss_pct": self.stop_loss_pct}


def test_on_tick_entry_sizing_uses_strategys_stop_loss_pct_override(tmp_path):
    from position_sizing import size_position

    path = str(tmp_path / "strategy_params.json")
    write_params(path, stop_loss_pct=0.5, max_position_qty=100000)  # params says 0.5; strategy overrides to 6.0 (large enough to escape the 20%-turnover ceiling both would otherwise share)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path, strategy=FakeStrategy(stop_loss_pct=6.0))
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5})

    expected_qty = size_position(capital=100000.0, risk_pct=0.01, entry_price=100.5, stop_loss_pct=6.0, buying_power=100000.0)
    assert engine.position["qty"] == expected_qty
    assert expected_qty != size_position(capital=100000.0, risk_pct=0.01, entry_price=100.5, stop_loss_pct=0.5, buying_power=100000.0)


def test_on_tick_does_not_re_enter_while_already_in_position(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5})

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.6})

    assert broker.calls == [(INSTRUMENT, "BUY", 150, 100.5)]


def test_on_tick_exits_at_target(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0})  # entry, target = 101.0

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 101.0})

    assert broker.calls[-1] == (INSTRUMENT, "SELL", 150, 101.0)
    assert engine.position is None


def test_on_tick_exits_at_stop_loss(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0})  # entry, stop = 99.5

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.5})

    assert broker.calls[-1] == (INSTRUMENT, "SELL", 150, 99.5)
    assert engine.position is None


def test_on_tick_trailing_stop_locks_in_gains_below_hard_stop(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0})  # entry, hard stop = 99.5
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.8})  # high water -> trail stop = 100.4976

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.4})

    assert broker.calls[-1] == (INSTRUMENT, "SELL", 150, 100.4)
    assert engine.position is None


def test_on_tick_logs_entry_and_exit_fills_to_trade_log(tmp_path):
    params_path = str(tmp_path / "strategy_params.json")
    write_params(params_path)
    log_path = str(tmp_path / "trades.csv")
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=params_path, trade_log_path=log_path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.0, "ts": "2026-07-16T09:16:00+05:30"})  # orb window
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0, "ts": "2026-07-16T09:31:00+05:30"})

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.5, "ts": "2026-07-16T09:32:00+05:30"})

    with open(log_path, newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["side"] == "BUY"
    assert rows[0]["reason"] == "entry"
    assert rows[0]["ts"] == "2026-07-16T09:31:00+05:30"
    assert rows[1]["side"] == "SELL"
    assert rows[1]["reason"] == "stop_loss"
    entry_fill = 100.0 * 1.0005
    exit_fill = 99.5 * 0.9995
    assert float(rows[0]["intended"]) == pytest.approx(100.0)
    assert float(rows[0]["fill"]) == pytest.approx(entry_fill)
    assert float(rows[1]["intended"]) == pytest.approx(99.5)
    assert float(rows[1]["fill"]) == pytest.approx(exit_fill)
    expected_net = (exit_fill - entry_fill) * 150 - costs("SELL", 150, exit_fill)
    assert float(rows[1]["net"]) == pytest.approx(expected_net)


def test_on_tick_prints_entry_and_exit_fills_to_console(tmp_path, capsys):
    params_path = str(tmp_path / "strategy_params.json")
    write_params(params_path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=params_path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.0, "ts": "2026-07-16T09:16:00+05:30"})  # orb window
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0, "ts": "2026-07-16T09:31:00+05:30"})  # entry

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.5, "ts": "2026-07-16T09:32:00+05:30"})  # stop_loss exit

    out = capsys.readouterr().out
    assert "BUY" in out and "entry" in out
    assert "SELL" in out and "stop_loss" in out


def test_on_tick_forces_square_off_at_1515_ist_regardless_of_target_or_stop(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.0, "ts": "2026-07-16T09:16:00+05:30"})  # orb window
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0, "ts": "2026-07-16T09:31:00+05:30"})  # entry

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.2, "ts": "2026-07-16T15:15:00+05:30"})  # neither target nor stop

    assert broker.calls[-1] == (INSTRUMENT, "SELL", 150, 100.2)
    assert engine.position is None


def test_on_tick_skips_entry_after_1500_ist(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5, "ts": "2026-07-16T15:00:00+05:30"})

    assert broker.calls == []
    assert engine.position is None


def test_on_tick_never_enters_during_orb_window_even_if_price_is_inside_entry_zone(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5, "ts": "2026-07-16T09:20:00+05:30"})

    assert broker.calls == []
    assert engine.position is None


def test_on_tick_enters_only_on_breakout_above_orb_high_after_window_closes(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.0, "ts": "2026-07-16T09:16:00+05:30"})  # orb window
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0, "ts": "2026-07-16T09:25:00+05:30"})  # orb window, high=100.0
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0, "ts": "2026-07-16T09:31:00+05:30"})  # not a breakout (==high)

    assert broker.calls == []

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5, "ts": "2026-07-16T09:32:00+05:30"})  # breaks above 100.0

    assert broker.calls == [(INSTRUMENT, "BUY", 150, 100.5)]


def test_on_tick_entry_qty_uses_risk_based_sizing_when_ceiling_is_generous(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path, max_position_qty=100000)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5})

    assert broker.calls == [(INSTRUMENT, "BUY", 199, 100.5)]  # 20%-of-capital cap binds before the 100000 ceiling or risk_qty=1990


def test_on_tick_skips_entry_when_position_sizing_returns_zero_qty(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path, entry_zone={"low": 24000.0, "high": 26000.0})
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 25000.0})  # 20%-of-capital cap floors qty to 0

    assert broker.calls == []
    assert engine.position is None


def test_on_tick_blocks_new_entries_after_5_trades_today(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.0, "ts": "2026-07-16T09:16:00+05:30"})  # orb window, orb_high=99
    for i in range(5):
        minute = 31 + i
        engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5, "ts": f"2026-07-16T09:{minute}:00+05:30"})  # entry
        engine.on_tick({"instrument": INSTRUMENT, "ltp": 102.0, "ts": f"2026-07-16T09:{minute}:30+05:30"})  # target exit

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5, "ts": "2026-07-16T10:00:00+05:30"})  # would otherwise be a 6th entry

    assert len(broker.calls) == 10  # 5 entries + 5 target exits, 6th entry blocked
    assert engine.position is None


def test_on_tick_halts_new_entries_after_3_consecutive_losses(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.0, "ts": "2026-07-16T09:16:00+05:30"})  # orb window, orb_high=99
    for i in range(3):
        minute = 31 + i
        engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5, "ts": f"2026-07-16T09:{minute}:00+05:30"})  # entry
        engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.5, "ts": f"2026-07-16T09:{minute}:30+05:30"})  # stop_loss (losing exit)

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5, "ts": "2026-07-16T10:00:00+05:30"})  # would otherwise be a 4th entry

    assert engine.halted is True
    assert len(broker.calls) == 6  # 3 losing entries+exits, 4th entry blocked
    assert engine.position is None


def test_on_tick_applies_slippage_to_entry_and_exit_fill_price(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0})  # entry, intended 100.0, fill 100.05 (0.05% adverse)

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 101.5})  # target exit (target=101.0), intended 101.5, fill 101.44925

    entry_fill = 100.0 * 1.0005
    exit_fill = 101.5 * 0.9995
    gross = (exit_fill - entry_fill) * 150
    expected_net = gross - costs("BUY", 150, entry_fill) - costs("SELL", 150, exit_fill)
    assert engine.realized_pnl_today == pytest.approx(expected_net)


def test_on_tick_skips_entry_when_final_capped_qty_turnover_is_below_min_turnover(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path, max_position_qty=1)  # sizer would allow ~200, but the params ceiling caps it to 1
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5})  # capped qty=1, turnover=100.5 < MIN_TURNOVER

    assert broker.calls == []
    assert engine.position is None


def test_engine_does_not_reset_strategy_state_on_the_very_first_tick(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    strategy = ORBStrategy()
    strategy.orb_high = 99.0  # pre-seeded, e.g. via main.maybe_backfill_orb before any tick is processed
    engine = ExecutionEngine(broker=broker, params_path=path, strategy=strategy)
    engine.load_params()

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5, "ts": "2026-07-16T09:31:00+05:30"})  # breaks above seeded orb_high

    assert broker.calls == [(INSTRUMENT, "BUY", 150, 100.5)]


def test_engine_resets_daily_state_across_days(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()

    for day in range(1, 13):
        date = f"2026-08-{day:02d}"
        engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.0, "ts": f"{date}T09:16:00+05:30"})  # orb window, orb_high=99
        engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5, "ts": f"{date}T09:31:00+05:30"})  # breakout entry
        engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.5, "ts": f"{date}T09:32:00+05:30"})  # stop_loss (losing exit)

    entries = [c for c in broker.calls if c[1] == "BUY"]
    assert len(entries) == 12  # today: halted latches after 3 consecutive losses on day 3, blocking days 4-12
    assert engine.halted is False  # today: stays True forever once latched


def test_on_tick_halts_new_entries_after_daily_max_loss_breached(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path, daily_max_loss=4.0)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0})  # entry, stop = 99.5
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.5})  # stopped out, loss = 5.0 -> breach

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5})  # would otherwise re-enter

    assert engine.halted is True
    assert broker.calls == [(INSTRUMENT, "BUY", 150, 100.0), (INSTRUMENT, "SELL", 150, 99.5)]
