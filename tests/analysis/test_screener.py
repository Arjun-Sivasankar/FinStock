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
