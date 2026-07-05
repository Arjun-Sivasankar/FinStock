from __future__ import annotations

import time
from collections import deque

import requests

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
BACKOFF_SCHEDULE = [1, 2, 4]


class RateLimiter:
    def __init__(self, max_calls: int, period_seconds: float):
        self.max_calls = max_calls
        self.period = period_seconds
        self._calls: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self.period:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            sleep_for = self.period - (now - self._calls[0])
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.monotonic()
            while self._calls and now - self._calls[0] > self.period:
                self._calls.popleft()
        self._calls.append(now)


class FinnhubClient:
    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._limiter = RateLimiter(max_calls=55, period_seconds=60)

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "token": self._api_key}
        last_exc: Exception | None = None
        for delay in [0] + BACKOFF_SCHEDULE:
            if delay:
                self._sleep(delay)
            self._limiter.acquire()
            try:
                resp = requests.get(f"{self.BASE_URL}{path}", params=params, timeout=15)
            except requests.RequestException as exc:
                last_exc = exc
                continue
            if resp.status_code in RETRYABLE_STATUS:
                last_exc = RuntimeError(f"Finnhub {path} returned {resp.status_code}")
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Finnhub request to {path} failed after retries") from last_exc

    def quote(self, symbol: str) -> dict:
        return self._get("/quote", {"symbol": symbol})

    def candles(self, symbol: str, resolution: str, frm: int, to: int) -> dict:
        return self._get(
            "/stock/candle",
            {"symbol": symbol, "resolution": resolution, "from": frm, "to": to},
        )

    def earnings_calendar(self, symbol: str) -> dict:
        return self._get("/calendar/earnings", {"symbol": symbol})

    def insider_transactions(self, symbol: str) -> dict:
        return self._get("/stock/insider-transactions", {"symbol": symbol})

    def recommendation_trends(self, symbol: str) -> list[dict]:
        return self._get("/stock/recommendation", {"symbol": symbol})

    def price_target(self, symbol: str) -> dict:
        return self._get("/stock/price-target", {"symbol": symbol})

    def basic_financials(self, symbol: str) -> dict:
        return self._get("/stock/metric", {"symbol": symbol, "metric": "all"})
