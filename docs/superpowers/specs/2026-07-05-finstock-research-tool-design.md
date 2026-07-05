# FinStock — Personal Investment Research Tool (Design Spec)

Date: 2026-07-05
Status: Approved by user, pending spec review

## Purpose

A strictly read-only / advisory Python tool that pulls the user's Trading 212
portfolio plus market data from Finnhub and Financial Modeling Prep (FMP),
runs fundamental and quant-screener analysis, and produces a dated markdown
research report twice a day, with a brief push notification to the user's
iPhone when a new report is ready.

The user makes all buy/sell decisions manually, outside this tool. The tool
must never place, modify, or cancel any order.

## Non-negotiable constraint: no trading capability

- The Trading 212 client (`clients/trading212.py`) implements only 5 GET
  methods, one per allowed endpoint:
  `/equity/account/cash`, `/equity/account/summary`, `/equity/portfolio`,
  `/equity/history/orders`, `/equity/history/dividends`.
- No function anywhere in the codebase accepts order parameters
  (ticker + quantity + side), and no code references the
  `/equity/orders` POST/DELETE path.
- A guardrail test (`tests/test_no_trading.py`) statically greps the entire
  `src/` tree for `/equity/orders` and for `requests.post` / `requests.delete`
  used outside the notification module. The test suite fails if either
  pattern appears, so a future edit cannot silently reintroduce
  order-placement code.
- `config.yaml` has a `t212_env: live | demo` setting so the tool can point
  at `live.trading212.com` or `demo.trading212.com`.

## Inputs gathered from the user

- Risk tolerance: **Balanced** — blend value, quality, and momentum roughly
  evenly.
- Sector preference: **No preference** — screen/analyze across all sectors,
  no tilts or exclusions.
- Time horizon: **Long-term and medium-term** — emphasize fundamentals over
  short-term price momentum, with momentum as a secondary signal.
- Watchlist/universe: a config-file ticker list, **plus automatic inclusion
  of current T212 holdings** so holdings always appear in screener rankings.
- FMP tier: **free tier** (~250 req/day, US-listed only, some endpoints
  paywalled) — design must degrade gracefully when an endpoint isn't
  entitled.
- Environment/tooling: **uv**-managed Python project.
- Delivery/scheduling: **twice-daily** run via **Windows Task Scheduler**,
  with a brief **ntfy.sh** push notification (summary only — full detail
  stays in the local markdown report) when each report is ready.
- Bull/bear narrative generation: **rule-based templates** (deterministic,
  no LLM API key, no added cost) rather than an LLM call.

## Project structure

```
FinanceStock/
├── .env / .env.example        # API keys (gitignored)
├── config/config.yaml         # watchlist, screener weights, thresholds, t212_env, notify schedule
├── pyproject.toml             # uv-managed
├── src/finstock/
│   ├── config.py               # loads .env + config.yaml into typed settings
│   ├── clients/
│   │   ├── trading212.py       # 5 read-only GET calls only — see constraint above
│   │   ├── finnhub.py          # fundamentals, quote, price history, earnings calendar, insider txns, estimates
│   │   └── fmp.py              # fundamentals/ratios fallback, price history
│   ├── models.py               # Holding, Fundamentals, ScreenerResult dataclasses
│   ├── analysis/
│   │   ├── holdings.py         # per-holding fundamentals + bull/bear synthesis
│   │   ├── screener.py         # value/quality/momentum scoring & ranking
│   │   └── technicals.py       # 50/200-day MA, RSI(14)
│   ├── state.py                # load/save JSON snapshots for "changes since last report"
│   ├── report.py                # renders dated markdown report
│   ├── notify.py                # ntfy.sh push notification
│   └── main.py                  # orchestrates a full run
├── data/snapshots/              # one JSON per run (git-ignored; used for diffing)
├── data/reports/                # dated markdown reports (git-ignored output)
├── scripts/register_task_scheduler.ps1   # registers the two daily Task Scheduler jobs, idempotent
└── tests/
    ├── test_no_trading.py       # guardrail: no order-placement code exists
    ├── test_screener.py         # scoring math against fixed fake data
    └── test_state.py            # change-detection diff logic against fixed fake data
```

## Data layer

- **Trading 212**: heavily rate-limited per endpoint. Each of the 5 endpoints
  is called once per run (twice-daily cadence makes this a non-issue), with
  retry + backoff on HTTP 429.
- **Finnhub** (free tier, 60 calls/min): primary source for quote/price
  history, earnings calendar, insider transactions, company fundamentals.
  Token-bucket limiter keeps calls under the cap.
- **FMP** (free tier, ~250 calls/day, US-listed only): fallback/supplement
  for ratios Finnhub doesn't expose. A 402/403 response (endpoint not on the
  free plan) is caught and surfaces as `"data unavailable on current plan"`
  in the report instead of raising.
- Both clients cache responses in a per-run in-memory dict so a ticker that
  appears in both the portfolio and the watchlist is only fetched once.

## Analysis

**Per-holding** (`analysis/holdings.py`): for each T212 holding, pulls P/E,
revenue growth, margins, debt/equity, price return over 1/3/6mo vs. a
benchmark (SPY, or a sector ETF proxy where easily mapped), and next
earnings date. Rule-based templates turn these into a bull/bear paragraph
that cites the actual pulled numbers (never a bare unsupported claim).

**Screener** (`analysis/screener.py`), tuned to balanced/no-tilt/long+medium
horizon:
- Value (40%): P/E, P/B, FCF yield
- Quality (35%): ROE, debt/equity
- Momentum (25%): 50/200-day MA position (golden/death cross), RSI(14)

Each metric is percentile-ranked within the run's universe (watchlist +
current holdings), combined into a weighted composite score, sorted
descending. Weights and thresholds live in `config.yaml`, not code. Output
is observational ("ranks in top decile for FCF yield...") — never
imperative.

## Change detection

`state.py` saves a JSON snapshot per run (`data/snapshots/YYYY-MM-DD_HHMM.json`)
of each holding's key fields (price, P/E, D/E, next earnings date, position
size). The next run diffs against the prior snapshot and flags: price move
beyond a configurable threshold (default ±5%), a new/changed earnings date,
a P/E crossing a configurable band, or a position-size change (surfaced as a
factual note, since the user trades manually outside the tool).

## Report

One dated markdown file per run at `data/reports/YYYY-MM-DD_HHMM.md`:
1. Portfolio overview + cash position
2. Per-holding: fundamentals, price vs. benchmark, earnings date, bull/bear
   paragraph, "changes since last report" callout, explicit
   uncertainty/risk line (data staleness, small-sample caveats, free-tier
   data lag)
3. Screener results table + reasoning per candidate
4. Footer disclaimer: this is observational research output, not a
   recommendation

## Notification & scheduling

- `notify.py` POSTs a brief summary (portfolio value, day's biggest mover,
  top screener pick) to the user's ntfy.sh topic after the report is
  written. A notification failure never blocks the report from being saved.
- `scripts/register_task_scheduler.ps1` registers two Windows Task Scheduler
  jobs (default 08:00 / 18:00, configurable) running
  `uv run python -m finstock.main`. Idempotent — safe to re-run to update
  the schedule.

## Config & secrets

- `.env`: `T212_API_KEY`, `FINNHUB_API_KEY`, `FMP_API_KEY`, `NTFY_TOPIC`.
  `.env.example` committed with blank placeholders. `.env` and `data/` are
  gitignored (reports/snapshots may contain portfolio contents).
- `config.yaml`: `t212_env`, watchlist tickers, screener weights,
  change-detection thresholds, benchmark ticker, notification schedule
  times.

## Testing

- Unit tests for screener scoring math and change-detection diff logic
  against fixed fake data (no live API calls in tests).
- The guardrail test from the constraint section above.
- Thin integration tests per API client, skipped unless real keys are
  present in the environment.
