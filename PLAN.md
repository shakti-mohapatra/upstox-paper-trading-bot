# JARVIS-Trader — Project Plan

**Status:** Fully wired, 100 tests green — **but see the warning below before trusting that.** Phase 0+1 done, Phase 2 search harness built. Live feed confirmed working 2026-07-16 (real ticks on disk).
**Next action:** `SONNET_BUILD_PLAN.md` → **START HERE** block (day-reset fix, archiver merge, then re-run the search). Not a paper session yet.
**Owner:** shaktibuilds
**Created:** 2026-07-15 · **Last revised:** 2026-07-16 (review session)
**Location:** `E:\Trading-bot`

> **⚠️ "100 tests green" is not evidence of anything.** Every test builds a
> fresh engine and feeds one day of ticks; the real path (live and backtest)
> is one engine instance eating months. **Zero tests cover how the code
> actually runs**, and the bot currently cannot trade a second day —
> `orb_high`/`trades_today`/`halted` never reset, and `halted` latches
> permanently. Full autopsy in `SONNET_BUILD_PLAN.md` §1. Read `§5 Rule 0`
> before acting on any number in this repo.

An algorithmic **paper-trading bot** for the Indian market (NSE) on the **Upstox
Developer API V2**. Paper-trades locally at ₹0 cost for ~1 month to tune a
strategy, then flips to real money on a free cloud host. Two-layer design: a
slow **analytical layer** sets strategy parameters; a fast **pure-Python
execution engine** acts on live ticks. The LLM never sits in the trade path.

---

## 1. Decisions locked (2026-07-15)

| Topic | Decision | Rationale |
|---|---|---|
| **Goal** | Paper now → real money in ~1 month | Tune over many paper sessions, then go live. |
| **Paper host** | Local PC (RTX 2060, 16GB), awake 9:15–3:30 IST | ₹0. Paper needs no static IP / VPS. |
| **Live host** | Oracle Cloud **Always-Free** ARM VM (free static IP) | ₹0/mo infra even live. Fallback: paid VPS ₹300–600/mo. |
| **Analytical brain** | **Stub / Python-rule first** (ponytail), Ollama later behind same interface | Prove engine before wiring an LLM. Zero new deps now. |
| **Segment** | **Equity cash (NSE)** first; abstract for F&O later | Simplest instruments; clone per market later. |
| **Instrument (v1)** | Default = most-traded liquid NSE large-cap (smoke test) | Selection driven by **liquidity + tick density**, NOT expected return. Final return-based pick is user's call, made before live. |
| **Paper fill model** | **Local fill sim** against live ticks (fill when a real tick crosses price) | More honest slippage than sandbox's idealized instant fills. |
| **Sandbox role** | Pre-live payload validation only, NOT the tuning loop | Sandbox = check order API plumbing before live. |
| **Order layer** | `BrokerAdapter` interface; `paper.py` now, `upstox_live.py` at go-live | Paper↔live swap = one line. |

---

## 2. Upstox API facts (verified 2026-07-15)

- **API is free.** All trading + market-data endpoints, ₹0. Need an Upstox
  demat (have it) + a self-serve **Developer App** for `api_key` / `api_secret`.
- **Auth:** OAuth2 auth-code flow. **Access token expires 3:30 AM daily**, no
  refresh token in standard flow → **re-login each morning**. Matches the
  "clean daily startup" constraint. (`upstox-totp` community pkg automates it;
  ToS-grey — decide before live.)
- **Static IP:** required for **live-money order placement only** (SEBI algo
  circular). Data APIs + sandbox orders are **not** IP-restricted → **paper
  needs no static IP.** One Primary + one Secondary IP allowed when live.
- **Rate limit:** max **10 orders/sec** — execution loop must throttle.
- **Sandbox:** free, 24/7, token 30-day validity, **one sandbox app/user**.
  Covers **order endpoints only** (place/modify/cancel). Market data always
  comes from the **live** WebSocket feed.
- **SDK:** official `upstox-python` exists with a sandbox/live toggle. We use
  raw `requests`/`websockets` where cleaner, SDK where it saves real work.

**Sources:** api-overview, rate-limiting, static-ip algo circular, sandbox,
get-token (expiry), upstox-python — all under
`https://upstox.com/developer/api-documentation/`.

---

## 3. Architecture

```
Ollama / rule (every 15 min, slow OK) ──writes──> strategy_params.json
                                                        │ (atomic read each loop)
Execution engine (pure Python, live ticks) ────────────┘ orders in microseconds
```

The two layers are decoupled by **`strategy_params.json`**. The broker is
decoupled by the **`BrokerAdapter`** interface. The LLM is never in the trade
path, so Ollama's speed is irrelevant (seconds of work, 15-min budget).

### Directory layout
```
E:\Trading-bot\
  PLAN.md                 # this file
  README.md               # quickstart (added at scaffold)
  requirements.txt
  .env.example            # api_key/secret/redirect placeholders (never commit real .env)
  config.py               # MODE=paper/live, risk params (daily max loss), NO static IP until live
  auth.py                 # OAuth2 daily login -> token; handles 3:30AM expiry / re-login
  websocket_listener.py   # live LTP + market depth feed (asyncio). Free, no static IP.
  execution_engine.py     # deterministic loop: ticks vs params, SL/target/trailing math
  analytical_bridge.py    # writes strategy_params.json (stub -> rule -> Ollama)
  strategy_params.json    # FROZEN schema, shared contract between layers
  broker\
    base.py               # BrokerAdapter interface: place/modify/cancel/positions
    paper.py              # local fill sim against live ticks (v1)
    upstox_live.py        # real REST orders (built at go-live, same interface)
  logs\                   # per-session trade + event logs
  tests\                  # minimal asserts per non-trivial module
```

### `strategy_params.json` — FROZEN schema (nail this on day 1)
Define every field the LLM would ever set; stub fills them statically now so
the Ollama swap later touches **zero** execution code.
```json
{
  "version": 1,
  "generated_at": "ISO-8601",
  "instrument": "NSE_EQ|INExxxxxxxxx",
  "enabled": true,
  "regime": "trend|range|avoid",
  "entry_zone": {"low": 0.0, "high": 0.0},
  "target_pct": 0.0,
  "stop_loss_pct": 0.0,
  "trail_pct": 0.0,
  "max_position_qty": 0,
  "notes": "why these params (LLM/rule rationale)"
}
```

---

## 4. Two things that MUST be right regardless of stub vs Ollama

1. **Freeze the JSON schema up front** (above). Stub writes static/rule values
   into the same fields the LLM will later fill → Ollama swap = no engine change.
2. **Atomic file write + read.** Analytical layer rewrites the JSON every 15 min
   while the engine reads it. Write temp file + `os.replace()` (atomic on
   Windows + Linux); engine reads the whole file each loop. Prevents reading a
   half-written file → garbage params → bad orders.

Both are ~5–10 lines, both needed even in the full Ollama version.

---

## 5. Risk / safety rules baked into the engine

- **Daily max-loss kill switch** in `config.py` → engine halts + flattens on breach.
- **10 orders/sec throttle** on the order path.
- **Reconnect handling** on the WebSocket (SEBI-grade robustness): auto-reconnect
  with backoff, resubscribe, gap-detect.
- **Token-expiry guard:** detect 3:30 AM expiry / 401 → stop cleanly, prompt re-login.
- **Paper fill honesty:** fill only when a real tick crosses the order price
  (model slippage), never idealized instant fills.
- **Comprehensive logging:** every tick-decision, order, fill, param reload,
  disconnect → `logs\` with timestamps.

---

## 6. Roadmap

| Phase | Deliverable | Proof |
|---|---|---|
| **0** | Create Upstox Developer App; fill `.env` | api_key/secret in hand |
| **1 (wk1)** | `auth.py` daily OAuth login + `websocket_listener.py` | Real LTP streaming locally |
| **2 (wk1–2)** | `execution_engine.py` + `broker/paper.py` + risk switches + logging | Simulated fills, SL/target/trail fire, kill switch works |
| **3 (wk2–3)** | `analytical_bridge.py` stub → simple Python regime rule writing params | Params reload live, atomic swap verified |
| **4 (wk3–4)** | Daily paper sessions; log every trade; tune params; clone config for a 2nd instrument | Abstraction proven on 2 instruments |
| **Go-live gate** | Sandbox payload test → Oracle free VM → register static IP → `upstox_live.py` → tiny real capital | Live order accepted from registered IP |

---

## 7. Cost

| Phase | Infra cost |
|---|---|
| Paper (month 1) | **₹0/mo** (local PC, free API, local brain) |
| Live | **₹0/mo** infra via Oracle Always-Free (free static IP); or ₹300–600/mo paid VPS. Plus per-trade brokerage + real capital. |

---

## 8. Open items / prerequisites

- [x] Create Upstox Developer App → get `api_key` + `api_secret` (Step 0, user).
- [x] Confirm default instrument = most-traded liquid NSE large-cap for smoke test.
      `NSE_EQ|INE002A01018` (RELIANCE) — liquidity pick for the paper smoke
      test only, not investment advice; final return-based pick is user's
      call before live.
- [x] Scaffold the files above.
- [x] Phase 1 real logic: `websocket_listener.py` (v3 feed, protobuf ltpc
      decode via `MarketDataFeed.proto`) + `execution_engine.py`
      (entry-zone/regime gating, target/stop-loss/trailing-stop exits) +
      `broker/paper.py` (instant fill at the real observed tick price).
- [x] Daily max-loss kill switch in `execution_engine.py` (checked on
      realized pnl at each exit, halts new entries) + reconnect-with-backoff
      (capped 60s) in `websocket_listener.run_forever()`.
- [x] Wired `auth.py` + `websocket_listener.py` + `execution_engine.py` +
      `broker/paper.py` into runnable `main.py` (`build_system()` +
      `run()`). 34 tests, TDD red-green throughout.
- [ ] Run first live paper session (market hours) to confirm real Upstox
      auth + v3 feed + fills end-to-end - nothing here has touched a real
      token or a real socket yet, only mocked tests.
- [ ] Decide on `upstox-totp` auto-login (ToS-grey) before live.
- [ ] Verify Oracle VM egress IP == reserved static IP before registering (at go-live).

---

## 9. Gotchas bank

- **The code has no concept of a trading day** — this is the root cause of four
  separate state bugs and it is the single most important thing to know about
  this codebase. Any per-day rule (opening range, max trades/day, daily loss,
  consecutive losses) is currently **lifetime-scoped**. Every rule in
  `trading_bot_mandatory_rules.md` is written in units of days; the code has no
  such unit.
- **`halted` latches forever.** Three consecutive losses kills the bot silently
  and permanently — it keeps consuming ticks and does nothing. If a session
  looks "quiet", check `halted` before believing the market was quiet.
- **Upstox revokes the previous access token on a new login for the same
  account.** Two processes calling `auth.login()` independently *cannot* both
  hold a valid session — whichever logs in last kills the other. The fix is one
  process, not a shared token file.
- **Log in BEFORE waiting for market open**, never after — otherwise you paste
  the OAuth code while the opening range burns.
- Token dies 3:30 AM daily, no refresh token → daily re-login.
- PC must stay awake 9:15–3:30 during paper phase (disable sleep) or ticks drop.
- Sandbox fills are idealized — use local fill sim for tuning, not sandbox.
- Static IP is the live gate — unregistered IP → live orders rejected.
- Final instrument pick (return-based) is the user's decision, made before live;
  not investment advice from the tool.
