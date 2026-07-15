import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from websocket_listener import WebSocketListener, decode_feed_response
import MarketDataFeed_pb2 as pb


def test_stores_access_token_and_instruments():
    listener = WebSocketListener("token-123", ["NSE_EQ|abc"])
    assert listener.access_token == "token-123"
    assert listener.instruments == ["NSE_EQ|abc"]


def test_decode_feed_response_extracts_ltp_and_ltt_per_instrument():
    response = pb.FeedResponse()
    response.feeds["NSE_EQ|abc"].ltpc.ltp = 101.25
    response.feeds["NSE_EQ|abc"].ltpc.ltt = 1752640560000  # epoch ms
    raw = response.SerializeToString()

    result = decode_feed_response(raw)

    assert result == {"NSE_EQ|abc": {"ltp": 101.25, "ltt": 1752640560000}}


def test_authorize_returns_wss_url_using_bearer_token(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"authorized_redirect_uri": "wss://example.com/feed?code=abc"}}

    captured = {}

    def fake_get(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("websocket_listener.requests.get", fake_get)
    listener = WebSocketListener("token-123", ["NSE_EQ|abc"])

    ws_url = listener.authorize()

    assert ws_url == "wss://example.com/feed?code=abc"
    assert captured["headers"]["Authorization"] == "Bearer token-123"


class FakeWebSocket:
    def __init__(self, incoming):
        self.incoming = incoming
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self.incoming:
            yield item


class FakeConnect:
    def __init__(self, ws):
        self.ws = ws

    async def __aenter__(self):
        return self.ws

    async def __aexit__(self, *exc_info):
        return False


def test_connect_subscribes_then_decodes_and_dispatches_ticks(monkeypatch):
    response = pb.FeedResponse()
    response.feeds["NSE_EQ|abc"].ltpc.ltp = 101.25
    response.feeds["NSE_EQ|abc"].ltpc.ltt = 1784173560000  # 2026-07-16 09:16:00 IST
    fake_ws = FakeWebSocket([response.SerializeToString()])

    listener = WebSocketListener("token-123", ["NSE_EQ|abc"])
    monkeypatch.setattr(listener, "authorize", lambda: "wss://example.com/feed")
    monkeypatch.setattr("websocket_listener.websockets.connect", lambda url: FakeConnect(fake_ws))

    received = []

    async def fake_on_tick(tick):
        received.append(tick)

    listener.on_tick = fake_on_tick

    asyncio.run(listener.connect())

    subscribed = json.loads(fake_ws.sent[0])
    assert subscribed["method"] == "sub"
    assert subscribed["data"] == {"mode": "ltpc", "instrumentKeys": ["NSE_EQ|abc"]}
    assert received == [{"instrument": "NSE_EQ|abc", "ltp": 101.25, "ts": "2026-07-16T09:16:00+05:30"}]


def test_run_forever_retries_connect_with_backoff_until_max_retries(monkeypatch):
    listener = WebSocketListener("token-123", ["NSE_EQ|abc"])
    connect_calls = 0

    async def failing_connect():
        nonlocal connect_calls
        connect_calls += 1
        raise ConnectionError("boom")

    listener.connect = failing_connect

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    asyncio.run(listener.run_forever(max_retries=3, sleep_fn=fake_sleep))

    assert connect_calls == 3
    assert sleeps == [1, 2, 4]


def test_run_forever_logs_connect_failures(monkeypatch, caplog):
    listener = WebSocketListener("token-123", ["NSE_EQ|abc"])

    async def failing_connect():
        raise ConnectionError("boom")

    listener.connect = failing_connect

    async def fake_sleep(seconds):
        pass

    with caplog.at_level("ERROR"):
        asyncio.run(listener.run_forever(max_retries=1, sleep_fn=fake_sleep))

    assert "boom" in caplog.text


def test_run_forever_caps_backoff_at_60_seconds(monkeypatch):
    listener = WebSocketListener("token-123", ["NSE_EQ|abc"])

    async def failing_connect():
        raise ConnectionError("boom")

    listener.connect = failing_connect

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    asyncio.run(listener.run_forever(max_retries=10, sleep_fn=fake_sleep))

    assert max(sleeps) == 60


def test_run_forever_resets_backoff_after_a_clean_connect(monkeypatch):
    listener = WebSocketListener("token-123", ["NSE_EQ|abc"])
    calls = []

    async def flaky_connect():
        calls.append(1)
        if len(calls) == 2:
            return  # clean disconnect, no error
        raise ConnectionError("boom")

    listener.connect = flaky_connect

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    asyncio.run(listener.run_forever(max_retries=3, sleep_fn=fake_sleep))

    assert len(calls) == 3
    assert sleeps == [1, 1]
