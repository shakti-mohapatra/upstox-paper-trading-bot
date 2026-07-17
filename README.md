# JARVIS-Trader

Algorithmic **paper-trading bot** for NSE equities on the [Upstox Developer
API v2](https://upstox.com/developer/api-documentation/open-api/). Trades
locally at zero cost to tune a strategy, then can flip to a real-money
execution path later.

## Architecture

Two layers, decoupled by a frozen JSON contract:

```
Ollama / rule (every 15 min, slow OK) ──writes──> strategy_params.json
                                                        │ (atomic read each loop)
Execution engine (pure Python, live ticks) ────────────┘ orders in microseconds
```

The analytical layer (currently a static stub, later a rule engine, later a
local LLM) never sits in the trade path — the execution engine just reads
whatever is in `strategy_params.json` and acts on live ticks. Broker access
goes through a `BrokerAdapter` interface (`broker/paper.py` for local paper
fills, a live adapter can be dropped in later behind the same interface).

## Status

**Work in progress — paper trading only, never run with real money.**

Live Upstox feed confirmed working (real NSE ticks streaming to disk). OAuth,
websocket listener, execution engine, paper fill sim, cost model, position
sizing, CSV trade log, a replay/backtest harness, and a walk-forward search
with an out-of-sample holdout all exist. 100 tests green.

**Known broken (fix in progress):** the engine has no concept of a trading day
— per-day limits and the opening range never reset, and the kill switch latches
permanently. Consequently **no trustworthy backtest result exists yet**, and
any strategy verdict you find in this repo's history is withdrawn. See
`SONNET_BUILD_PLAN.md` → START HERE.

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
cp .env.example .env   # fill in your own Upstox api_key/api_secret
```

Run everything through the venv's python explicitly (`.venv\Scripts\python.exe
main.py`) — the global python on this machine lacks the deps.

## Dashboard

```bash
.venv/Scripts/python.exe -m http.server 8000
# open http://127.0.0.1:8000/dashboard.html
```

Single file, no dependencies. Reads `logs/status.json` (writer not yet built —
see START HERE). Surfaces the states that fail *silently*: kill-switch halts, a
stale feed, a missed opening range, and whether the tick archiver is alive.

## Not investment advice

Instrument selection in this repo is driven by liquidity/tick-density for
testing purposes only, not a return prediction. Any real-money decision is
the user's own.
