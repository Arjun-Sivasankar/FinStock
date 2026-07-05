from __future__ import annotations


def simple_moving_average(prices: list[float], window: int) -> float | None:
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = prices[-i] - prices[-i - 1]
        if delta >= 0:
            gains.append(delta)
        else:
            losses.append(-delta)
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
