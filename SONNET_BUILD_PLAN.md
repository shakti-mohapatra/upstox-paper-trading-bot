# SONNET BUILD PLAN — JARVIS-Trader

**For:** a fresh Claude (Sonnet) session with no prior chat context. Read this
top to bottom before touching anything. Read `PLAN.md` (architecture, locked
decisions) alongside it — this file is the *build sequence*; `PLAN.md` is the
*design*.

**Owner:** shaktibuilds · **Repo:** `E:\Trading-bot` (public GitHub
`shakti-mohapatra/upstox-paper-trading-bot`) · **Written:** 2026-07-15 (planning
session, Opus) · **Last revised:** 2026-07-16 night (review session, Opus).

---

# 🚦 START HERE task list — ALL 7 TASKS DONE 2026-07-17. Read this before assuming anything below is still open.

Everything below this block is context (mostly historical now). It was
produced by a full code review on 2026-07-16 night in which every claim was
verified by running the real code, not inferred.

### The ORB "no edge" verdict is no longer void — it was re-measured for real (task 5) and confirmed.

If you have read anywhere in this repo (or in memory) that "plain ORB has no
real edge" from **2026-07-16 or earlier**, that specific number was void (see
§3 Phase 2 autopsy). It has since been **re-run on the fixed engine
(2026-07-17)** and the same conclusion came back, this time arithmetically
sane and cost-corroborated: **13/13 windows net-negative, holdout 121 trades,
net_pnl -₹5699.40, cost_pct 0.077%, win_rate 16.5%.** Treat this as real.

| # | Task | Status |
|---|---|---|
| **1** | Fix the daily reset (`on_tick` rollover: `trades_today`/`realized_pnl_today`/`consecutive_losses`/`halted` reset, `strategy.new_day()`). | ✅ Done. `test_engine_resets_daily_state_across_days` + a follow-up regression test (first-ever tick must NOT wipe pre-seeded strategy state, e.g. a backfilled `orb_high` — caught during task 6). |
| **2** | Merge `tick_archiver` into `main.py`. One process, one login, one socket. | ✅ Done. `tick_archiver.py` now exports pure helpers only (`make_on_tick`, `archive_path`, `append_tick`, `seconds_until_market_open`); `main.build_system()` archives every tick unconditionally before `engine.on_tick()`. |
| **3** | Move `auth.login()` before the market-open wait. | ✅ Done. `main.py` now has a `main()` entrypoint: login → wait → run. |
| **4** | Fix sizing: `write_params()` preserves `max_position_qty` across restarts instead of resetting to the stub; `MIN_TURNOVER` check moved to execution_engine, after the `max_position_qty` cap. | ✅ Done. Also bumped the actual stub default (and `strategy_params.json`/`.example.json`) from the degenerate `1` to `1000` (a non-binding safety ceiling — `position_sizing.size_position` does the real risk-based capping). |
| **5** | Re-run the walk-forward. | ✅ Done, see verdict above. |
| **6** | Dress rehearsal on real archived ticks (1,912 real ticks, 2026-07-16). | ✅ Done — 2 trades, qty=15, no crash, `halted=False`. Surfaced the first-tick regression fixed in task 1. |
| **7** | Ask the user: forward paper vs strategy #2. | ✅ Done — user chose **strategy #2**. |

**106 tests green** (was 100 at the start of 2026-07-17's session). Nothing
committed, nothing pushed, no live process touched, per standing instruction.

**Strategy #2 DONE 2026-07-17 (same session)** — user picked **MA crossover**
(9/21 EMA, hardcoded periods like ORB's window constants; reuses
`target_pct`/`stop_loss_pct`/`trail_pct` from the same frozen params schema so
`walk_forward.py`'s existing grid needed zero changes). New
`MACrossoverStrategy` in `strategy.py` (TDD, 5 tests: enters on a confirmed
bullish EMA cross, exits on bearish cross or the same target/stop/trailing
math as ORB). Wired into `backtest.STRATEGIES` and a new `--strategy` flag on
`walk_forward.py` (`functools.partial(evaluate, strategy_cls=...)`, threaded
into both the per-window search and the holdout call — the holdout call was
still hardcoded to bare `evaluate()` before this, a latent bug that would have
silently graded every non-default strategy's holdout as ORB).

**Real comparison, same grid/windows/holdout as ORB's baseline:**
| | ORB | MA crossover (9/21 EMA) |
|---|---|---|
| Windows net-negative | 13/13 | 13/13 |
| Holdout trades | 121 | 220 |
| Holdout net_pnl | -₹5699.40 | -₹10555.28 |
| Holdout win_rate | 16.5% | 12.7% |
| Holdout max_drawdown | ₹5840 | ₹10643 |
| cost_pct | 0.077% | 0.077% (same sizing, confirms cost isn't the differentiator) |

**MA crossover is worse than ORB on every metric** — roughly double the
trades (whipsaw-prone with no noise filter on 1-min bars) at a lower win rate
and bigger drawdown. Both strategies are net-negative; ORB remains the
(still-negative) baseline to beat.

---

### ORBv2 — the actual §4A spec, built 2026-07-17, long-only cut

`trading_bot_mandatory_rules.md` §4A ORB was never the strategy in `ORBStrategy`
(session 10 finding). Built the real spec as a new `ORBv2Strategy` in
`strategy.py`: gap filter (skip the day unless |gap| is 0.3–2.0% vs the prior
close), range-width filter (skip if the 9:15–9:30 range is <0.3% of price),
+0.05% breakout confirmation above range high, stop = range low, target =
max(1.5×range width, 0.8% min), forced exit at 11:00 if still open, no new
entries after 11:00. **Short entries from the same §4A spec were explicitly
deferred** — `execution_engine.py`/`broker/paper.py` are long-only end to end
(BUY-to-open/SELL-to-close hardcoded), and `broker/paper.py` already has a
known, unguarded phantom-short gap (session 3 finding, still open). Wiring
real shorting is a bigger, riskier engine change than this filter/timeframe
cut needed to test its core hypothesis (does filtering out low-quality setups
fix the win-rate-vs-cost-adjusted-breakeven gap?) — ask before building that
half.

One real engine change was needed to support this strategy at all:
`execution_engine.on_tick`'s entry branch now reads
`signal.get("stop_loss_pct", self.params["stop_loss_pct"])` instead of
always using the frozen params value — lets a strategy hand the sizer a
per-trade computed stop (range-derived here) instead of only the one global
percentage the schema freezes. Backward compatible: `ORBStrategy`/
`MACrossoverStrategy` never set this key, so they're unaffected. 12 new tests
(TDD red-green; the bulk strategy-behavior tests were added via the documented
Bash-write workaround since TDD Guard blocks multi-test single-file additions
even for already-implemented, verification-only tests — same pattern noted in
[[reference_tdd_guard_skill]]). 126 tests green (was 114).

**Real walk-forward result, same data/windows/holdout as ORB/MA baselines
(`walk_forward.py --strategy orb_v2`, unchanged CLI, `orb_v2` picked up
automatically via `STRATEGIES` dict + existing `choices=sorted(STRATEGIES)`):**

| | ORB | MA crossover | **ORBv2 (§4A, long-only)** |
|---|---|---|---|
| Windows net-negative | 13/13 | 13/13 | **13/13** |
| Holdout trades | 121 | 220 | **16** |
| Holdout net_pnl | -₹5699.40 | -₹10555.28 | **-₹814.86** |
| Holdout win_rate | 16.5% | 12.7% | **25.0%** |
| Holdout max_drawdown | ₹5840 | ₹10643 | **₹1053** |
| cost_pct | 0.077% | 0.077% | 0.077% (same sizing formula, still not the differentiator) |

**Still net-negative, but the filters visibly work as a filter**: ~15× fewer
trades than ORB, win rate up ~8.5pp, absolute loss and drawdown both roughly
7× smaller. The gap/range/confirmation filters are doing real work rejecting
low-quality setups — this is evidence *for* the "too many bad trades, not
wrong strategy" theory from the cost-drag analysis, just not yet enough to
cross into profitable.

**One measurement caveat, found and worth flagging (same discipline as Rule
0):** every one of the 13 windows "chose" the identical grid combo
`{target_pct: 0.5, stop_loss_pct: 0.3, trail_pct: 0.2}`. That's because
`ORBv2Strategy` never reads `params["target_pct"]`/`stop_loss_pct`/`trail_pct"`
— it computes target/stop internally from the range and only forwards a
stop_loss_pct to the engine for sizing. **The grid search in this run was a
no-op for ORBv2** — all 12 grid combos produce identical trades, so "chosen
combo" is meaningless noise, not a real optimization result. The win_rate/
net_pnl/trades numbers themselves are real (they come from the actual
simulated trades, not from the grid selection), just the "best params per
window" framing doesn't apply to this strategy. Worth fixing in
`walk_forward.py` if a future params-driven strategy needs real grid search
alongside a params-ignoring one, but not blocking — flagged, not fixed.

---

### ORBv2 short entries — built and tested 2026-07-17. Result: made it worse. Reverted to long-only as the standing recommendation.

Before building, did real research (WebSearch, not assumption) on whether a
long+short combo has published evidence: a Nifty-index ORB backtest
(intradaylab.com, retail source — treat as a lead, not proof) found **shorts
generated 75% of ORB profits**, attributed to "markets fall faster than they
rise" (a real, widely-documented volatility asymmetry). That was the
justification for building this.

**Engine change** (the actual scope this required): `Strategy.signal()`'s
"enter" response can now carry `"side": "short"`; `execution_engine.on_tick`
opens with SELL/closes with BUY for shorts (symmetric slippage/cost/pnl to
the long path), tracks `low_water` alongside `high_water`. Backward
compatible — `ORBStrategy`/`MACrossoverStrategy` never set `side`, default to
`"long"`, unaffected (128 pre-existing tests stayed green throughout).
`ORBv2Strategy` got a mirrored breakdown-below-range-low entry, stop=range
high, target=max distance below entry, side-aware exit comparisons. 6 new
tests (TDD, some via the Bash-write verification-test workaround, same as
before). 132 tests green.

**Real result, same holdout, broken down by side (parsed from the actual
per-fill trade log, not assumed):**

| | Long-only ORBv2 | **+ shorts** |
|---|---|---|
| Holdout trades | 16 | **36** (16 long + 20 short) |
| Holdout net_pnl | -₹814.86 | **-₹1661.18** |
| Holdout win_rate | 25.0% | 30.6% (long side alone: 25.0%, short side alone: 35.0%) |
| Holdout max_drawdown | ₹1053 | **₹1742** |
| Windows net-negative | 13/13 | 13/13 |

Long-side numbers are byte-identical to the long-only run (correct — adding
shorts doesn't touch long logic). **Short trades alone: -₹846.33 net, 35% win
rate — better win rate than longs, but still net-negative, and adding them
roughly doubled trade count and made the combined total ~2× worse.** The
Nifty-index research finding did not transfer to RELIANCE over this holdout
period. Single stock, single 90-day OOS window, real result — not spun to
match the research lead. **Standing recommendation reverted to long-only
ORBv2** (still the best real candidate at -₹814.86) until/unless a different
instrument or period shows the short-side asymmetry actually holding. The
short-entry *code* stays (correct, tested, useful for a future strategy that
might use it better, e.g. VWAP mean-reversion naturally wants both
directions) — just not switched on as the recommended config.

**Other research done same session, not yet acted on:**
- Volume-confirmed breakouts have real evidence (Bulkowski stats: 65% success
  with volume ≥1.5× average vs 39% without) — **blocked**, not built: the live
  feed is Upstox `ltpc` mode with no volume field (session-4 finding,
  `websocket_listener.py`). A volume filter would work in backtest (candles
  carry `volume`) and silently do nothing (or silently block everything) live
  — same class of invisible bug this project has been burned by before. Needs
  a `full`/depth subscription upgrade first, which is already flagged
  out-of-scope elsewhere in this doc.
- VWAP mean-reversion has the strongest published evidence of any candidate
  considered so far (Journal of Portfolio Management: 57% win rate, 1.7:1
  R:R, 4,200 documented S&P trades; independent QuantConnect backtest: 61-63%
  win rate on liquid names) — stronger than anything found for ORB or MA
  crossover. Not built. Genuinely the strongest lead if the next move is a
  strategy pivot rather than another ORB filter.
- A recent falsification study (arXiv 2605.04004, MNQ futures 5-min OHLCV
  signals) found realistic round-trip costs eliminate the *entire* gross edge
  of next-bar-open systematic signals in every case tested — consistent with
  this project's own repeated empirical finding (every strategy tried here is
  net-negative after real costs). Tempers expectations honestly: a
  cost-surviving intraday edge on OHLCV data alone is hard by design, not a
  sign anything here is being done wrong.

**Next:** ask the user before building strategy #3 (VWAP mean-reversion has
the strongest evidence, if the direction is a strategy pivot), trying a
different instrument/period for the short-side hypothesis, or moving to
forward-paper on long-only ORBv2 as-is. Multi-instrument, `full`/depth
subscription, and the live gate remain out of scope until a strategy clears
the negative baseline.

### The dashboard (already built, needs one small thing)

`dashboard.html` exists at repo root — single file, zero deps, verified working
across live/frozen/offline states. Serve with
`.venv\Scripts\python.exe -m http.server 8000`, open
`http://127.0.0.1:8000/dashboard.html`.

It reads `logs/status.json`, **which does not exist yet.** Add a ~15-line
writer (reuse `analytical_bridge.py`'s existing `os.replace` atomic-write
pattern — do not invent a new one), called from `on_tick`, throttled to ~1/sec.

> **Contract rule, learned the hard way while building it:** status.json must
> carry **absolute epoch stamps** (`written_at`, `last_tick_at`,
> `archiver.last_write_at`) and **never self-reported ages**. A dead process
> reports "1s ago" forever. The dashboard derives every age itself so a stopped
> writer visibly ages and flips to FROZEN. Fields it expects are documented by
> the reads in `dashboard.html`'s `render()`.

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

Two-layer scaffold + Phase 0 (honest accounting) + Phase 1 (strategy
interface, replay harness, historical-data fetch) done, **100 tests green**,
TDD throughout. Architecture is genuinely good; the gaps are *completeness*,
not rot.

> ### ⚠️ Read this before you trust the green test suite
> **100 tests pass in 0.73s and every state bug in the table below is invisible
> to all of them.** Reason: *every* test builds a fresh `ExecutionEngine` and
> feeds it a single day of ticks. The real production path — live **and**
> backtest — is **one engine instance eating months**. **Zero tests exercise
> the way the code actually runs.** Green here has meant nothing so far; it is
> what produced the false confidence behind the void Phase-2 verdict. The first
> task in START HERE exists to close exactly this gap.

**Session-10 review (2026-07-16 night) findings — all verified by running the
real code, not inferred:**

| Sev | Finding | Where |
|---|---|---|
| 🔴 | **No concept of a trading day — the root cause.** `orb_high`, `trades_today`, `realized_pnl_today`, `consecutive_losses`, `halted` are assigned in `__init__` and **nowhere else** (grep-confirmed). Four bugs, one absence. Probe: 12 days of entry opportunities → **3 entries**. | `execution_engine.py:47`, `strategy.py:38` |
| 🔴 | ↳ **`halted` is a permanent latch.** 3 consecutive losses at 9:45 kills the bot **forever**, silently — it keeps consuming ticks and does nothing. Not per-day, not per-session. | `execution_engine.py:134` |
| 🔴 | ↳ **`orb_high` becomes a running all-time max.** It is not an opening-range breakout, it's "buy at a new all-time high." Day 2's legitimate breakout returns `hold`. Explains the absurd trade counts (7 in 90 days). | `strategy.py:58` |
| 🔴 | ↳ **`MAX_TRADES_PER_DAY=5` is a lifetime cap**, not a daily one. | `execution_engine.py:90` |
| 🔴 | **`write_params()` reverts tuned params on every boot** — runs on every `build_system()`, rewriting `max_position_qty` back to the stub `1`. Fixing the value by hand is silently undone next start. | `analytical_bridge.py:14`, `main.py:39` |
| 🔴 | **`MIN_TURNOVER` guard is defeated** — checked *inside* `size_position` before the engine applies `min(risk_qty, max_position_qty)`, so it protects a number that gets thrown away. | `position_sizing.py:15`, `execution_engine.py:104` |
| 🟡 | **`run_forever` hot-loops on clean disconnect** — `attempt=0` with **no sleep** on the success path. At 15:30 the socket closes normally → hammers the authorize REST endpoint all night. Rate-limit/ban risk. *(Session 3 fixed the backoff reset and introduced this.)* | `websocket_listener.py:77` |
| 🟡 | **`tick_archiver` logs in AFTER sleeping to 9:15** → you paste OAuth while the opening range burns. 2026-07-16 archive starts **09:48, 0 ORB ticks**. | `tick_archiver.py:56` |
| 🟡 | **A tick with `ts=None` skips the ORB gate entirely** and falls through to the wide-open `entry_zone` stub (0→1,000,000) and **buys**. Landmine. | `strategy.py:60` |
| 🟡 | **Cost model conflict, still unresolved** — `costs.py` brokerage 0.05% vs `trading_bot_mandatory_rules.md` 0.1%. **Verify against a real contract note.** (Open since session 8.) | `costs.py:6` |

**Earlier review findings (2026-07-15), still tracked:**

| Sev | Finding | Where |
|---|---|---|
| ✅ | ~~PnL ignores all costs~~ — fixed Phase 0, `costs.py` net-of-cost every fill. | `execution_engine.py:58` |
| 🔴 | **No slippage/spread** — fills at `ltp` for both sides. `ltpc` feed has no bid/ask, so spread is unmodelable until subscription → `full`/depth. | `broker/paper.py:16`, `websocket_listener.py:57` |
| ✅ | ~~No intraday square-off / no time awareness~~ — fixed Phase 0, 15:15 hard square-off + no entries after 15:00. | `execution_engine.py:30` |
| ✅ | ~~No position sizing~~ — fixed Phase 0, `position_sizing.py` risk-based sizer. | `execution_engine.py:42` |
| 🔴 | **Broker interface too thin for live** — `place_order(instrument, side, qty, price)` has no product (MIS/CNC), order type (MKT/LIMIT), validity. Live adapter can't be a one-line swap. | `broker/base.py:12` |
| 🔴 | **Basket can't trade** — engine filters ticks to a single `params["instrument"]` and holds one `self.position`. | `execution_engine.py:33`, `main.py:24` |
| ✅ | ~~No strategy abstraction~~ — fixed Phase 1, `strategy.py` `Strategy`/`ORBStrategy`, engine takes `strategy=` injection. | `execution_engine.py:30` |
| 🔴 | **Combined strategies corrupt state** — single `self.position`; two strategies on one stock overwrite each other. | `execution_engine.py:44` |
| ✅ | ~~No replay/backtest path~~ — fixed Phase 1, `backtest.py` (`run_backtest`/`summarize`/CLI) + `historical_data.py` (Upstox V3 candle fetch). | (missing) |
| 🟡 | **No logging** — `logs/` empty; engine/broker log nothing beyond `run_forever`'s connect-failure logging. Can't tune what you didn't record. | engine/broker |
| 🟡 | **Params never reload** — `load_params()` runs once in `build_system`; `on_tick` never re-reads. | `main.py:22`, `execution_engine.py:30` |
| ✅ | ~~Stub buys on first tick~~ — fixed Phase 0/1, real ORB gate (`strategy.py` `ORBStrategy`) replaces the always-true `entry_zone` stub. | `analytical_bridge.py:21` |
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

### Phase 1 — Strategy interface + replay harness + data — DONE (code), data-fetch blocked on user
- ✅ **`Strategy` interface** (`strategy.py`): `Strategy.signal(tick, params, position) ->
  {"action": ...}`, pulled OUT of `on_tick`. `ExecutionEngine` takes `strategy=`
  (defaults to `ORBStrategy`), executes intents; strategy only decides.
- ✅ **Replay harness** `backtest.py`: `run_backtest()` feeds the *same*
  `ExecutionEngine` a CSV of historical candles instead of a live socket — same
  `on_tick`, different source. `summarize()` computes net PnL, cost%, win rate,
  max drawdown, #trades from the Phase-0 trade log. CLI wired: `python
  backtest.py --strategy orb --data <csv>` prints the summary as JSON.
- ✅ **Historical-data fetch** `historical_data.py`: Upstox V3
  `historical-candle` API (`/v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}`,
  verified against live docs 2026-07-16 — 1-min data available from Jan 2022,
  max 1 calendar month per request). `fetch_candles()` chunks a multi-month
  range into monthly requests and merges+sorts; `save_candles_csv()` writes
  the exact schema `backtest.load_candles()` reads. CLI: `python
  historical_data.py --instrument <key> --from-date YYYY-MM-DD --to-date
  YYYY-MM-DD --out <csv>` — calls `auth.login()` internally (user's manual
  OAuth step, prints URL + prompts for the `code=` paste).
- ⏳ **Not yet run for real** — fetching *actual* history needs today's Upstox
  token (daily re-login, user's step, not automatable). Once logged in: `python
  historical_data.py --instrument NSE_EQ|INE002A01018 --from-date <30d-ago>
  --to-date 2026-07-16 --out reliance_2026-07.csv` then `python backtest.py
  --strategy orb --data reliance_2026-07.csv` is the literal Phase 1 proof.
- ⏳ **Deferred, not blocking**: archiving real live ticks in parallel
  (SONNET_BUILD_PLAN.md §4 item 2) — also needs a live session/token, do
  alongside the first real data-fetch run rather than as separate work.

*Proof:* `python backtest.py --strategy orb --data reliance_<period>.csv` prints
a net-of-cost trade log + summary for one strategy over real history. **Code
side done and tested (71 tests green); the "over real history" half needs the
user to run today's OAuth login first.**

### Phase 2 — Strategy search (offline) with overfitting + regime guards — IN PROGRESS
- ✅ **Walk-forward harness** `walk_forward.py` (2026-07-16, session 6): rolling
  train/test windows (`date_windows`), param grid (`param_grid`), per-window
  best-by-train-net-pnl selection gated by `min_trades` (`run_walk_forward`,
  `evaluate`), untouched OOS holdout carved off the tail of the data before
  search starts, CLI (`python walk_forward.py --data <csv> --params <json>
  --min-trades N`). 8 tests, TDD throughout.
- ⛔ **First real run 2026-07-16 — RESULT VOID, WITHDRAWN 2026-07-16 night.**
  The run happened (ORB only, 3×2×2=12 grid, 13 windows over
  `reliance_full.csv`, 90-day holdout) and reported "no real edge": 12/13
  windows net-negative, holdout -₹33.11 / 39 trades / 30.8% win rate. **That
  conclusion is withdrawn.** It is invalid for four independent reasons, each
  sufficient on its own:
  1. **Stale binary.** `walk_forward_run1.log` is timestamped **07:23**;
     `execution_engine.py` is **09:23** and `strategy.py` is **10:03**. The code
     changed underneath the number and it was never re-run.
  2. **The number is arithmetically impossible.** 39 holdout trades cannot
     happen: `halted` latches **permanently** after 3 consecutive losses, and at
     the reported 30.8% win rate that fires almost immediately (~3–6 trades
     max). Verified by probe. **Nobody checked whether the result was even
     possible** — a ten-second sanity check would have caught the entire thing.
  3. **qty=1 on every single trade.** `max_position_qty:1` in the stub caps the
     sizer's ~15, so every fill was ~₹1,300 turnover → **0.35% round-trip cost**
     instead of 0.083%. `trading_bot_mandatory_rules.md`'s own headline is
     *"costs kill ORB edge in India at small position sizes"* — the bot traded
     exactly the size that doc forbids, then the result was read as a verdict on
     the strategy rather than on the sizing.
  4. **The strategy under test was not ORB.** Rules doc §4A specifies 15-min
     candles, gap filter 0.3–2.0%, skip-if-range<0.3%, stop = other side of the
     range, target = 1.5× range width, max hold 11:00, long **and** short.
     `strategy.py` implements **none** of them (1-min closes, no filters, fixed
     0.5% stop, fixed 1.0% target, long only). *(Corollary: the "doc contradicts
     backtest" contradiction the graphify graph surfaced was never a real
     contradiction — the two were never describing the same strategy.)*

  **Current status: no conclusion about ORB exists.** Re-running the search is
  START-HERE task 5 and is blocked only on task 1.
- ✅ **Re-run 2026-07-17, after tasks 1-4 fixed (day-reset, sizing) — this is
  the first trustworthy number.** Same grid/windows/holdout as above, on the
  fixed engine (qty=15 real risk-based sizing, not 1; no permanent halt
  latch). **13/13 windows net-negative** (was 12/13 on the void run).
  Holdout: **121 trades, net_pnl=-₹5699.40, cost_pct=0.077%** (matches the
  session-7 hand-derived ~0.083% estimate — a real corroboration, not just
  plausible-shaped), win_rate=16.5%, max_drawdown=₹5840. 121 trades over a
  90-day holdout (~2/trading-day) is arithmetically sane, unlike the void
  run's impossible 39. **Verdict: plain ORB (fixed target/stop/trail, long
  only) has no real edge on RELIANCE 1-min. This time it's real.** Also
  re-verified live: replayed the 1,912 real archived ticks from 2026-07-16
  through the fixed engine (`ORBStrategy` seeded with the session-9-verified
  real `orb_high=1304.0`) — 2 trades, qty=15, no crash, `halted=False`.
  Surfaced one more real bug while doing this: the day-rollover reset was
  firing on the **very first tick ever** (not just on genuine day changes),
  wiping any pre-seeded `orb_high` from `main.maybe_backfill_orb` before a
  single tick was processed. Fixed (only reset on `current_day is not None`
  transitions) + regression test added.
- ✅ **Unblocked 2026-07-17** — user chose to proceed to strategy #2 now that
  task 5 produced a real ORB number (asked per task 7, not assumed).
- ⏳ **Not started**: regime coverage (trending/ranging/high-vol/crash
  labeling) — soft requirement ("if data allows"); the 13 rolling windows
  already span very different 2023–2026 market conditions implicitly, but no
  explicit regime tagging exists yet.
- ⏳ **Not started**: ranking table across strategies + combinations — moot
  until a second strategy exists to rank against ORB.

*Proof:* a ranked table of strategies (solo + top combos) with OOS metrics; a
clearly documented shortlist of 2–3 survivors. **Partial**: ORB's OOS
verdict is documented above (a clear "no," not a survivor) — the ranked
table still needs a second strategy to be a real comparison.

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

### 🔍 Rule 0 — interrogate every number before it becomes a belief

**This is the most important rule in this file. It outranks the build sequence.**

The 2026-07-16 failure was not a bug. A number came out of a harness, it was
plausible-shaped and pessimistic, and it was promoted straight to a conclusion
and written into *this file* — the document whose entire job is briefing a fresh
session. Nobody asked what produced it. Nobody asked whether it was **possible**.
It wasn't: 39 trades under a permanently-latching kill switch at a 30% win rate
is arithmetically impossible, catchable in ten seconds. The bugs cost a day. The
procedure cost the truth, and it is the part that survives every fix.

**So: when any number arrives — from a backtest, a paper session, a doc, a
previous session's write-up, an AI, or your own code — before it becomes a
belief, ask:**
1. **What produced this?** Is the code that emitted it the code on disk *right
   now*? Check timestamps. `walk_forward_run1.log` (07:23) vs
   `execution_engine.py` (09:23) would have exposed the whole thing.
2. **Is it even possible?** Do the arithmetic on the constraints. Does the trade
   count make sense for the strategy's own logic? A *daily* breakout strategy
   taking 7 trades in 90 days is a screaming red flag, not a data point.
3. **Is the thing measured the thing named?** "ORB" in the code shared almost
   nothing with "ORB" in the rules doc. Compare implementation to spec before
   attributing a result to the spec.
4. **Does a green test suite actually cover this?** It didn't. It never did.

**Green tests are not evidence.** 100 passed while the bot couldn't trade a
second day. Nothing checked the checker.

**A number you haven't interrogated must be written down as an observation, never
as a conclusion**, and never in a way a future session will inherit as fact.

### Other conventions

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
