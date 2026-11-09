"""Every test runs offline: no paid API can be reached, and the user's settings are untouched."""

import urllib.request

import httpx
import pytest


class NetworkBlocked(httpx.TransportError):
    """Looks like a dead network to the code under test, so its fallbacks still run."""


def _blocked(*_a, **_k):
    raise NetworkBlocked("network is blocked in tests; inject a mock")


def _blocked_urlopen(*_a, **_k):
    raise OSError("network is blocked in tests; inject a mock")


@pytest.fixture(autouse=True)
def _offline_and_isolated(monkeypatch, tmp_path):
    for name in ("get", "post", "stream", "request"):
        monkeypatch.setattr(httpx, name, _blocked)
    monkeypatch.setattr(httpx.Client, "send", _blocked)
    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)
    monkeypatch.setenv("AD_SPY_CONFIG", str(tmp_path / "ad-spy-kit-settings.env"))
    for var in ("AD_SPY_TRANSCRIBE", "AD_SPY_TRANSCRIBE_MODEL", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
