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
- All HTTP calls in the project use the `requests` library (no other HTTP
  client is introduced), so the guardrail below has one library surface to
  check.
- A guardrail test (`tests/test_no_trading.py`) enforces two things:
  1. **AST check on `clients/trading212.py` specifically**: parses the file
     and asserts the only `requests.*` calls present are `requests.get`. Any
     `requests.post`/`put`/`patch`/`delete` in that module fails the test.
     This is the primary guarantee — it doesn't depend on catching a
     particular URL string, so dynamically-built endpoint paths don't slip
     past it.
  2. **Repo-wide grep** for the literal substring `/equity/orders` anywhere
     under `src/`. Fails the test if found anywhere outside a code comment
     explaining why it's disallowed (i.e. it should never appear as part of
     a constructed URL).
  - `requests.post` is allowed in exactly one file: `notify.py` (for the
    ntfy.sh push). The test asserts no other file under `src/` calls
    `requests.post`/`put`/`patch`/`delete`.
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
  is called once per run (twice-daily cadence makes this a non-issue).
  Retry policy: up to 3 attempts on HTTP 429/5xx/timeout, backoff 2s / 5s /
  10s. If `/equity/portfolio` or `/equity/account/cash` still fails after
  retries (e.g. bad/expired key), the run **aborts** — there's no
  meaningful report without portfolio data — and a failure notification
  ("FinStock run failed: <reason>") is sent via ntfy instead of a report
  summary. If only `/equity/history/orders` or `/equity/history/dividends`
  fails, the run continues and that section is marked
  `"data unavailable this run"` in the report.
- **Finnhub** (free tier, 60 calls/min): primary source for quote/price
  history, earnings calendar, insider transactions, analyst estimates, and
  company fundamentals. Token-bucket limiter keeps calls under the cap.
  Retry policy: up to 3 attempts, backoff 1s / 2s / 4s, on 429/5xx/timeout.
- **FMP** (free tier, ~250 calls/day, US-listed only): fallback/supplement
  for ratios Finnhub doesn't expose. Same retry policy as Finnhub. A
  402/403 response (endpoint not on the free plan) is caught immediately
  (no retry) and surfaces as `"data unavailable on current plan"` in the
  report instead of raising.
- On any per-ticker failure that survives retries, that ticker's affected
  field(s) are marked unavailable in its report section rather than
  aborting the whole run — only a failure of core T212 portfolio/cash data
  aborts the run.
- Both clients cache responses in a per-run in-memory dict so a ticker that
  appears in both the portfolio and the watchlist is only fetched once.
- **FMP daily budget**: with two runs/day and a ~250 call/day cap, each run
  has a soft budget of ~120 FMP calls. Tickers are prioritized
  highest-first: current T212 holdings, then watchlist tickers in the
  order listed in `config.yaml`. If the universe would exceed the budget,
  remaining lower-priority tickers skip FMP enrichment for that run (they
  still get full Finnhub data) and are marked `"FMP data skipped this run
  (daily budget)"`.
- **Ticker mapping**: T212's portfolio endpoint returns its own instrument
  codes (e.g. `AAPL_US_EQ`), not bare tickers. `models.py` derives a base
  ticker by taking the substring before the first `_` (covers the common
  `TICKER_EXCHANGE_TYPE` pattern for US-listed equities). Since FMP's free
  tier is US-listed-only anyway, non-US holdings are expected to hit
  degraded/unavailable data — `config.yaml` supports an optional
  `ticker_overrides:` map (T212 code → Finnhub/FMP symbol) for any holding
  where the automatic derivation doesn't produce a queryable symbol.

## Analysis

**Per-holding** (`analysis/holdings.py`): for each T212 holding, pulls P/E,
revenue growth, margins, debt/equity, price return over 1/3/6mo vs. a single
configured benchmark ticker (default `SPY` — no per-sector ETF mapping,
consistent with "no sector preference"), next earnings date, recent insider
transaction activity (net buying/selling in the trailing quarter), and
analyst consensus (rating + price target) from Finnhub. Rule-based templates
turn these into a bull/bear paragraph that cites the actual pulled numbers
(never a bare unsupported claim) — e.g. insider net buying and a
below-average P/E feed the bull side; analyst price target below the
current price feeds the bear side.

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
factual note, since the user trades manually outside the tool). **First-ever
run**: if `data/snapshots/` has no prior file, change detection is skipped
entirely and the report notes `"First run — no prior snapshot to compare."`
instead of attempting a diff.

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
  times. Example shape:

  ```yaml
  t212_env: live          # live | demo

  benchmark_ticker: SPY

  watchlist:
    - MSFT
    - GOOGL
    - NVDA

  ticker_overrides:        # T212 instrument code -> Finnhub/FMP symbol
    VOD_LON_EQ: VOD.L

  screener:
    weights:
      value: 0.40
      quality: 0.35
      momentum: 0.25

  change_detection:
    price_move_pct: 5.0
    pe_band_pct: 15.0

  notify:
    ntfy_topic_env_var: NTFY_TOPIC   # actual topic name comes from .env
    schedule_times: ["08:00", "18:00"]
  ```

## Testing

- Unit tests for screener scoring math and change-detection diff logic
  against fixed fake data (no live API calls in tests).
- The guardrail test from the constraint section above.
- Thin integration tests per API client, skipped unless real keys are
  present in the environment.
