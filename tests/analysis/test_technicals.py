# tests/analysis/test_technicals.py
from finstock.analysis.technicals import rsi, simple_moving_average


def test_simple_moving_average_over_window():
    prices = [10, 20, 30, 40, 50]
    assert simple_moving_average(prices, window=3) == 40.0  # avg of 30,40,50


def test_simple_moving_average_returns_none_when_insufficient_data():
    assert simple_moving_average([10, 20], window=5) is None


def test_rsi_all_gains_is_100():
    prices = [float(i) for i in range(1, 16)]  # strictly increasing
    assert rsi(prices, period=14) == 100.0


def test_rsi_returns_none_when_insufficient_data():
    assert rsi([1.0, 2.0], period=14) is None
