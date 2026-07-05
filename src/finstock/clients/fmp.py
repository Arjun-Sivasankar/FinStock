from __future__ import annotations

import time

import requests

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
NOT_ENTITLED_STATUS = {402, 403}
BACKOFF_SCHEDULE = [1, 2, 4]


class FMPNotEntitledError(Exception):
    """Raised when the current FMP plan doesn't include an endpoint."""


class FMPClient:
    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self.calls_made = 0

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _get(self, path: str, params: dict | None = None) -> list | dict:
        params = {**(params or {}), "apikey": self._api_key}
        last_exc: Exception | None = None
        for delay in [0] + BACKOFF_SCHEDULE:
            if delay:
                self._sleep(delay)
            try:
                resp = requests.get(f"{self.BASE_URL}{path}", params=params, timeout=15)
            except requests.RequestException as exc:
                last_exc = exc
                continue
            if resp.status_code in NOT_ENTITLED_STATUS:
                raise FMPNotEntitledError(f"FMP {path} not available on current plan")
            if resp.status_code in RETRYABLE_STATUS:
                last_exc = RuntimeError(f"FMP {path} returned {resp.status_code}")
                continue
            resp.raise_for_status()
            self.calls_made += 1
            return resp.json()
        raise RuntimeError(f"FMP request to {path} failed after retries") from last_exc

    def key_metrics(self, symbol: str) -> list[dict]:
        return self._get(f"/key-metrics/{symbol}", {"limit": 1})

    def ratios(self, symbol: str) -> list[dict]:
        return self._get(f"/ratios/{symbol}", {"limit": 1})
