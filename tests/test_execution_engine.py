import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution_engine import ExecutionEngine

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
        "max_position_qty": 10,
    }
    params.update(overrides)
    with open(path, "w") as f:
        json.dump(params, f)
    return params


def test_stores_broker_and_default_params_path():
    engine = ExecutionEngine(broker="fake-broker")
    assert engine.broker == "fake-broker"
    assert engine.params_path == "strategy_params.json"


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

    assert broker.calls == [(INSTRUMENT, "BUY", 10, 100.5)]
    assert engine.position["qty"] == 10
    assert engine.position["entry_price"] == 100.5


def test_on_tick_does_not_re_enter_while_already_in_position(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.5})

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.6})

    assert broker.calls == [(INSTRUMENT, "BUY", 10, 100.5)]


def test_on_tick_exits_at_target(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0})  # entry, target = 101.0

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 101.0})

    assert broker.calls[-1] == (INSTRUMENT, "SELL", 10, 101.0)
    assert engine.position is None


def test_on_tick_exits_at_stop_loss(tmp_path):
    path = str(tmp_path / "strategy_params.json")
    write_params(path)
    broker = FakeBroker()
    engine = ExecutionEngine(broker=broker, params_path=path)
    engine.load_params()
    engine.on_tick({"instrument": INSTRUMENT, "ltp": 100.0})  # entry, stop = 99.5

    engine.on_tick({"instrument": INSTRUMENT, "ltp": 99.5})

    assert broker.calls[-1] == (INSTRUMENT, "SELL", 10, 99.5)
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

    assert broker.calls[-1] == (INSTRUMENT, "SELL", 10, 100.4)
    assert engine.position is None


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
    assert broker.calls == [(INSTRUMENT, "BUY", 10, 100.0), (INSTRUMENT, "SELL", 10, 99.5)]
