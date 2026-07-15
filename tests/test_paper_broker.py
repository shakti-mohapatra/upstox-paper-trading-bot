import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker.paper import PaperBroker


def test_paper_broker_starts_with_no_positions():
    broker = PaperBroker()
    assert broker.positions() == {}


def test_buy_order_fills_immediately_and_opens_position():
    broker = PaperBroker()

    broker.place_order("NSE_EQ|TEST", "BUY", 10, 100.5)

    assert broker.positions() == {"NSE_EQ|TEST": 10}


def test_sell_order_closes_position():
    broker = PaperBroker()
    broker.place_order("NSE_EQ|TEST", "BUY", 10, 100.5)

    broker.place_order("NSE_EQ|TEST", "SELL", 10, 101.0)

    assert broker.positions() == {"NSE_EQ|TEST": 0}


def test_place_order_returns_unique_order_ids():
    broker = PaperBroker()

    id1 = broker.place_order("NSE_EQ|TEST", "BUY", 10, 100.5)
    id2 = broker.place_order("NSE_EQ|TEST", "BUY", 5, 100.6)

    assert id1 != id2


def test_cancel_order_on_already_filled_order_raises():
    broker = PaperBroker()
    order_id = broker.place_order("NSE_EQ|TEST", "BUY", 10, 100.5)

    try:
        broker.cancel_order(order_id)
        assert False, "expected ValueError"
    except ValueError:
        pass
