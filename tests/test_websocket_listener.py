import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from websocket_listener import WebSocketListener


def test_stores_access_token_and_instruments():
    listener = WebSocketListener("token-123", ["NSE_EQ|abc"])
    assert listener.access_token == "token-123"
    assert listener.instruments == ["NSE_EQ|abc"]
