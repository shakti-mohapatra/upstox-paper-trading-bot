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

Early scaffold — `auth.py`'s OAuth2 login flow is real and tested;
`websocket_listener.py`, `execution_engine.py`, and `broker/paper.py` are
stubs pending the next build phase (see `PLAN.md`).

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
cp .env.example .env   # fill in your own Upstox api_key/api_secret
```

## Not investment advice

Instrument selection in this repo is driven by liquidity/tick-density for
testing purposes only, not a return prediction. Any real-money decision is
the user's own.
