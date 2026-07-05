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
