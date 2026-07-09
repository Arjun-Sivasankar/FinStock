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
