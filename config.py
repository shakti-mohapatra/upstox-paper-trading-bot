import os

from dotenv import load_dotenv

load_dotenv()

MODE = os.getenv("MODE", "paper")  # paper | live

UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")
UPSTOX_API_SECRET = os.getenv("UPSTOX_API_SECRET")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI")

DAILY_MAX_LOSS = float(os.getenv("DAILY_MAX_LOSS", "1000"))  # rupees, kill switch
MAX_ORDERS_PER_SEC = 10
