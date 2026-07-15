"""Live LTP feed over Upstox's v3 market-data websocket.

authorize() gets a signed wss:// URL, connect() subscribes in ltpc mode and
decodes protobuf ticks (MarketDataFeed.proto), dispatching each to
on_tick() - a stub meant to be overridden/wired to execution_engine.on_tick.

connect() runs one session and returns when the socket closes; the 9:15-3:30
uptime requirement needs a reconnect-with-backoff loop around it, which
belongs in the orchestrator (main.py, not built yet) rather than here.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import requests
import websockets

import MarketDataFeed_pb2 as pb

AUTHORIZE_URL = "https://api.upstox.com/v3/feed/market-data-feed/authorize"
IST = timezone(timedelta(hours=5, minutes=30))

log = logging.getLogger(__name__)


def decode_feed_response(raw: bytes) -> dict[str, dict]:
    response = pb.FeedResponse()
    response.ParseFromString(raw)
    return {
        instrument: {"ltp": feed.ltpc.ltp, "ltt": feed.ltpc.ltt}
        for instrument, feed in response.feeds.items()
        if feed.HasField("ltpc")
    }


class WebSocketListener:
    def __init__(self, access_token: str, instruments: list[str]):
        self.access_token = access_token
        self.instruments = instruments

    def authorize(self) -> str:
        resp = requests.get(
            AUTHORIZE_URL,
            headers={"Authorization": f"Bearer {self.access_token}", "Accept": "*/*"},
        )
        resp.raise_for_status()
        return resp.json()["data"]["authorized_redirect_uri"]

    async def connect(self):
        ws_url = self.authorize()
        async with websockets.connect(ws_url) as ws:
            subscribe_msg = json.dumps(
                {
                    "guid": str(uuid.uuid4()),
                    "method": "sub",
                    "data": {"mode": "ltpc", "instrumentKeys": self.instruments},
                }
            )
            await ws.send(subscribe_msg)
            async for raw in ws:
                for instrument, feed in decode_feed_response(raw).items():
                    ts = datetime.fromtimestamp(feed["ltt"] / 1000, tz=IST).isoformat()
                    await self.on_tick({"instrument": instrument, "ltp": feed["ltp"], "ts": ts})

    async def on_tick(self, tick: dict):
        raise NotImplementedError("TODO: dispatch tick to execution_engine")

    async def run_forever(self, max_retries: int | None = None, sleep_fn=asyncio.sleep):
        attempt = 0
        tries = 0
        while max_retries is None or tries < max_retries:
            tries += 1
            try:
                await self.connect()
                attempt = 0
            except Exception:
                log.exception("websocket connect failed, retrying")
                await sleep_fn(min(2**attempt, 60))
                attempt += 1
