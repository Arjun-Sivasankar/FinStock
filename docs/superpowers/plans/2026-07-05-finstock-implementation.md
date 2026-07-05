# FinStock Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strictly read-only Python tool that pulls the user's Trading 212 portfolio plus Finnhub/FMP market data, runs rule-based fundamental + screener analysis, writes a dated markdown report with change-tracking, and pushes a brief ntfy.sh notification — scheduled twice daily via Windows Task Scheduler.

**Architecture:** A `src/finstock` package with three isolated API clients (Trading 212 read-only, Finnhub, FMP), pure-function analysis modules (technicals, screener, holdings), a JSON-snapshot-based change-detection module, a markdown report renderer, an ntfy notifier, and a `main.py` orchestrator. Every module is unit-tested with fixed fake data; no test hits a live API. A dedicated guardrail test enforces the no-trading constraint at the AST level.

**Tech Stack:** Python 3.11+, uv (project/deps), `requests`, `pyyaml`, `python-dotenv`, `pytest`, `responses` (HTTP mocking).

**Spec:** `docs/superpowers/specs/2026-07-05-finstock-research-tool-design.md`

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config/config.yaml`
- Create: `src/finstock/__init__.py`
- Create: `src/finstock/clients/__init__.py`
- Create: `src/finstock/analysis/__init__.py`
- Create: `README.md`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "finstock"
version = "0.1.0"
description = "Personal read-only investment research tool"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "responses>=0.25",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/finstock"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

- [ ] **Step 2: Create `.gitignore`**

```
.venv/
.env
data/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: Create `.env.example`**

```
T212_API_KEY=
FINNHUB_API_KEY=
FMP_API_KEY=
NTFY_TOPIC=
```

- [ ] **Step 4: Create `config/config.yaml`**

```yaml
t212_env: demo

benchmark_ticker: SPY

watchlist:
  - MSFT
  - GOOGL
  - NVDA

ticker_overrides: {}

screener:
  weights:
    value: 0.40
    quality: 0.35
    momentum: 0.25

change_detection:
  price_move_pct: 5.0
  pe_band_pct: 15.0

notify:
  schedule_times: ["08:00", "18:00"]
```

- [ ] **Step 5: Create empty package `__init__.py` files**

Create `src/finstock/__init__.py`, `src/finstock/clients/__init__.py`, `src/finstock/analysis/__init__.py` — all empty.

- [ ] **Step 6: Create a minimal `README.md`**

```markdown
# FinStock

A personal, strictly read-only investment research tool. Pulls Trading 212
portfolio data plus Finnhub/FMP market data, runs rule-based analysis, and
writes a dated markdown report twice a day. It never places, modifies, or
cancels orders — see `docs/superpowers/specs/2026-07-05-finstock-research-tool-design.md`.

## Setup

1. `uv sync`
2. Copy `.env.example` to `.env` and fill in your API keys
3. Edit `config/config.yaml` for your watchlist and preferences
4. `uv run python -m finstock.main`
5. To schedule twice-daily runs: `powershell scripts/register_task_scheduler.ps1`
```

- [ ] **Step 7: Run `uv sync` to create the virtualenv and lock file**

Run: `cd c:/MySPACE/FinanceStock && uv sync`
Expected: creates `.venv/` and `uv.lock` with no errors.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore .env.example config/config.yaml src/finstock/__init__.py src/finstock/clients/__init__.py src/finstock/analysis/__init__.py README.md uv.lock
git commit -m "chore: scaffold finstock project with uv"
```

---

## Task 2: Config loader

**Files:**
- Create: `src/finstock/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import textwrap
from pathlib import Path

from finstock.config import load_settings


def test_load_settings_reads_yaml_and_env(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(textwrap.dedent("""\
        t212_env: demo
        benchmark_ticker: SPY
        watchlist: [MSFT, GOOGL]
        ticker_overrides:
          VOD_LON_EQ: VOD.L
        screener:
          weights:
            value: 0.4
            quality: 0.35
            momentum: 0.25
        change_detection:
          price_move_pct: 5.0
          pe_band_pct: 15.0
        notify:
          schedule_times: ["08:00", "18:00"]
    """))
    env_path = tmp_path / ".env"
    env_path.write_text(
        "T212_API_KEY=t212-key\n"
        "FINNHUB_API_KEY=finnhub-key\n"
        "FMP_API_KEY=fmp-key\n"
        "NTFY_TOPIC=my-topic\n"
    )

    settings = load_settings(config_path=config_path, env_path=env_path)

    assert settings.t212_env == "demo"
    assert settings.t212_api_key == "t212-key"
    assert settings.benchmark_ticker == "SPY"
    assert settings.watchlist == ["MSFT", "GOOGL"]
    assert settings.ticker_overrides == {"VOD_LON_EQ": "VOD.L"}
    assert settings.screener_weights.value == 0.4
    assert settings.change_detection.price_move_pct == 5.0
    assert settings.notify.ntfy_topic == "my-topic"
    assert settings.notify.schedule_times == ["08:00", "18:00"]
    assert settings.t212_base_url == "https://demo.trading212.com/api/v0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.config'`

- [ ] **Step 3: Write `src/finstock/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class ScreenerWeights:
    value: float
    quality: float
    momentum: float


@dataclass
class ChangeDetectionThresholds:
    price_move_pct: float
    pe_band_pct: float


@dataclass
class NotifyConfig:
    ntfy_topic: str
    schedule_times: list[str]


@dataclass
class Settings:
    t212_env: str
    t212_api_key: str
    finnhub_api_key: str
    fmp_api_key: str
    benchmark_ticker: str
    watchlist: list[str]
    ticker_overrides: dict[str, str]
    screener_weights: ScreenerWeights
    change_detection: ChangeDetectionThresholds
    notify: NotifyConfig

    @property
    def t212_base_url(self) -> str:
        if self.t212_env == "live":
            return "https://live.trading212.com/api/v0"
        if self.t212_env == "demo":
            return "https://demo.trading212.com/api/v0"
        raise ValueError(f"Unknown t212_env: {self.t212_env!r}")


def load_settings(
    config_path: Path | str = "config/config.yaml",
    env_path: Path | str = ".env",
) -> Settings:
    load_dotenv(env_path)
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    return Settings(
        t212_env=raw["t212_env"],
        t212_api_key=os.environ["T212_API_KEY"],
        finnhub_api_key=os.environ["FINNHUB_API_KEY"],
        fmp_api_key=os.environ["FMP_API_KEY"],
        benchmark_ticker=raw["benchmark_ticker"],
        watchlist=list(raw.get("watchlist", [])),
        ticker_overrides=dict(raw.get("ticker_overrides") or {}),
        screener_weights=ScreenerWeights(**raw["screener"]["weights"]),
        change_detection=ChangeDetectionThresholds(**raw["change_detection"]),
        notify=NotifyConfig(
            ntfy_topic=os.environ["NTFY_TOPIC"],
            schedule_times=list(raw["notify"]["schedule_times"]),
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finstock/config.py tests/test_config.py
git commit -m "feat: add config loader for .env + config.yaml"
```

---

## Task 3: Data models and ticker mapping

**Files:**
- Create: `src/finstock/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from finstock.models import derive_symbol


def test_derive_symbol_strips_t212_suffix():
    assert derive_symbol("AAPL_US_EQ", {}) == "AAPL"


def test_derive_symbol_uses_override_when_present():
    overrides = {"VOD_LON_EQ": "VOD.L"}
    assert derive_symbol("VOD_LON_EQ", overrides) == "VOD.L"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.models'`

- [ ] **Step 3: Write `src/finstock/models.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field


def derive_symbol(t212_code: str, overrides: dict[str, str]) -> str:
    if t212_code in overrides:
        return overrides[t212_code]
    return t212_code.split("_")[0]


@dataclass
class Holding:
    t212_ticker: str
    symbol: str
    quantity: float
    average_price: float
    current_price: float
    ppl: float


@dataclass
class Fundamentals:
    symbol: str
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    fcf_yield: float | None = None
    roe: float | None = None
    debt_to_equity: float | None = None
    revenue_growth_yoy: float | None = None
    net_margin: float | None = None
    source_notes: list[str] = field(default_factory=list)


@dataclass
class TechnicalSnapshot:
    symbol: str
    price: float
    ma_50: float | None = None
    ma_200: float | None = None
    rsi_14: float | None = None


@dataclass
class ScreenerResult:
    symbol: str
    composite_score: float
    value_score: float
    quality_score: float
    momentum_score: float
    reasoning: list[str]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finstock/models.py tests/test_models.py
git commit -m "feat: add data models and T212 ticker mapping"
```

---

## Task 4: Trading 212 read-only client

**Files:**
- Create: `src/finstock/clients/trading212.py`
- Test: `tests/clients/test_trading212.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/clients/test_trading212.py
import responses

from finstock.clients.trading212 import Trading212Client


@responses.activate
def test_get_portfolio_returns_json():
    responses.get(
        "https://demo.trading212.com/api/v0/equity/portfolio",
        json=[{"ticker": "AAPL_US_EQ", "quantity": 10}],
        status=200,
    )
    client = Trading212Client(api_key="key", base_url="https://demo.trading212.com/api/v0")

    result = client.get_portfolio()

    assert result == [{"ticker": "AAPL_US_EQ", "quantity": 10}]
    assert responses.calls[0].request.headers["Authorization"] == "key"


@responses.activate
def test_get_cash_retries_on_429_then_succeeds():
    responses.get(
        "https://demo.trading212.com/api/v0/equity/account/cash",
        status=429,
    )
    responses.get(
        "https://demo.trading212.com/api/v0/equity/account/cash",
        json={"free": 100.0},
        status=200,
    )
    client = Trading212Client(api_key="key", base_url="https://demo.trading212.com/api/v0")
    client._sleep = lambda seconds: None  # skip real sleeps in test

    result = client.get_cash()

    assert result == {"free": 100.0}


@responses.activate
def test_get_cash_raises_after_exhausting_retries():
    for _ in range(4):
        responses.get(
            "https://demo.trading212.com/api/v0/equity/account/cash",
            status=429,
        )
    client = Trading212Client(api_key="key", base_url="https://demo.trading212.com/api/v0")
    client._sleep = lambda seconds: None

    try:
        client.get_cash()
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/clients/test_trading212.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.clients.trading212'`

- [ ] **Step 3: Write `src/finstock/clients/trading212.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/clients/test_trading212.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/finstock/clients/trading212.py tests/clients/test_trading212.py
git commit -m "feat: add read-only Trading 212 client with retry/backoff"
```

---

## Task 5: No-trading guardrail test

**Files:**
- Create: `tests/test_no_trading.py`

- [ ] **Step 1: Write `tests/test_no_trading.py`**

This test has no "make it pass" cycle in the usual TDD sense — it validates
existing code from Task 4 onward and must stay green for the life of the
project.

```python
import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parent.parent / "src" / "finstock"
FORBIDDEN_HTTP_METHODS = {"post", "put", "patch", "delete"}


def _requests_attr_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in FORBIDDEN_HTTP_METHODS
            and isinstance(node.value, ast.Name)
            and node.value.id == "requests"
        ):
            yield node


def test_trading212_client_only_uses_requests_get():
    path = SRC_ROOT / "clients" / "trading212.py"
    tree = ast.parse(path.read_text())
    offenders = list(_requests_attr_calls(tree))
    assert not offenders, (
        f"trading212.py must never call requests.{{post,put,patch,delete}}, "
        f"found at lines {[n.lineno for n in offenders]}"
    )


def test_no_order_placement_endpoint_referenced_anywhere():
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text()
        assert "/equity/orders" not in text, (
            f"{path} references the order-placement endpoint /equity/orders"
        )


def test_only_notify_module_uses_requests_post():
    for path in SRC_ROOT.rglob("*.py"):
        if path.name == "notify.py":
            continue
        tree = ast.parse(path.read_text())
        offenders = list(_requests_attr_calls(tree))
        assert not offenders, (
            f"{path} calls requests.{{post,put,patch,delete}} at lines "
            f"{[n.lineno for n in offenders]} — only notify.py may do this"
        )
```

- [ ] **Step 2: Run test to verify it passes against current code**

Run: `uv run pytest tests/test_no_trading.py -v`
Expected: PASS (3 passed) — confirms Task 4's client is already compliant.

- [ ] **Step 3: Commit**

```bash
git add tests/test_no_trading.py
git commit -m "test: add AST-based guardrail against order-placement code"
```

---

## Task 6: Finnhub client

**Files:**
- Create: `src/finstock/clients/finnhub.py`
- Test: `tests/clients/test_finnhub.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/clients/test_finnhub.py
import responses

from finstock.clients.finnhub import FinnhubClient


@responses.activate
def test_quote_includes_api_token_and_symbol():
    responses.get(
        "https://finnhub.io/api/v1/quote",
        json={"c": 150.0},
        status=200,
    )
    client = FinnhubClient(api_key="fh-key")

    result = client.quote("AAPL")

    assert result == {"c": 150.0}
    req = responses.calls[0].request
    assert "token=fh-key" in req.url
    assert "symbol=AAPL" in req.url


@responses.activate
def test_insider_transactions_retries_on_500():
    responses.get(
        "https://finnhub.io/api/v1/stock/insider-transactions",
        status=500,
    )
    responses.get(
        "https://finnhub.io/api/v1/stock/insider-transactions",
        json={"data": []},
        status=200,
    )
    client = FinnhubClient(api_key="fh-key")
    client._sleep = lambda seconds: None

    result = client.insider_transactions("AAPL")

    assert result == {"data": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/clients/test_finnhub.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.clients.finnhub'`

- [ ] **Step 3: Write `src/finstock/clients/finnhub.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/clients/test_finnhub.py -v`
Expected: PASS

- [ ] **Step 5: Run the full no-trading guardrail suite again**

Run: `uv run pytest tests/test_no_trading.py -v`
Expected: PASS — `finnhub.py` only uses `requests.get`, so it stays compliant.

- [ ] **Step 6: Commit**

```bash
git add src/finstock/clients/finnhub.py tests/clients/test_finnhub.py
git commit -m "feat: add Finnhub client with rate limiting and retry"
```

---

## Task 7: FMP client with budget-aware degradation

**Files:**
- Create: `src/finstock/clients/fmp.py`
- Test: `tests/clients/test_fmp.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/clients/test_fmp.py
import pytest
import responses

from finstock.clients.fmp import FMPClient, FMPNotEntitledError


@responses.activate
def test_key_metrics_increments_calls_made():
    responses.get(
        "https://financialmodelingprep.com/api/v3/key-metrics/AAPL",
        json=[{"peRatio": 18.0}],
        status=200,
    )
    client = FMPClient(api_key="fmp-key")

    result = client.key_metrics("AAPL")

    assert result == [{"peRatio": 18.0}]
    assert client.calls_made == 1


@responses.activate
def test_not_entitled_response_raises_without_retry():
    responses.get(
        "https://financialmodelingprep.com/api/v3/ratios/AAPL",
        status=403,
    )
    client = FMPClient(api_key="fmp-key")

    with pytest.raises(FMPNotEntitledError):
        client.ratios("AAPL")

    assert len(responses.calls) == 1  # no retry on 403
    assert client.calls_made == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/clients/test_fmp.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.clients.fmp'`

- [ ] **Step 3: Write `src/finstock/clients/fmp.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/clients/test_fmp.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finstock/clients/fmp.py tests/clients/test_fmp.py
git commit -m "feat: add FMP client with plan-degradation handling"
```

---

## Task 8: Technicals (moving averages, RSI)

**Files:**
- Create: `src/finstock/analysis/technicals.py`
- Test: `tests/analysis/test_technicals.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/analysis/test_technicals.py
from finstock.analysis.technicals import rsi, simple_moving_average


def test_simple_moving_average_over_window():
    prices = [10, 20, 30, 40, 50]
    assert simple_moving_average(prices, window=3) == 40.0  # avg of 30,40,50


def test_simple_moving_average_returns_none_when_insufficient_data():
    assert simple_moving_average([10, 20], window=5) is None


def test_rsi_all_gains_is_100():
    prices = [float(i) for i in range(1, 16)]  # strictly increasing
    assert rsi(prices, period=14) == 100.0


def test_rsi_returns_none_when_insufficient_data():
    assert rsi([1.0, 2.0], period=14) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/analysis/test_technicals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.analysis.technicals'`

- [ ] **Step 3: Write `src/finstock/analysis/technicals.py`**

```python
from __future__ import annotations


def simple_moving_average(prices: list[float], window: int) -> float | None:
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = prices[-i] - prices[-i - 1]
        if delta >= 0:
            gains.append(delta)
        else:
            losses.append(-delta)
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/analysis/test_technicals.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finstock/analysis/technicals.py tests/analysis/test_technicals.py
git commit -m "feat: add moving average and RSI technical indicators"
```

---

## Task 9: Screener scoring

**Files:**
- Create: `src/finstock/analysis/screener.py`
- Test: `tests/analysis/test_screener.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/analysis/test_screener.py
from finstock.analysis.screener import ScreenerInput, score_universe

WEIGHTS = {"value": 0.40, "quality": 0.35, "momentum": 0.25}


def test_cheaper_higher_quality_stock_ranks_above_expensive_weak_one():
    inputs = [
        ScreenerInput(
            symbol="CHEAP", pe_ratio=10.0, pb_ratio=1.0, fcf_yield=0.08,
            roe=0.25, debt_to_equity=0.3, ma_50=95.0, ma_200=90.0,
            rsi_14=50.0, price=100.0,
        ),
        ScreenerInput(
            symbol="PRICEY", pe_ratio=40.0, pb_ratio=8.0, fcf_yield=0.01,
            roe=0.05, debt_to_equity=2.0, ma_50=105.0, ma_200=110.0,
            rsi_14=80.0, price=100.0,
        ),
    ]

    results = score_universe(inputs, WEIGHTS)

    assert [r.symbol for r in results] == ["CHEAP", "PRICEY"]
    assert results[0].composite_score > results[1].composite_score
    assert results[0].reasoning  # non-empty, cites actual metrics


def test_missing_metrics_do_not_crash_scoring():
    inputs = [
        ScreenerInput(
            symbol="PARTIAL", pe_ratio=None, pb_ratio=None, fcf_yield=None,
            roe=0.10, debt_to_equity=None, ma_50=None, ma_200=None,
            rsi_14=None, price=None,
        ),
    ]

    results = score_universe(inputs, WEIGHTS)

    assert results[0].symbol == "PARTIAL"
    assert 0.0 <= results[0].composite_score <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/analysis/test_screener.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.analysis.screener'`

- [ ] **Step 3: Write `src/finstock/analysis/screener.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from finstock.models import ScreenerResult


@dataclass
class ScreenerInput:
    symbol: str
    pe_ratio: float | None
    pb_ratio: float | None
    fcf_yield: float | None
    roe: float | None
    debt_to_equity: float | None
    ma_50: float | None
    ma_200: float | None
    rsi_14: float | None
    price: float | None


def _percentile_rank(values: list[float], value: float) -> float:
    if len(values) <= 1:
        return 0.5
    sorted_vals = sorted(values)
    count_below = sum(1 for v in sorted_vals if v < value)
    return count_below / (len(sorted_vals) - 1)


def score_universe(inputs: list[ScreenerInput], weights: dict[str, float]) -> list[ScreenerResult]:
    def valid(attr: str) -> list[float]:
        return [getattr(i, attr) for i in inputs if getattr(i, attr) is not None]

    pe_vals, pb_vals, fcf_vals = valid("pe_ratio"), valid("pb_ratio"), valid("fcf_yield")
    roe_vals, de_vals = valid("roe"), valid("debt_to_equity")

    results = []
    for item in inputs:
        reasoning: list[str] = []

        value_components = []
        if item.pe_ratio is not None and pe_vals:
            r = 1 - _percentile_rank(pe_vals, item.pe_ratio)
            value_components.append(r)
            reasoning.append(f"P/E {item.pe_ratio:.1f} ranks {r:.0%} (lower is better)")
        if item.pb_ratio is not None and pb_vals:
            r = 1 - _percentile_rank(pb_vals, item.pb_ratio)
            value_components.append(r)
            reasoning.append(f"P/B {item.pb_ratio:.1f} ranks {r:.0%} (lower is better)")
        if item.fcf_yield is not None and fcf_vals:
            r = _percentile_rank(fcf_vals, item.fcf_yield)
            value_components.append(r)
            reasoning.append(f"FCF yield {item.fcf_yield:.1%} ranks {r:.0%}")
        value_score = sum(value_components) / len(value_components) if value_components else 0.0

        quality_components = []
        if item.roe is not None and roe_vals:
            r = _percentile_rank(roe_vals, item.roe)
            quality_components.append(r)
            reasoning.append(f"ROE {item.roe:.1%} ranks {r:.0%}")
        if item.debt_to_equity is not None and de_vals:
            r = 1 - _percentile_rank(de_vals, item.debt_to_equity)
            quality_components.append(r)
            reasoning.append(f"Debt/Equity {item.debt_to_equity:.2f} ranks {r:.0%} (lower is better)")
        quality_score = sum(quality_components) / len(quality_components) if quality_components else 0.0

        momentum_components = []
        if item.price is not None and item.ma_50 is not None:
            momentum_components.append(1.0 if item.price > item.ma_50 else 0.0)
        if item.price is not None and item.ma_200 is not None:
            momentum_components.append(1.0 if item.price > item.ma_200 else 0.0)
        if item.rsi_14 is not None:
            distance_from_neutral = abs(item.rsi_14 - 50) / 50
            momentum_components.append(1 - distance_from_neutral)
            reasoning.append(f"RSI(14) {item.rsi_14:.0f}")
        momentum_score = (
            sum(momentum_components) / len(momentum_components) if momentum_components else 0.0
        )

        composite = (
            value_score * weights["value"]
            + quality_score * weights["quality"]
            + momentum_score * weights["momentum"]
        )
        results.append(
            ScreenerResult(
                symbol=item.symbol,
                composite_score=composite,
                value_score=value_score,
                quality_score=quality_score,
                momentum_score=momentum_score,
                reasoning=reasoning,
            )
        )

    results.sort(key=lambda r: r.composite_score, reverse=True)
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/analysis/test_screener.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finstock/analysis/screener.py tests/analysis/test_screener.py
git commit -m "feat: add value/quality/momentum screener scoring"
```

---

## Task 10: Holding analysis (bull/bear narrative)

**Files:**
- Create: `src/finstock/analysis/holdings.py`
- Test: `tests/analysis/test_holdings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/analysis/test_holdings.py
from finstock.analysis.holdings import analyze_holding
from finstock.models import Fundamentals, TechnicalSnapshot


def test_analyze_holding_cites_real_numbers_in_bull_and_bear():
    fundamentals = Fundamentals(
        symbol="AAPL", pe_ratio=18.0, revenue_growth_yoy=0.12, debt_to_equity=1.4,
        net_margin=0.15,
    )
    technicals = TechnicalSnapshot(symbol="AAPL", price=200.0)

    analysis = analyze_holding(
        symbol="AAPL",
        fundamentals=fundamentals,
        technicals=technicals,
        price_return_1m=0.03,
        benchmark_return_1m=0.01,
        next_earnings_date="2026-08-01",
        insider_net_shares_qtr=-5000.0,
        analyst_rating="buy",
        analyst_price_target=220.0,
    )

    assert any("18.0" in p for p in analysis.bull_points)
    assert any("1.40" in p for p in analysis.bear_points)  # elevated D/E flagged as bear
    assert any("15.0%" in p for p in analysis.bull_points)  # net margin flagged as bull
    assert any("2026-08-01" in n for n in analysis.uncertainty_notes)
    assert any("sold" in p for p in analysis.bear_points)  # insiders net sold


def test_analyze_holding_notes_uncertainty_for_missing_data():
    fundamentals = Fundamentals(symbol="XYZ")
    technicals = TechnicalSnapshot(symbol="XYZ", price=50.0)

    analysis = analyze_holding(
        symbol="XYZ",
        fundamentals=fundamentals,
        technicals=technicals,
        price_return_1m=None,
        benchmark_return_1m=None,
        next_earnings_date=None,
        insider_net_shares_qtr=None,
        analyst_rating=None,
        analyst_price_target=None,
    )

    assert any("P/E" in n for n in analysis.uncertainty_notes)
    assert any("Insider" in n for n in analysis.uncertainty_notes)


def test_analyze_holding_cites_3m_and_6m_returns_when_provided():
    fundamentals = Fundamentals(symbol="AAPL")
    technicals = TechnicalSnapshot(symbol="AAPL", price=200.0)

    analysis = analyze_holding(
        symbol="AAPL",
        fundamentals=fundamentals,
        technicals=technicals,
        price_return_1m=None,
        benchmark_return_1m=None,
        price_return_3m=0.10,
        benchmark_return_3m=0.04,
        price_return_6m=-0.02,
        benchmark_return_6m=0.05,
        next_earnings_date=None,
        insider_net_shares_qtr=None,
        analyst_rating=None,
        analyst_price_target=None,
    )

    assert any("3-month" in p and "10.0%" in p for p in analysis.bull_points)
    assert any("6-month" in p and "-2.0%" in p for p in analysis.bear_points)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/analysis/test_holdings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.analysis.holdings'`

- [ ] **Step 3: Write `src/finstock/analysis/holdings.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field

from finstock.models import Fundamentals, TechnicalSnapshot


@dataclass
class HoldingAnalysis:
    symbol: str
    bull_points: list[str] = field(default_factory=list)
    bear_points: list[str] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)


def analyze_holding(
    symbol: str,
    fundamentals: Fundamentals,
    technicals: TechnicalSnapshot,
    price_return_1m: float | None,
    benchmark_return_1m: float | None,
    next_earnings_date: str | None,
    insider_net_shares_qtr: float | None,
    analyst_rating: str | None,
    analyst_price_target: float | None,
    price_return_3m: float | None = None,
    benchmark_return_3m: float | None = None,
    price_return_6m: float | None = None,
    benchmark_return_6m: float | None = None,
) -> HoldingAnalysis:
    bull: list[str] = []
    bear: list[str] = []
    uncertainty: list[str] = []

    if fundamentals.pe_ratio is not None:
        target = bull if fundamentals.pe_ratio < 20 else bear
        target.append(f"Trades at {fundamentals.pe_ratio:.1f}x earnings.")
    else:
        uncertainty.append("P/E ratio unavailable this run.")

    if fundamentals.revenue_growth_yoy is not None:
        target = bull if fundamentals.revenue_growth_yoy > 0.05 else bear
        target.append(f"Revenue growth of {fundamentals.revenue_growth_yoy:.1%} YoY.")
    else:
        uncertainty.append("Revenue growth data unavailable this run.")

    if fundamentals.debt_to_equity is not None:
        target = bear if fundamentals.debt_to_equity > 1.0 else bull
        target.append(f"Debt/Equity of {fundamentals.debt_to_equity:.2f}.")
    else:
        uncertainty.append("Debt/Equity unavailable this run.")

    if fundamentals.net_margin is not None:
        target = bull if fundamentals.net_margin > 0.10 else bear
        target.append(f"Net margin of {fundamentals.net_margin:.1%}.")
    else:
        uncertainty.append("Net margin unavailable this run.")

    for label, price_return, benchmark_return in (
        ("1-month", price_return_1m, benchmark_return_1m),
        ("3-month", price_return_3m, benchmark_return_3m),
        ("6-month", price_return_6m, benchmark_return_6m),
    ):
        if price_return is not None and benchmark_return is not None:
            diff = price_return - benchmark_return
            target = bull if diff > 0 else bear
            target.append(
                f"{label} return of {price_return:.1%} vs benchmark {benchmark_return:.1%}."
            )
        else:
            uncertainty.append(f"{label} price-vs-benchmark comparison unavailable this run.")

    if insider_net_shares_qtr is not None:
        direction = "bought" if insider_net_shares_qtr > 0 else "sold"
        target = bull if insider_net_shares_qtr > 0 else bear
        target.append(
            f"Insiders net {direction} {abs(insider_net_shares_qtr):,.0f} shares "
            "over the trailing quarter."
        )
    else:
        uncertainty.append("Insider transaction data unavailable this run.")

    if analyst_rating is not None:
        bull.append(f"Analyst consensus: {analyst_rating}.")

    if analyst_price_target is not None and technicals.price:
        diff_pct = (analyst_price_target - technicals.price) / technicals.price
        target = bull if diff_pct > 0 else bear
        target.append(
            f"Analyst price target {analyst_price_target:.2f} implies "
            f"{diff_pct:+.1%} vs current price."
        )

    if next_earnings_date is not None:
        uncertainty.append(
            f"Upcoming earnings on {next_earnings_date} may move the stock materially."
        )

    uncertainty.append("Free-tier data sources may lag real-time pricing/fundamentals.")

    return HoldingAnalysis(symbol=symbol, bull_points=bull, bear_points=bear, uncertainty_notes=uncertainty)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/analysis/test_holdings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finstock/analysis/holdings.py tests/analysis/test_holdings.py
git commit -m "feat: add rule-based bull/bear holding analysis"
```

---

## Task 11: State and change detection

**Files:**
- Create: `src/finstock/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state.py
import json
from datetime import datetime

from finstock.state import HoldingSnapshot, diff_snapshots, load_latest_snapshot, save_snapshot


def test_save_and_load_latest_snapshot(tmp_path):
    holdings = [
        HoldingSnapshot(symbol="AAPL", price=200.0, pe_ratio=18.0, debt_to_equity=1.4,
                         next_earnings_date="2026-08-01", quantity=10),
    ]
    save_snapshot(tmp_path, holdings, timestamp=datetime(2026, 7, 5, 8, 0))

    loaded = load_latest_snapshot(tmp_path)

    assert loaded["holdings"][0]["symbol"] == "AAPL"
    assert loaded["holdings"][0]["price"] == 200.0


def test_load_latest_snapshot_returns_none_when_no_history(tmp_path):
    assert load_latest_snapshot(tmp_path / "does-not-exist") is None


def test_diff_flags_price_move_beyond_threshold():
    previous = {"holdings": [{"symbol": "AAPL", "price": 200.0, "pe_ratio": 18.0,
                               "next_earnings_date": "2026-08-01", "quantity": 10}]}
    current = [HoldingSnapshot(symbol="AAPL", price=215.0, pe_ratio=18.0, debt_to_equity=1.4,
                                next_earnings_date="2026-08-01", quantity=10)]

    changes = diff_snapshots(previous, current, price_move_pct=5.0, pe_band_pct=15.0)

    assert "AAPL" in changes
    assert any("7.5%" in note for note in changes["AAPL"])


def test_diff_returns_empty_when_no_prior_snapshot():
    current = [HoldingSnapshot(symbol="AAPL", price=200.0, pe_ratio=18.0, debt_to_equity=1.4,
                                next_earnings_date="2026-08-01", quantity=10)]

    changes = diff_snapshots(None, current, price_move_pct=5.0, pe_band_pct=15.0)

    assert changes == {}


def test_diff_flags_position_size_change():
    previous = {"holdings": [{"symbol": "AAPL", "price": 200.0, "pe_ratio": 18.0,
                               "next_earnings_date": "2026-08-01", "quantity": 10}]}
    current = [HoldingSnapshot(symbol="AAPL", price=200.0, pe_ratio=18.0, debt_to_equity=1.4,
                                next_earnings_date="2026-08-01", quantity=15)]

    changes = diff_snapshots(previous, current, price_move_pct=5.0, pe_band_pct=15.0)

    assert any("15" in note and "10" in note for note in changes["AAPL"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.state'`

- [ ] **Step 3: Write `src/finstock/state.py`**

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class HoldingSnapshot:
    symbol: str
    price: float
    pe_ratio: float | None
    debt_to_equity: float | None
    next_earnings_date: str | None
    quantity: float


def save_snapshot(snapshots_dir: Path, holdings: list[HoldingSnapshot], timestamp: datetime) -> Path:
    snapshots_dir = Path(snapshots_dir)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    path = snapshots_dir / f"{timestamp.strftime('%Y-%m-%d_%H%M')}.json"
    payload = {"timestamp": timestamp.isoformat(), "holdings": [asdict(h) for h in holdings]}
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_latest_snapshot(snapshots_dir: Path) -> dict | None:
    snapshots_dir = Path(snapshots_dir)
    if not snapshots_dir.exists():
        return None
    files = sorted(snapshots_dir.glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text())


def diff_snapshots(
    previous: dict | None,
    current: list[HoldingSnapshot],
    price_move_pct: float,
    pe_band_pct: float,
) -> dict[str, list[str]]:
    changes: dict[str, list[str]] = {}
    if previous is None:
        return changes

    prev_by_symbol = {h["symbol"]: h for h in previous["holdings"]}
    for holding in current:
        prev = prev_by_symbol.get(holding.symbol)
        if prev is None:
            changes[holding.symbol] = ["New holding since last report."]
            continue

        notes: list[str] = []
        if prev.get("price"):
            pct_move = (holding.price - prev["price"]) / prev["price"] * 100
            if abs(pct_move) >= price_move_pct:
                notes.append(f"Price moved {pct_move:+.1f}% since last report.")
        if prev.get("pe_ratio") and holding.pe_ratio:
            pe_move = (holding.pe_ratio - prev["pe_ratio"]) / prev["pe_ratio"] * 100
            if abs(pe_move) >= pe_band_pct:
                notes.append(f"P/E moved {pe_move:+.1f}% since last report.")
        if prev.get("next_earnings_date") != holding.next_earnings_date:
            notes.append(f"Earnings date changed to {holding.next_earnings_date}.")
        if prev.get("quantity") != holding.quantity:
            notes.append(
                f"Position size changed from {prev['quantity']} to {holding.quantity} shares."
            )
        if notes:
            changes[holding.symbol] = notes

    return changes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finstock/state.py tests/test_state.py
git commit -m "feat: add JSON snapshot state and change detection"
```

---

## Task 12: Markdown report renderer

**Files:**
- Create: `src/finstock/report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report.py
from datetime import datetime
from pathlib import Path

from finstock.analysis.holdings import HoldingAnalysis
from finstock.models import ScreenerResult
from finstock.report import render_report, save_report


def test_render_report_includes_all_required_sections():
    holding_analyses = [
        HoldingAnalysis(
            symbol="AAPL",
            bull_points=["Trades at 18.0x earnings."],
            bear_points=["Debt/Equity of 1.40."],
            uncertainty_notes=["Free-tier data sources may lag real-time pricing/fundamentals."],
        )
    ]
    changes = {"AAPL": ["Price moved +7.5% since last report."]}
    screener_results = [
        ScreenerResult(
            symbol="MSFT", composite_score=0.82, value_score=0.7,
            quality_score=0.9, momentum_score=0.8,
            reasoning=["P/E 25.0 ranks 60% (lower is better)"],
        )
    ]

    markdown = render_report(
        generated_at=datetime(2026, 7, 5, 8, 0),
        cash_free=1000.0,
        cash_total=5000.0,
        portfolio_value=6200.0,
        holding_analyses=holding_analyses,
        changes_by_symbol=changes,
        screener_results=screener_results,
        first_run=False,
        recent_orders=["2026-07-01: BUY 2 AAPL @ 195.00"],
        recent_dividends=["2026-06-15: AAPL dividend $4.20"],
    )

    assert "# FinStock Report" in markdown
    assert "2026-07-05" in markdown
    assert "1000.0" in markdown  # cash position
    assert "6200.0" in markdown  # portfolio value
    assert "AAPL" in markdown
    assert "Trades at 18.0x earnings." in markdown
    assert "Price moved +7.5% since last report." in markdown
    assert "MSFT" in markdown
    assert "not a recommendation" in markdown.lower()
    assert "2026-07-01: BUY 2 AAPL @ 195.00" in markdown
    assert "2026-06-15: AAPL dividend $4.20" in markdown


def test_render_report_first_run_notes_no_comparison():
    markdown = render_report(
        generated_at=datetime(2026, 7, 5, 8, 0),
        cash_free=1000.0,
        cash_total=5000.0,
        portfolio_value=5000.0,
        holding_analyses=[],
        changes_by_symbol={},
        screener_results=[],
        first_run=True,
        recent_orders=["data unavailable this run"],
        recent_dividends=["data unavailable this run"],
    )

    assert "First run" in markdown
    assert "data unavailable this run" in markdown


def test_save_report_writes_dated_file(tmp_path):
    path = save_report(tmp_path, datetime(2026, 7, 5, 8, 0), "# content")

    assert path.read_text() == "# content"
    assert path.name == "2026-07-05_0800.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.report'`

- [ ] **Step 3: Write `src/finstock/report.py`**

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from finstock.analysis.holdings import HoldingAnalysis
from finstock.models import ScreenerResult

DISCLAIMER = (
    "This report is observational research output generated from third-party "
    "data and is **not a recommendation** to buy, sell, or hold any security. "
    "All figures may be delayed or incomplete due to free-tier data limits. "
    "You are the sole decision-maker on any transaction."
)


def render_report(
    generated_at: datetime,
    cash_free: float,
    cash_total: float,
    portfolio_value: float,
    holding_analyses: list[HoldingAnalysis],
    changes_by_symbol: dict[str, list[str]],
    screener_results: list[ScreenerResult],
    first_run: bool,
    recent_orders: list[str],
    recent_dividends: list[str],
) -> str:
    lines = [
        "# FinStock Report",
        "",
        f"Generated: {generated_at.isoformat()}",
        "",
        "## Portfolio overview",
        "",
        f"- Free cash: {cash_free}",
        f"- Total cash: {cash_total}",
        f"- Portfolio value: {portfolio_value}",
        "",
    ]

    if first_run:
        lines.append("_First run — no prior snapshot to compare._")
        lines.append("")

    lines.append("## Recent activity")
    lines.append("")
    lines.append("**Orders (last period):**")
    for entry in recent_orders:
        lines.append(f"- {entry}")
    lines.append("")
    lines.append("**Dividends (last period):**")
    for entry in recent_dividends:
        lines.append(f"- {entry}")
    lines.append("")

    lines.append("## Holdings")
    lines.append("")
    for analysis in holding_analyses:
        lines.append(f"### {analysis.symbol}")
        lines.append("")
        if analysis.symbol in changes_by_symbol:
            lines.append("**Changes since last report:**")
            for note in changes_by_symbol[analysis.symbol]:
                lines.append(f"- {note}")
            lines.append("")
        if analysis.bull_points:
            lines.append("**Bull points:**")
            for point in analysis.bull_points:
                lines.append(f"- {point}")
            lines.append("")
        if analysis.bear_points:
            lines.append("**Bear points:**")
            for point in analysis.bear_points:
                lines.append(f"- {point}")
            lines.append("")
        if analysis.uncertainty_notes:
            lines.append("**Uncertainty / risk notes:**")
            for note in analysis.uncertainty_notes:
                lines.append(f"- {note}")
            lines.append("")

    lines.append("## Screener results")
    lines.append("")
    for rank, result in enumerate(screener_results, start=1):
        lines.append(
            f"{rank}. **{result.symbol}** — composite {result.composite_score:.2f} "
            f"(value {result.value_score:.2f}, quality {result.quality_score:.2f}, "
            f"momentum {result.momentum_score:.2f})"
        )
        for reason in result.reasoning:
            lines.append(f"   - {reason}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(DISCLAIMER)

    return "\n".join(lines)


def save_report(reports_dir: Path, timestamp: datetime, content: str) -> Path:
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{timestamp.strftime('%Y-%m-%d_%H%M')}.md"
    path.write_text(content)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finstock/report.py tests/test_report.py
git commit -m "feat: add markdown report renderer"
```

---

## Task 13: ntfy.sh notification

**Files:**
- Create: `src/finstock/notify.py`
- Test: `tests/test_notify.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notify.py
import responses

from finstock.notify import send_notification


@responses.activate
def test_send_notification_posts_to_ntfy_topic():
    responses.post("https://ntfy.sh/my-topic", status=200)

    result = send_notification("my-topic", title="FinStock report ready", message="Cash: 1000")

    assert result is True
    assert responses.calls[0].request.headers["Title"] == "FinStock report ready"


@responses.activate
def test_send_notification_returns_false_on_failure():
    responses.post("https://ntfy.sh/my-topic", status=500)

    result = send_notification("my-topic", title="FinStock report ready", message="Cash: 1000")

    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_notify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.notify'`

- [ ] **Step 3: Write `src/finstock/notify.py`**

```python
from __future__ import annotations

import requests


def send_notification(ntfy_topic: str, title: str, message: str) -> bool:
    try:
        resp = requests.post(
            f"https://ntfy.sh/{ntfy_topic}",
            data=message.encode("utf-8"),
            headers={"Title": title},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException:
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_notify.py -v`
Expected: PASS

- [ ] **Step 5: Run the guardrail suite once more**

Run: `uv run pytest tests/test_no_trading.py -v`
Expected: PASS — `notify.py` is the one file allowed to call `requests.post`.

- [ ] **Step 6: Commit**

```bash
git add src/finstock/notify.py tests/test_notify.py
git commit -m "feat: add ntfy.sh push notification"
```

---

## Task 14: Main orchestration

**Files:**
- Create: `src/finstock/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write the failing integration test (all clients mocked)**

```python
# tests/test_main.py
from datetime import datetime
from unittest.mock import MagicMock

from finstock.config import ChangeDetectionThresholds, NotifyConfig, ScreenerWeights, Settings
from finstock.main import run


def _fake_settings(tmp_path) -> Settings:
    return Settings(
        t212_env="demo",
        t212_api_key="t212-key",
        finnhub_api_key="finnhub-key",
        fmp_api_key="fmp-key",
        benchmark_ticker="SPY",
        watchlist=["MSFT"],
        ticker_overrides={},
        screener_weights=ScreenerWeights(value=0.4, quality=0.35, momentum=0.25),
        change_detection=ChangeDetectionThresholds(price_move_pct=5.0, pe_band_pct=15.0),
        notify=NotifyConfig(ntfy_topic="my-topic", schedule_times=["08:00", "18:00"]),
    )


def test_run_aborts_and_notifies_failure_when_t212_portfolio_fails(tmp_path, monkeypatch):
    settings = _fake_settings(tmp_path)

    t212_client = MagicMock()
    t212_client.get_cash.return_value = {"free": 100.0, "total": 500.0}
    t212_client.get_portfolio.side_effect = RuntimeError("T212 down")

    sent = {}

    def fake_send_notification(topic, title, message):
        sent["topic"] = topic
        sent["title"] = title
        sent["message"] = message
        return True

    monkeypatch.setattr("finstock.main.send_notification", fake_send_notification)

    result = run(
        settings=settings,
        data_dir=tmp_path,
        now=datetime(2026, 7, 5, 8, 0),
        t212_client=t212_client,
        finnhub_client=MagicMock(),
        fmp_client=MagicMock(),
    )

    assert result.aborted is True
    assert "failed" in sent["title"].lower()
    assert not (tmp_path / "reports").exists() or not list((tmp_path / "reports").glob("*.md"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finstock.main'`

- [ ] **Step 3: Write `src/finstock/main.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from finstock.analysis.holdings import analyze_holding
from finstock.analysis.screener import ScreenerInput, score_universe
from finstock.analysis.technicals import rsi, simple_moving_average
from finstock.clients.finnhub import FinnhubClient
from finstock.clients.fmp import FMPClient, FMPNotEntitledError
from finstock.clients.trading212 import Trading212Client
from finstock.config import Settings, load_settings
from finstock.models import Fundamentals, TechnicalSnapshot, derive_symbol
from finstock.notify import send_notification
from finstock.report import render_report, save_report
from finstock.state import HoldingSnapshot, diff_snapshots, load_latest_snapshot, save_snapshot

FMP_CALLS_PER_RUN_BUDGET = 120


@dataclass
class RunResult:
    aborted: bool
    report_path: Path | None = None


def run(
    settings: Settings,
    data_dir: Path,
    now: datetime,
    t212_client: Trading212Client,
    finnhub_client: FinnhubClient,
    fmp_client: FMPClient,
) -> RunResult:
    reports_dir = Path(data_dir) / "reports"
    snapshots_dir = Path(data_dir) / "snapshots"

    try:
        cash = t212_client.get_cash()
        portfolio = t212_client.get_portfolio()
    except Exception as exc:  # noqa: BLE001 - any T212 core-data failure aborts the run
        send_notification(
            settings.notify.ntfy_topic,
            title="FinStock run failed",
            message=f"Could not fetch T212 portfolio/cash: {exc}",
        )
        return RunResult(aborted=True)

    try:
        account_summary = t212_client.get_account_summary()
        portfolio_value = account_summary.get("total", cash.get("total", 0.0))
    except Exception:  # noqa: BLE001 - degrade, cash total is a reasonable fallback
        portfolio_value = cash.get("total", 0.0)

    try:
        orders = t212_client.get_order_history()
        recent_orders = [
            f"{o.get('dateExecuted', '?')}: {o.get('type', '?')} "
            f"{o.get('filledQuantity', '?')} {o.get('ticker', '?')} @ {o.get('fillPrice', '?')}"
            for o in orders.get("items", [])
        ] or ["No orders in this period."]
    except Exception:  # noqa: BLE001
        recent_orders = ["data unavailable this run"]

    try:
        dividends = t212_client.get_dividend_history()
        recent_dividends = [
            f"{d.get('paidOn', '?')}: {d.get('ticker', '?')} dividend {d.get('amount', '?')}"
            for d in dividends.get("items", [])
        ] or ["No dividends in this period."]
    except Exception:  # noqa: BLE001
        recent_dividends = ["data unavailable this run"]

    holdings_symbols = [
        derive_symbol(position["ticker"], settings.ticker_overrides) for position in portfolio
    ]
    universe = list(dict.fromkeys(holdings_symbols + settings.watchlist))  # holdings first, deduped

    fundamentals_by_symbol: dict[str, Fundamentals] = {}
    technicals_by_symbol: dict[str, TechnicalSnapshot] = {}
    day_change_by_symbol: dict[str, float] = {}

    for symbol in universe:
        fundamentals = Fundamentals(symbol=symbol)
        try:
            metrics = finnhub_client.basic_financials(symbol).get("metric", {})
            fundamentals.pe_ratio = metrics.get("peNormalizedAnnual")
            fundamentals.roe = metrics.get("roeTTM")
            fundamentals.debt_to_equity = metrics.get("totalDebt/totalEquityAnnual")
            fundamentals.revenue_growth_yoy = metrics.get("revenueGrowthTTMYoy")
            fundamentals.net_margin = metrics.get("netProfitMarginTTM")
        except Exception:  # noqa: BLE001 - degrade gracefully per spec
            fundamentals.source_notes.append("Finnhub fundamentals unavailable this run.")

        if fmp_client.calls_made < FMP_CALLS_PER_RUN_BUDGET:
            try:
                key_metrics = fmp_client.key_metrics(symbol)
                if key_metrics:
                    fundamentals.pb_ratio = key_metrics[0].get("pbRatio")
                    fundamentals.fcf_yield = key_metrics[0].get("freeCashFlowYield")
            except FMPNotEntitledError:
                fundamentals.source_notes.append("data unavailable on current plan")
            except Exception:  # noqa: BLE001
                fundamentals.source_notes.append("FMP data unavailable this run.")
        else:
            fundamentals.source_notes.append("FMP data skipped this run (daily budget).")

        fundamentals_by_symbol[symbol] = fundamentals

        try:
            quote = finnhub_client.quote(symbol)
            price = quote.get("c", 0.0)
            day_change_by_symbol[symbol] = quote.get("dp", 0.0) / 100.0
        except Exception:  # noqa: BLE001
            price = 0.0
            day_change_by_symbol[symbol] = 0.0
        technicals_by_symbol[symbol] = TechnicalSnapshot(symbol=symbol, price=price)

    screener_inputs = [
        ScreenerInput(
            symbol=symbol,
            pe_ratio=fundamentals_by_symbol[symbol].pe_ratio,
            pb_ratio=fundamentals_by_symbol[symbol].pb_ratio,
            fcf_yield=fundamentals_by_symbol[symbol].fcf_yield,
            roe=fundamentals_by_symbol[symbol].roe,
            debt_to_equity=fundamentals_by_symbol[symbol].debt_to_equity,
            ma_50=None,
            ma_200=None,
            rsi_14=None,
            price=technicals_by_symbol[symbol].price,
        )
        for symbol in universe
    ]
    weights = {
        "value": settings.screener_weights.value,
        "quality": settings.screener_weights.quality,
        "momentum": settings.screener_weights.momentum,
    }
    screener_results = score_universe(screener_inputs, weights)

    holding_analyses = []
    current_snapshots = []
    for symbol in holdings_symbols:
        fundamentals = fundamentals_by_symbol[symbol]
        technicals = technicals_by_symbol[symbol]
        analysis = analyze_holding(
            symbol=symbol,
            fundamentals=fundamentals,
            technicals=technicals,
            price_return_1m=None,
            benchmark_return_1m=None,
            next_earnings_date=None,
            insider_net_shares_qtr=None,
            analyst_rating=None,
            analyst_price_target=None,
        )
        holding_analyses.append(analysis)
        current_snapshots.append(
            HoldingSnapshot(
                symbol=symbol,
                price=technicals.price,
                pe_ratio=fundamentals.pe_ratio,
                debt_to_equity=fundamentals.debt_to_equity,
                next_earnings_date=None,
                quantity=next(
                    (p["quantity"] for p in portfolio if derive_symbol(p["ticker"], settings.ticker_overrides) == symbol),
                    0.0,
                ),
            )
        )

    previous_snapshot = load_latest_snapshot(snapshots_dir)
    changes = diff_snapshots(
        previous_snapshot,
        current_snapshots,
        settings.change_detection.price_move_pct,
        settings.change_detection.pe_band_pct,
    )
    save_snapshot(snapshots_dir, current_snapshots, now)

    markdown = render_report(
        generated_at=now,
        cash_free=cash.get("free", 0.0),
        cash_total=cash.get("total", 0.0),
        portfolio_value=portfolio_value,
        holding_analyses=holding_analyses,
        changes_by_symbol=changes,
        screener_results=screener_results,
        first_run=previous_snapshot is None,
        recent_orders=recent_orders,
        recent_dividends=recent_dividends,
    )
    report_path = save_report(reports_dir, now, markdown)

    top_pick = screener_results[0].symbol if screener_results else "n/a"
    biggest_mover = max(
        day_change_by_symbol.items(), key=lambda kv: abs(kv[1]), default=(None, 0.0)
    )
    mover_text = (
        f"{biggest_mover[0]} ({biggest_mover[1]:+.1%})" if biggest_mover[0] else "n/a"
    )
    send_notification(
        settings.notify.ntfy_topic,
        title="FinStock report ready",
        message=(
            f"Portfolio value: {portfolio_value}. "
            f"Biggest mover: {mover_text}. "
            f"Top screener pick: {top_pick}. "
            f"Report: {report_path.name}"
        ),
    )

    return RunResult(aborted=False, report_path=report_path)


if __name__ == "__main__":
    settings = load_settings()
    run(
        settings=settings,
        data_dir=Path("data"),
        now=datetime.now(),
        t212_client=Trading212Client(settings.t212_api_key, settings.t212_base_url),
        finnhub_client=FinnhubClient(settings.finnhub_api_key),
        fmp_client=FMPClient(settings.fmp_api_key),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Run the entire test suite**

Run: `uv run pytest -v`
Expected: all tests pass, including `tests/test_no_trading.py`.

- [ ] **Step 6: Commit**

```bash
git add src/finstock/main.py tests/test_main.py
git commit -m "feat: wire up main orchestration with abort/degrade rules"
```

*Note for the implementing engineer:* `main.py`'s per-holding wiring (1/3/6-month returns, benchmark comparison, earnings dates, insider/analyst data, and MA/RSI feed into the screener) is intentionally left as `None`/unfilled stubs in this task — each of those data feeds already has a tested client method (Finnhub `candles`, `earnings_calendar`, `insider_transactions`, `recommendation_trends`, `price_target`) and a tested consumer (`analyze_holding`, `score_universe`, `simple_moving_average`, `rsi`). Task 15 wires them together end-to-end; don't treat Task 14's stubs as the finished product.

---

## Task 15: Wire remaining data feeds into main

**Files:**
- Modify: `src/finstock/main.py`
- Test: `tests/test_main.py` (extend)

- [ ] **Step 1: Write a failing test asserting MA/RSI and benchmark data reach the screener/report**

```python
# add to tests/test_main.py
def test_run_populates_technicals_and_benchmark_return(tmp_path, monkeypatch):
    settings = _fake_settings(tmp_path)

    t212_client = MagicMock()
    t212_client.get_cash.return_value = {"free": 100.0, "total": 500.0}
    t212_client.get_portfolio.return_value = [
        {"ticker": "AAPL_US_EQ", "quantity": 10}
    ]
    t212_client.get_account_summary.return_value = {"total": 1500.0}
    t212_client.get_order_history.return_value = {"items": []}
    t212_client.get_dividend_history.return_value = {"items": []}

    finnhub_client = MagicMock()
    finnhub_client.quote.return_value = {"c": 150.0}
    finnhub_client.basic_financials.return_value = {"metric": {}}
    finnhub_client.candles.return_value = {
        "c": [100.0 + i for i in range(210)], "s": "ok",
    }
    finnhub_client.earnings_calendar.return_value = {"earningsCalendar": []}
    finnhub_client.insider_transactions.return_value = {"data": []}
    finnhub_client.recommendation_trends.return_value = []
    finnhub_client.price_target.return_value = {}

    fmp_client = MagicMock()
    fmp_client.calls_made = 0
    fmp_client.key_metrics.return_value = []

    monkeypatch.setattr("finstock.main.send_notification", lambda *a, **k: True)

    result = run(
        settings=settings,
        data_dir=tmp_path,
        now=datetime(2026, 7, 5, 8, 0),
        t212_client=t212_client,
        finnhub_client=finnhub_client,
        fmp_client=fmp_client,
    )

    assert result.aborted is False
    content = result.report_path.read_text()
    assert "AAPL" in content
```

- [ ] **Step 2: Run test to verify it fails or exposes gaps**

Run: `uv run pytest tests/test_main.py -v`
Expected: initially may PASS trivially (stubs already produce a report) — inspect the report content manually and confirm MA/RSI/benchmark fields are still blank; this confirms the gap Task 14 flagged.

- [ ] **Step 3: Extend `src/finstock/main.py` to compute technicals and benchmark comparison**

Replace the technicals-fetching block (`technicals_by_symbol[symbol] = TechnicalSnapshot(...)`) with:

```python
    to_ts = int(now.timestamp())
    from_ts = to_ts - 400 * 24 * 60 * 60  # ~400 days of daily candles

    def _period_return(prices: list[float], bars_back: int) -> float | None:
        if len(prices) >= bars_back + 1 and prices[-bars_back - 1]:
            return (prices[-1] - prices[-bars_back - 1]) / prices[-bars_back - 1]
        return None

    benchmark_candles = finnhub_client.candles(settings.benchmark_ticker, "D", from_ts, to_ts)
    benchmark_prices = benchmark_candles.get("c", [])
    benchmark_return_1m = _period_return(benchmark_prices, 22)
    benchmark_return_3m = _period_return(benchmark_prices, 66)
    benchmark_return_6m = _period_return(benchmark_prices, 132)

    prices_by_symbol: dict[str, list[float]] = {}

    for symbol in universe:
        ...  # existing fundamentals code above stays as-is

        try:
            candles = finnhub_client.candles(symbol, "D", from_ts, to_ts)
            prices = candles.get("c", [])
        except Exception:  # noqa: BLE001
            prices = []
        prices_by_symbol[symbol] = prices

        price = prices[-1] if prices else 0.0
        day_change_by_symbol[symbol] = (
            (prices[-1] - prices[-2]) / prices[-2] if len(prices) >= 2 and prices[-2] else 0.0
        )
        technicals_by_symbol[symbol] = TechnicalSnapshot(
            symbol=symbol,
            price=price,
            ma_50=simple_moving_average(prices, 50),
            ma_200=simple_moving_average(prices, 200),
            rsi_14=rsi(prices, 14),
        )
```

`prices_by_symbol` caches each symbol's candle series so the per-holding loop below (which needs
the same series for 1m/3m/6m returns) doesn't re-fetch it from Finnhub.

This also replaces the `day_change_by_symbol[symbol] = quote.get("dp", 0.0) / 100.0` line from
Task 14 — it's now derived from candles instead of a separate `quote()` call, so `finnhub_client.quote(symbol)`
is only used for the universe's screener price where candles aren't already fetched. Since candles are now
fetched for every symbol in the universe, remove the earlier `quote()` call entirely from this loop.

And update `screener_inputs` to use the real `ma_50`/`ma_200`/`rsi_14` instead of `None`:

```python
    screener_inputs = [
        ScreenerInput(
            symbol=symbol,
            pe_ratio=fundamentals_by_symbol[symbol].pe_ratio,
            pb_ratio=fundamentals_by_symbol[symbol].pb_ratio,
            fcf_yield=fundamentals_by_symbol[symbol].fcf_yield,
            roe=fundamentals_by_symbol[symbol].roe,
            debt_to_equity=fundamentals_by_symbol[symbol].debt_to_equity,
            ma_50=technicals_by_symbol[symbol].ma_50,
            ma_200=technicals_by_symbol[symbol].ma_200,
            rsi_14=technicals_by_symbol[symbol].rsi_14,
            price=technicals_by_symbol[symbol].price,
        )
        for symbol in universe
    ]
```

And update the `analyze_holding` call to pass real 1-month return, benchmark return, earnings date, insider data, and analyst data:

```python
    for symbol in holdings_symbols:
        fundamentals = fundamentals_by_symbol[symbol]
        technicals = technicals_by_symbol[symbol]

        prices = prices_by_symbol.get(symbol, [])
        price_return_1m = _period_return(prices, 22)
        price_return_3m = _period_return(prices, 66)
        price_return_6m = _period_return(prices, 132)

        try:
            earnings = finnhub_client.earnings_calendar(symbol).get("earningsCalendar", [])
            next_earnings_date = earnings[0]["date"] if earnings else None
        except Exception:  # noqa: BLE001
            next_earnings_date = None

        try:
            insider = finnhub_client.insider_transactions(symbol).get("data", [])
            insider_net_shares_qtr = sum(t.get("share", 0) for t in insider) if insider else None
        except Exception:  # noqa: BLE001
            insider_net_shares_qtr = None

        try:
            recs = finnhub_client.recommendation_trends(symbol)
            if recs:
                latest = recs[0]
                bullish = latest.get("buy", 0) + latest.get("strongBuy", 0)
                bearish = latest.get("sell", 0) + latest.get("strongSell", 0)
                analyst_rating = "buy-leaning" if bullish > bearish else "hold-or-lower"
            else:
                analyst_rating = None
        except Exception:  # noqa: BLE001
            analyst_rating = None

        try:
            target = finnhub_client.price_target(symbol)
            analyst_price_target = target.get("targetMean")
        except Exception:  # noqa: BLE001
            analyst_price_target = None

        analysis = analyze_holding(
            symbol=symbol,
            fundamentals=fundamentals,
            technicals=technicals,
            price_return_1m=price_return_1m,
            benchmark_return_1m=benchmark_return_1m,
            next_earnings_date=next_earnings_date,
            insider_net_shares_qtr=insider_net_shares_qtr,
            analyst_rating=analyst_rating,
            analyst_price_target=analyst_price_target,
            price_return_3m=price_return_3m,
            benchmark_return_3m=benchmark_return_3m,
            price_return_6m=price_return_6m,
            benchmark_return_6m=benchmark_return_6m,
        )
        holding_analyses.append(analysis)
        current_snapshots.append(
            HoldingSnapshot(
                symbol=symbol,
                price=technicals.price,
                pe_ratio=fundamentals.pe_ratio,
                debt_to_equity=fundamentals.debt_to_equity,
                next_earnings_date=next_earnings_date,
                quantity=next(
                    (p["quantity"] for p in portfolio if derive_symbol(p["ticker"], settings.ticker_overrides) == symbol),
                    0.0,
                ),
            )
        )
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests pass, including the extended `test_run_populates_technicals_and_benchmark_return`.

- [ ] **Step 5: Commit**

```bash
git add src/finstock/main.py tests/test_main.py
git commit -m "feat: wire technicals, benchmark return, earnings, insider, and analyst data into main"
```

---

## Task 16: Task Scheduler registration script

**Files:**
- Create: `scripts/register_task_scheduler.ps1`

- [ ] **Step 1: Write `scripts/register_task_scheduler.ps1`**

```powershell
param(
    [string]$TaskNamePrefix = "FinStock",
    [string[]]$Times = @("08:00", "18:00"),
    [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot)
)

foreach ($i in 0..($Times.Count - 1)) {
    $taskName = "$TaskNamePrefix-$i"
    $time = $Times[$i]

    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }

    $action = New-ScheduledTaskAction -Execute "uv" -Argument "run python -m finstock.main" -WorkingDirectory $ProjectPath
    $trigger = New-ScheduledTaskTrigger -Daily -At $time
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description "FinStock research report run" | Out-Null
    Write-Host "Registered $taskName at $time"
}
```

- [ ] **Step 2: Verify the script parses correctly (dry-run syntax check, does not register real tasks)**

Run: `powershell -NoProfile -Command "Get-Command -Syntax { & '.\scripts\register_task_scheduler.ps1' }"` — or simply open the file and confirm no syntax errors via `powershell -NoProfile -Command "[void][System.Management.Automation.PSParser]::Tokenize((Get-Content .\scripts\register_task_scheduler.ps1 -Raw), [ref]$null)"`
Expected: no errors printed.

- [ ] **Step 3: Commit**

```bash
git add scripts/register_task_scheduler.ps1
git commit -m "feat: add Windows Task Scheduler registration script"
```

---

## Task 17: Manual end-to-end verification (uses your real read-only keys)

This task is **not automated** — it's a checklist for you to run once, using your real Trading 212 demo/live key, Finnhub key, and FMP key, before trusting the tool with scheduled runs.

*Deviation from spec:* the spec's Testing section describes "thin integration tests per API client, skipped unless real keys are present in the environment" (i.e. `pytest.mark.skipif`-based tests). This plan substitutes a manual checklist instead, since a personal single-user tool doesn't need that automation to stay maintainable, and the mocked tests in Tasks 4/6/7 already cover each client's request-building and retry logic. If you'd rather have real `skipif`-gated integration tests, that can be added as a follow-up task.

- [ ] **Step 1:** Copy `.env.example` to `.env` and fill in your real `T212_API_KEY`, `FINNHUB_API_KEY`, `FMP_API_KEY`, and `NTFY_TOPIC` (subscribe to that topic in the ntfy iOS app first).
- [ ] **Step 2:** Set `t212_env: demo` in `config/config.yaml` for the first run (switch to `live` only once you're satisfied with the output).
- [ ] **Step 3:** Run `uv run python -m finstock.main`.
- [ ] **Step 4:** Confirm a new file appears under `data/reports/` and open it — check the portfolio section reflects your real cash/holdings, and the disclaimer/uncertainty notes are present throughout.
- [ ] **Step 5:** Confirm a notification arrived on your phone via ntfy.
- [ ] **Step 6:** Re-run the tool a second time and confirm the report now includes a "Changes since last report" section (even if empty) instead of "First run."
- [ ] **Step 7:** If satisfied, switch `t212_env` to `live` with your live read-only key, and run `powershell scripts/register_task_scheduler.ps1` to register the twice-daily schedule.
- [ ] **Step 8:** Run `uv run pytest -v` one final time to confirm the full suite (including the no-trading guardrail) is green before relying on the scheduled runs.
