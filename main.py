"""Entrypoint: daily login, wire listener -> engine -> paper broker, run forever.

Two-layer design (see PLAN.md): analytical_bridge writes strategy_params.json
(stub for now, Ollama later - execution_engine never changes either way).
"""
import asyncio
import time as time_mod
from datetime import datetime, timedelta, timezone

import analytical_bridge
import auth
import config
import historical_data
import tick_archiver
from broker.paper import PaperBroker
from execution_engine import ExecutionEngine
from strategy import ORB_WINDOW_END, ORBStrategy, orb_high_from_candles
from websocket_listener import WebSocketListener

DEFAULT_INSTRUMENT = "NSE_EQ|INE002A01018"  # RELIANCE - liquidity pick for paper smoke test
IST = timezone(timedelta(hours=5, minutes=30))


def maybe_backfill_orb(strategy, instrument: str, access_token: str, now=None) -> None:
    """If starting after the 9:15-9:30 ORB window, seed orb_high from today's
    1-min candles instead of leaving it None (which blocks all entries forever)."""
    now = now or datetime.now(IST)
    if strategy.orb_high is not None or now.time() < ORB_WINDOW_END:
        return
    candles = historical_data.fetch_intraday(instrument, access_token)
    strategy.orb_high = orb_high_from_candles(candles)


def build_system(
    access_token: str,
    instrument: str = DEFAULT_INSTRUMENT,
    params_path: str = "strategy_params.json",
    trade_log_path: str = "logs/trades.csv",
    strategy=None,
    ticks_dir: str = "ticks",
):
    analytical_bridge.write_params(instrument, path=params_path)
    broker = PaperBroker()
    engine = ExecutionEngine(
        broker,
        params_path=params_path,
        daily_max_loss=config.DAILY_MAX_LOSS,
        trade_log_path=trade_log_path,
        strategy=strategy,
    )
    engine.load_params()

    listener = WebSocketListener(access_token, [instrument])
    archive_tick = tick_archiver.make_on_tick(instrument, dir=ticks_dir)

    async def on_tick(tick):
        await archive_tick(tick)  # unconditional, before the engine sees it
        engine.on_tick(tick)

    listener.on_tick = on_tick

    return engine, listener


async def run(access_token: str, instrument: str = DEFAULT_INSTRUMENT):
    strategy = ORBStrategy()
    maybe_backfill_orb(strategy, instrument, access_token)
    _, listener = build_system(access_token, instrument, strategy=strategy)
    await listener.run_forever()


def main():
    token = auth.login()  # login BEFORE waiting so the OAuth dance doesn't burn the ORB window
    wait = tick_archiver.seconds_until_market_open(datetime.now(IST))
    if wait > 0:
        print(f"Waiting {wait / 60:.1f} min for market open (9:15 IST)...")
        time_mod.sleep(wait)
    asyncio.run(run(token))


if __name__ == "__main__":
    main()
