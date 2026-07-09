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
