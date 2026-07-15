import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from auth import exchange_code_for_token, get_login_url, login


def test_get_login_url_includes_client_id_and_redirect_uri():
    url = get_login_url()
    assert config.UPSTOX_API_KEY in url
    assert config.UPSTOX_REDIRECT_URI in url


def test_exchange_code_for_token_returns_access_token(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "fake-token-123"}

    monkeypatch.setattr("auth.requests.post", lambda *a, **kw: FakeResponse())

    token = exchange_code_for_token("some-code")

    assert token == "fake-token-123"


def test_login_prompts_for_code_and_returns_exchanged_token(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "pasted-code")
    monkeypatch.setattr("auth.exchange_code_for_token", lambda code: f"token-for-{code}")

    token = login()

    assert token == "token-for-pasted-code"
