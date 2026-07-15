"""Entrypoint: daily login, wire listener -> engine -> paper broker, run forever.

Two-layer design (see PLAN.md): analytical_bridge writes strategy_params.json
(stub for now, Ollama later - execution_engine never changes either way).
"""
import asyncio

import analytical_bridge
import auth
import config
from broker.paper import PaperBroker
from execution_engine import ExecutionEngine
from websocket_listener import WebSocketListener

DEFAULT_INSTRUMENT = "NSE_EQ|INE002A01018"  # RELIANCE - liquidity pick for paper smoke test


def build_system(access_token: str, instrument: str = DEFAULT_INSTRUMENT, params_path: str = "strategy_params.json"):
    analytical_bridge.write_params(instrument, path=params_path)
    broker = PaperBroker()
    engine = ExecutionEngine(broker, params_path=params_path, daily_max_loss=config.DAILY_MAX_LOSS)
    engine.load_params()

    listener = WebSocketListener(access_token, [instrument])

    async def on_tick(tick):
        engine.on_tick(tick)

    listener.on_tick = on_tick

    return engine, listener


async def run(access_token: str, instrument: str = DEFAULT_INSTRUMENT):
    _, listener = build_system(access_token, instrument)
    await listener.run_forever()


if __name__ == "__main__":
    token = auth.login()
    asyncio.run(run(token))
