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
