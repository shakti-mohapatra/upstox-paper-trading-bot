"""Intraday transaction cost model (SONNET_BUILD_PLAN.md §2).

Rates verified against a real Upstox contract note before trusting -
statutory rates drift.
"""
BROKERAGE_RATE = 0.0005  # 0.05% of turnover
BROKERAGE_CAP = 20.0  # Rs20 per order, whichever is lower
STT_RATE = 0.00025  # 0.025%, SELL side only
EXCHANGE_RATE = 0.0000297  # ~0.00297% per side (NSE)
SEBI_RATE = 0.000001  # Rs10 / crore, per side
IPFT_RATE = 0.000001  # Rs0.10 / lakh, per side - separate from SEBI turnover fee
STAMP_RATE = 0.00003  # 0.003%, BUY side only
GST_RATE = 0.18  # on brokerage + exchange + sebi + ipft


def costs(side: str, qty: int, price: float) -> float:
    turnover = qty * price
    brokerage = min(BROKERAGE_CAP, BROKERAGE_RATE * turnover)
    exchange = EXCHANGE_RATE * turnover
    sebi = SEBI_RATE * turnover
    ipft = IPFT_RATE * turnover
    stt = STT_RATE * turnover if side == "SELL" else 0.0
    stamp = STAMP_RATE * turnover if side == "BUY" else 0.0
    gst = GST_RATE * (brokerage + exchange + sebi + ipft)
    return brokerage + exchange + sebi + ipft + stt + stamp + gst


def breakeven_win_rate(target_pct: float, stop_loss_pct: float, cost_pct: float) -> float:
    """Min win rate to break even, given cost as % of turnover (mandatory_rules.md §2)."""
    net_win = target_pct - cost_pct
    net_loss = stop_loss_pct + cost_pct
    return net_loss / (net_win + net_loss)
