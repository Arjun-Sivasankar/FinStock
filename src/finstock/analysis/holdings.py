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
