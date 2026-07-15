import os

from dotenv import load_dotenv

load_dotenv()

MODE = os.getenv("MODE", "paper")  # paper | live

def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"required .env var {name} is missing")
    return value


UPSTOX_API_KEY = _require("UPSTOX_API_KEY")
UPSTOX_API_SECRET = _require("UPSTOX_API_SECRET")
UPSTOX_REDIRECT_URI = _require("UPSTOX_REDIRECT_URI")

DAILY_MAX_LOSS = float(os.getenv("DAILY_MAX_LOSS", "1000"))  # rupees, kill switch
MAX_ORDERS_PER_SEC = 10
