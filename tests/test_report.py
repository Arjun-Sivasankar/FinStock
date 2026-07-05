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
