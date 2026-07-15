import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution_engine import ExecutionEngine


def test_stores_broker_and_default_params_path():
    engine = ExecutionEngine(broker="fake-broker")
    assert engine.broker == "fake-broker"
    assert engine.params_path == "strategy_params.json"
