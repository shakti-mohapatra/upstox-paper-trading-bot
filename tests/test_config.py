import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as config_module


def reload_config():
    return importlib.reload(config_module)


def test_config_raises_when_api_key_missing(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("UPSTOX_API_KEY", raising=False)
    monkeypatch.setenv("UPSTOX_API_SECRET", "s")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "https://localhost:3000/callback")

    try:
        reload_config()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "UPSTOX_API_KEY" in str(e)


def test_config_raises_when_api_secret_missing(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("UPSTOX_API_KEY", "k")
    monkeypatch.delenv("UPSTOX_API_SECRET", raising=False)
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "https://localhost:3000/callback")

    try:
        reload_config()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "UPSTOX_API_SECRET" in str(e)


def test_config_raises_when_redirect_uri_missing(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("UPSTOX_API_KEY", "k")
    monkeypatch.setenv("UPSTOX_API_SECRET", "s")
    monkeypatch.delenv("UPSTOX_REDIRECT_URI", raising=False)

    try:
        reload_config()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "UPSTOX_REDIRECT_URI" in str(e)
