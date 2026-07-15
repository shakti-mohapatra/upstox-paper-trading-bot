"""Live LTP + market depth feed over Upstox's market-data websocket.

Real implementation needs: GET /v2/feed/market-data-feed/authorize (with the
access token) to get a signed ws URL, then connect + decode protobuf tick
messages. connect()/on_tick() are stubs until Phase 1 build (see PLAN.md).
"""


class WebSocketListener:
    def __init__(self, access_token: str, instruments: list[str]):
        self.access_token = access_token
        self.instruments = instruments

    async def connect(self):
        raise NotImplementedError("TODO Phase 1: authorize feed URL, connect, decode protobuf ticks")

    async def on_tick(self, tick: dict):
        raise NotImplementedError("TODO: dispatch tick to execution_engine")
