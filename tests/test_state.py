# tests/test_state.py
import json
from datetime import datetime

from finstock.state import HoldingSnapshot, diff_snapshots, load_latest_snapshot, save_snapshot


def test_save_and_load_latest_snapshot(tmp_path):
    holdings = [
        HoldingSnapshot(symbol="AAPL", price=200.0, pe_ratio=18.0, debt_to_equity=1.4,
                         next_earnings_date="2026-08-01", quantity=10),
    ]
    save_snapshot(tmp_path, holdings, timestamp=datetime(2026, 7, 5, 8, 0))

    loaded = load_latest_snapshot(tmp_path)

    assert loaded["holdings"][0]["symbol"] == "AAPL"
    assert loaded["holdings"][0]["price"] == 200.0


def test_load_latest_snapshot_returns_none_when_no_history(tmp_path):
    assert load_latest_snapshot(tmp_path / "does-not-exist") is None


def test_diff_flags_price_move_beyond_threshold():
    previous = {"holdings": [{"symbol": "AAPL", "price": 200.0, "pe_ratio": 18.0,
                               "next_earnings_date": "2026-08-01", "quantity": 10}]}
    current = [HoldingSnapshot(symbol="AAPL", price=215.0, pe_ratio=18.0, debt_to_equity=1.4,
                                next_earnings_date="2026-08-01", quantity=10)]

    changes = diff_snapshots(previous, current, price_move_pct=5.0, pe_band_pct=15.0)

    assert "AAPL" in changes
    assert any("7.5%" in note for note in changes["AAPL"])


def test_diff_returns_empty_when_no_prior_snapshot():
    current = [HoldingSnapshot(symbol="AAPL", price=200.0, pe_ratio=18.0, debt_to_equity=1.4,
                                next_earnings_date="2026-08-01", quantity=10)]

    changes = diff_snapshots(None, current, price_move_pct=5.0, pe_band_pct=15.0)

    assert changes == {}


def test_diff_flags_position_size_change():
    previous = {"holdings": [{"symbol": "AAPL", "price": 200.0, "pe_ratio": 18.0,
                               "next_earnings_date": "2026-08-01", "quantity": 10}]}
    current = [HoldingSnapshot(symbol="AAPL", price=200.0, pe_ratio=18.0, debt_to_equity=1.4,
                                next_earnings_date="2026-08-01", quantity=15)]

    changes = diff_snapshots(previous, current, price_move_pct=5.0, pe_band_pct=15.0)

    assert any("15" in note and "10" in note for note in changes["AAPL"])
