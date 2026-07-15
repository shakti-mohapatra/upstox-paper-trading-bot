"""Daily Upstox OAuth2 login.

Access token expires 3:30 AM IST, no refresh token -> re-run this each morning.
"""
import requests

from config import UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_REDIRECT_URI

AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


def get_login_url() -> str:
    return (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={UPSTOX_API_KEY}"
        f"&redirect_uri={UPSTOX_REDIRECT_URI}"
    )


def exchange_code_for_token(code: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        headers={
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "code": code,
            "client_id": UPSTOX_API_KEY,
            "client_secret": UPSTOX_API_SECRET,
            "redirect_uri": UPSTOX_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def login() -> str:
    print("Open this URL, log in, then paste the `code=` value from the redirected address bar:")
    print(get_login_url())
    code = input("code: ").strip()
    token = exchange_code_for_token(code)
    print("Login OK, token acquired (expires 3:30 AM IST).")
    return token


if __name__ == "__main__":
    login()
