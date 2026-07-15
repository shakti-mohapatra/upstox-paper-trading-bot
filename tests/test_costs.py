import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from costs import costs


def test_buy_leg_cost_includes_brokerage_exchange_sebi_stamp_and_gst_but_not_stt():
    # turnover = 10 * 100 = 1000, well under the Rs20 brokerage cap
    result = costs("BUY", qty=10, price=100.0)

    brokerage = 0.0005 * 1000
    exchange = 0.0000297 * 1000
    sebi = 0.000001 * 1000
    stamp = 0.00003 * 1000
    gst = 0.18 * (brokerage + exchange + sebi)
    expected = brokerage + exchange + sebi + stamp + gst

    assert result == pytest.approx(expected, rel=1e-9)


def test_sell_leg_cost_includes_stt_but_not_stamp():
    result = costs("SELL", qty=10, price=100.0)

    brokerage = 0.0005 * 1000
    exchange = 0.0000297 * 1000
    sebi = 0.000001 * 1000
    stt = 0.00025 * 1000
    gst = 0.18 * (brokerage + exchange + sebi)
    expected = brokerage + exchange + sebi + stt + gst

    assert result == pytest.approx(expected, rel=1e-9)


def test_brokerage_is_capped_at_rs20_for_large_turnover():
    # turnover = 100 * 1000 = 100000 -> 0.05% = 50, capped at 20
    result = costs("BUY", qty=100, price=1000.0)

    turnover = 100000.0
    brokerage = 20.0
    exchange = 0.0000297 * turnover
    sebi = 0.000001 * turnover
    stamp = 0.00003 * turnover
    gst = 0.18 * (brokerage + exchange + sebi)
    expected = brokerage + exchange + sebi + stamp + gst

    assert result == pytest.approx(expected, rel=1e-9)
