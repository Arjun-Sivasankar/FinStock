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
