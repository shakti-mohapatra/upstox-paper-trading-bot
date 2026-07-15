import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker.paper import PaperBroker


def test_paper_broker_starts_with_no_positions():
    broker = PaperBroker()
    assert broker.positions() == {}
