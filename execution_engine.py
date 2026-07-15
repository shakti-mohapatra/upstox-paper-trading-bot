"""Deterministic loop: live ticks vs strategy_params.json -> SL/target/trailing orders.

load_params()/on_tick() are stubs until Phase 2 build (see PLAN.md roadmap).
Must read strategy_params.json atomically (whole-file read each loop) since
analytical_bridge rewrites it every 15 min via os.replace().
"""


class ExecutionEngine:
    def __init__(self, broker, params_path: str = "strategy_params.json"):
        self.broker = broker
        self.params_path = params_path

    def load_params(self) -> dict:
        raise NotImplementedError("TODO Phase 2: read + validate strategy_params.json")

    def on_tick(self, tick: dict):
        raise NotImplementedError("TODO Phase 2: SL/target/trailing logic against live tick")
