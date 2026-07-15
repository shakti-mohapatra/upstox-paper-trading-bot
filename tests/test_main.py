import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import build_system

INSTRUMENT = "NSE_EQ|TEST"


def test_build_system_wires_listener_ticks_into_engine(tmp_path):
    path = str(tmp_path / "strategy_params.json")

    engine, listener = build_system("token-123", INSTRUMENT, params_path=path)

    assert listener.instruments == [INSTRUMENT]
    assert engine.params["instrument"] == INSTRUMENT

    entry_price = engine.params["entry_zone"]["low"]
    asyncio.run(listener.on_tick({"instrument": INSTRUMENT, "ltp": entry_price}))

    assert engine.position is not None
