# SONNET BUILD PLAN — JARVIS-Trader

**For:** a fresh Claude (Sonnet) session with no prior chat context. Read this
top to bottom before touching anything. Read `PLAN.md` (architecture, locked
decisions) alongside it — this file is the *build sequence*; `PLAN.md` is the
*design*.

**Owner:** shaktibuilds · **Repo:** `E:\Trading-bot` (public GitHub
`shakti-mohapatra/upstox-paper-trading-bot`) · **Written:** 2026-07-15 (planning
session, Opus). Nothing in this plan was implemented yet.

---

## 0. The one idea that shapes everything

Finding the best strategy is a **search** problem that needs *thousands* of
trades. Forward paper trading produces ~a few trades per day — far too slow to
search. So we split three machines the previous design fused into one:

| Machine | Purpose | Tool | Speed |
|---|---|---|---|
| **Search** | which strategy (solo/combined) is best? | **offline replay over historical data** | thousands of trades in seconds |
| **Validate** | does the shortlist survive real ticks/latency/fills? | **forward paper** (₹1L virtual) | a few trades/day, a shortlist only |
| **Execute** | real money | **live** (₹5k float) | real |

**User's own caveat, which is correct and non-negotiable in this plan:**
backtest performance ≠ live performance. Historical data *cannot contain a
regime that has not happened yet* (COVID crash, war shock, flash crash). A
strategy tuned on 2023–2025 data has never met those and will meet them first
with real money. Therefore:
- Backtesting only proves a strategy *isn't broken in known conditions*.
- Forward paper is the reality check for conditions history didn't hold.
- **Live must carry abnormal-condition circuit-breakers** (vol spike / gap /
  wide spread / feed gap → halt + flatten) that no backtest will ever force
  you to build. Build them anyway.

Sequence: **Phase 0 → 1 → 2 → 3 → 4.** Do not skip. Do not build a later phase's
feature early.

---

## 1. Current code state (what exists, what's broken)

Clean two-layer scaffold, 34 tests green, TDD throughout. Architecture is good;
the gaps are *completeness*, not rot. Deep review found these — fix them in the
phases below, not ad hoc:

| Sev | Finding | Where |
|---|---|---|
| 🔴 | **PnL ignores all costs** (brokerage/STT/exchange/GST/stamp). Every recorded number is optimistic. | `execution_engine.py:58` |
| 🔴 | **No slippage/spread** — fills at `ltp` for both sides. `ltpc` feed has no bid/ask, so spread is unmodelable until subscription → `full`/depth. | `broker/paper.py:16`, `websocket_listener.py:57` |
| 🔴 | **No intraday square-off / no time awareness** — MIS not flattened → auto-square penalty or delivery conversion (margin call risk). | `execution_engine.py:30` |
| 🔴 | **No position sizing** — `qty = max_position_qty = 1` hardcoded. No capital/risk/stop-distance sizing. | `execution_engine.py:42` |
| 🔴 | **Broker interface too thin for live** — `place_order(instrument, side, qty, price)` has no product (MIS/CNC), order type (MKT/LIMIT), validity. Live adapter can't be a one-line swap. | `broker/base.py:12` |
| 🔴 | **Basket can't trade** — engine filters ticks to a single `params["instrument"]` and holds one `self.position`. | `execution_engine.py:33`, `main.py:24` |
| 🔴 | **No strategy abstraction** — the entry/exit rule is hardcoded inside `on_tick`. Can't compare N strategies. | `execution_engine.py:30` |
| 🔴 | **Combined strategies corrupt state** — single `self.position`; two strategies on one stock overwrite each other. | `execution_engine.py:44` |
| 🔴 | **No replay/backtest path** — only forward live ticks. | (missing) |
| 🟡 | **No logging** — `logs/` empty; engine/broker log nothing. Can't tune what you didn't record. | engine/broker |
| 🟡 | **Params never reload** — `load_params()` runs once in `build_system`; `on_tick` never re-reads. | `main.py:22`, `execution_engine.py:30` |
| 🟡 | **Stub buys on first tick** — `entry_zone` = `0 … 1e6` → always true → blind entry at 9:15. | `analytical_bridge.py:21` |
| 🟡 | **Token-expiry not handled** — 401 swallowed by broad `except` in `run_forever` → hot reconnect loop, not "stop cleanly + re-login". | `websocket_listener.py:75` |
| 🟡 | **No overfitting guard** — testing many strategies × combos on limited data manufactures false winners. | (methodology) |
| 🟢 | Per-tick exceptions look like network drops; no gap-detect; `place_order(SELL)` with no prior BUY drives phantom short. | listener/paper |

`auth.py` is real and correct (`resp.json()["access_token"]` matches Upstox v2).
Atomic write in `analytical_bridge.py` is correct.

---

## 2. Values (single source of truth for this build)

Capital-independent strategy params (starting points; move to ATR later):

| Param | Value | Note |
|---|---|---|
| Stop-loss | **0.4–0.5%** from entry | fixed to start; `1.5 × ATR(14, 5-min)` later |
| Target | **≥1.5R**, floored at `2 × round-trip-cost%` | must clear costs, not just the stop |
| Trailing | activate after **+1R**, trail **0.3%** | |
| No new entries after | **15:00 IST** | |
| Hard square-off | **15:15 IST** | solvency, not tidiness |
| Max trades/day | **3–5** | cost control / anti-overtrading |
| Sizing | `qty = min( floor(risk / (entry × SL_frac)), floor(buying_power / entry) )` | risk-based, capped by affordability |

Capital-dependent (two profiles — **compute both**, always):

| Param | Paper (search + validate) | Live (later) |
|---|---|---|
| Capital | **₹1,00,000** | ₹5,000 |
| Risk / trade (1%) | ₹1,000 | ₹50 |
| Daily max loss (3%) | **₹3,000** → `DAILY_MAX_LOSS=3000` | ₹150 |
| MIS leverage | verify per stock (SEBI caps intraday ~5×) | same |

**Why both profiles:** you search/tune at ₹1L but deploy ₹5k — a 20× gap. Cost%,
sizing, and slippage all scale with size. Report every metric at **both** capital
levels so the ₹5k live-viability question is answered *before* real money. The
₹5k live gate passes only on **net-positive-after-costs at ₹5k sizing**, not ₹1L.

**Cost model** (rates in `config.py` as constants — statutory rates drift,
**verify against a real Upstox contract note before trusting**):

```
brokerage = min(20, 0.0005 * turnover)   # ₹20 or 0.05%, whichever lower (intraday)
stt       = 0.00025 * sell_turnover      # 0.025%, SELL side only
exchange  = 0.0000297 * turnover         # ~0.00297% per side (NSE — verify current)
sebi      = 0.000001 * turnover          # ₹10 / crore, per side
stamp     = 0.00003 * buy_turnover       # 0.003%, BUY side only
gst       = 0.18 * (brokerage + exchange + sebi)
net_pnl   = gross - buy_costs - sell_costs
```

---

## 3. Phases

Each phase: build the deliverable, prove it, leave one runnable self-check
(TDD — see §5). Do not start a phase until the previous one's proof passes.

### Phase 0 — Honest accounting layer (shared by backtest AND paper)
Everything downstream measures with these, so build them first.
- **Cost function** `costs(side, qty, price)` per §2; subtract in
  `realized_pnl`. Config-driven rates.
- **Trade log**: append one CSV row per fill —
  `ts, symbol, strategy, side, qty, intended, fill, gross, cost, net, reason`.
  Same format for backtest and paper (so results are comparable).
- **15:15 hard square-off** + no entries after 15:00: pass tick time into
  `on_tick`; force-exit any open position ≥ 15:15.
- **Off-first-tick entry**: replace the wide-open `entry_zone` stub with a real
  opening-range-breakout gate (record 9:15–9:30 high/low; enter on break) so
  nothing buys blindly at 9:15.
- **Position sizing** per §2 formula (risk-based, affordability-capped), replacing
  hardcoded `qty=1`.
- **`config.py` validation**: fail loudly if required `.env` vars are None.

*Proof:* a scripted tick sequence produces a CSV log with correct net-of-cost
PnL; square-off fires; kill switch fires at the daily-max threshold.

### Phase 1 — Strategy interface + replay harness + data
- **`Strategy` interface**: `signal(state) -> intent` (enter/exit/hold), pulled
  OUT of `on_tick`. Engine executes intents; strategy only decides. This is what
  makes N strategies comparable and combinable.
- **Replay harness** `backtest.py`: feed the *same* engine a CSV of historical
  candles instead of a live socket — same `on_tick`, different source. Runs a
  strategy over months of history in seconds, emitting the Phase-0 trade log +
  summary metrics (net PnL, cost%, win rate, avg R, max drawdown, #trades).
- **Historical data**: source it (see §4 open decision — candle vs tick,
  Upstox historical-candle API vs saved CSV). Decide fidelity before building the
  harness around it.

*Proof:* `python backtest.py --strategy orb --data reliance_<period>.csv` prints
a net-of-cost trade log + summary for one strategy over real history.

### Phase 2 — Strategy search (offline) with overfitting + regime guards
- Implement a starter set of strategies (confirm set with user, §4).
- **Walk-forward** validation (rolling train/test windows), not a single
  in-sample fit.
- **Out-of-sample holdout** kept untouched until the very end.
- **Minimum-trades threshold** (~30+) before any strategy is eligible to "win".
- **Regime coverage**: run across trending / ranging / high-vol / crash periods
  if data allows; a winner must survive more than one regime.
- Rank by **cost-adjusted** metrics at both ₹1L and ₹5k profiles. Then evaluate
  **combinations** (portfolio/ensemble) — needs the multi-strategy state from
  Phase 3's engine work or a simplified offline allocator; decide at that point.

*Proof:* a ranked table of strategies (solo + top combos) with OOS metrics; a
clearly documented shortlist of 2–3 survivors.

### Phase 3 — Forward paper validation (₹1L, multi-instrument, multi-strategy)
- Refactor engine to **multi-instrument** (positions keyed by instrument) and
  **multi-strategy** (per-strategy sub-accounts / allocator) — fixes the
  single-`self.position` corruption.
- Switch feed subscription to **`full`/depth** so bid/ask exists → honest
  slippage (buy at ask, sell at bid), not LTP-both-sides.
- Wire **params reload** (`on_tick` re-reads `strategy_params.json` atomically)
  so the analytical layer actually drives the engine.
- Run the shortlist forward on live ticks, paper fills, ₹1L. Compare forward
  results to the backtest — divergence here is the regime-gap signal.

*Proof:* shortlist runs a full session on real ticks; forward metrics logged and
compared to backtest; kill switch + square-off + circuit-breaker all fire in the
log.

### Phase 4 — Live gate (₹5k, real money — user-approved only)
- **Widen `BrokerAdapter`**: product (MIS/CNC), order type (MKT/LIMIT), validity
  — so `upstox_live.py` is a true swap.
- `upstox_live.py` real REST orders + 10 orders/sec throttle.
- **Circuit-breakers** (the regime guards): halt + flatten on vol spike / gap
  beyond threshold / spread beyond threshold / feed gap.
- Sandbox payload test → Oracle free VM → register static IP (verify egress IP ==
  reserved IP first) → tiny ₹5k live.
- **Gate:** net-positive-after-costs at ₹5k sizing across many forward-paper
  sessions. If ₹5k proves cost-unviable, the honest answer may be "raise the
  float or don't go live."

---

## 4. Open decisions

**Decided 2026-07-15 (session 5):**
1. **Historical data — RESOLVED.** Researched free tick-level NSE sources
   first (per standing rule, don't assume): NSE's own tick/order data is
   paid-SFTP only; Kaggle datasets are all OHLC, not tick; the one GitHub repo
   claiming "live tick data" (`ShabbirHasan1/NSE-Data`) is dead — `gh api`
   confirmed last push `2021-06-13`, plus GPL-3.0 (copyleft, bad fit once
   live code exists). **No credible free tick data exists.** Decision: use
   **Upstox historical-candle API V3, 1-min bars, back to Jan 2022** (free,
   official, same dev account already authed; paginate 1-month chunks per
   call) for Phase 1 backtest fidelity, **AND** start archiving real live
   ticks from `websocket_listener.py` from today onward (small addition,
   reuse the Phase-0 CSV trade-log pattern) so a true tick-fidelity dataset
   accumulates in parallel for later, higher-precision replay/validation —
   does not block Phase 1 starting now.
3. **Starter strategy set — RESOLVED for now.** Opening-range breakout (ORB)
   only, first Strategy interface implementation (Phase 1). Other candidates
   (VWAP mean-reversion, MA crossover, momentum) deferred to when Phase 2
   search actually needs more than one strategy to compare — ask again then.

**Still open — ask before Phase 2/4 needs them:**
2. **Final basket**: the 3–5 liquid large-caps. User's liquidity/return call.
   Default for now stays `NSE_EQ|INE002A01018` (RELIANCE) per Phase 1 lock.
4. **MIS leverage** multiple per stock (verify with Upstox) + live product type.
5. **Exact Upstox brokerage / statutory rates** — verify vs a real contract note.
6. **`upstox-totp` auto-login** (ToS-grey) — decide at the pre-live gate only.

---

## 5. Working conventions (this repo)

- **TDD Guard is wired** (`pyproject.toml: tdd_guard_project_root = "E:/"` — the
  session root, NOT the repo root; this gotcha already bit once). Test-first.
  Confirm red with `./.venv/Scripts/python.exe -m pytest <test> -v` **immediately
  before** each implementation write — `test.json` clears itself between calls.
- venv: `E:\Trading-bot\.venv` (gitignored). Use its python explicitly.
- **Do not commit or push unless the user explicitly asks.** Working tree was
  clean at `2ce6ee9`.
- **Never read out, print, or commit `.env`** — real api_key/secret live there.
- The **OAuth code paste / real broker login is the user's step**, not Claude's.
- **Paper only** until the user approves the Phase 4 live gate. No real orders,
  no paid calls, no leaving GPU/servers running.
- Ponytail: smallest diff that works; mark deliberate shortcuts with a
  `ponytail:` comment naming the ceiling + upgrade path.
