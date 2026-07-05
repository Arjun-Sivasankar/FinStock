from __future__ import annotations

import time

import requests

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
BACKOFF_SCHEDULE = [2, 5, 10]


class Trading212Client:
    """Read-only client. Only ever issues requests.get — see
    tests/test_no_trading.py, which enforces this at the AST level."""

    def __init__(self, api_key: str, base_url: str):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{self._base_url}{path}"
        headers = {"Authorization": self._api_key}
        last_exc: Exception | None = None
        for delay in [0] + BACKOFF_SCHEDULE:
            if delay:
                self._sleep(delay)
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=15)
            except requests.RequestException as exc:
                last_exc = exc
                continue
            if resp.status_code in RETRYABLE_STATUS:
                last_exc = RuntimeError(f"T212 {path} returned {resp.status_code}")
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"T212 request to {path} failed after retries") from last_exc

    def get_cash(self) -> dict:
        return self._get("/equity/account/cash")

    def get_account_summary(self) -> dict:
        return self._get("/equity/account/summary")

    def get_portfolio(self) -> list[dict]:
        return self._get("/equity/portfolio")

    def get_order_history(self, **params) -> dict:
        return self._get("/equity/history/orders", params=params)

    def get_dividend_history(self, **params) -> dict:
        return self._get("/equity/history/dividends", params=params)
