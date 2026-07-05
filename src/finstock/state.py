from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class HoldingSnapshot:
    symbol: str
    price: float
    pe_ratio: float | None
    debt_to_equity: float | None
    next_earnings_date: str | None
    quantity: float


def save_snapshot(snapshots_dir: Path, holdings: list[HoldingSnapshot], timestamp: datetime) -> Path:
    snapshots_dir = Path(snapshots_dir)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    path = snapshots_dir / f"{timestamp.strftime('%Y-%m-%d_%H%M')}.json"
    payload = {"timestamp": timestamp.isoformat(), "holdings": [asdict(h) for h in holdings]}
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_latest_snapshot(snapshots_dir: Path) -> dict | None:
    snapshots_dir = Path(snapshots_dir)
    if not snapshots_dir.exists():
        return None
    files = sorted(snapshots_dir.glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text())


def diff_snapshots(
    previous: dict | None,
    current: list[HoldingSnapshot],
    price_move_pct: float,
    pe_band_pct: float,
) -> dict[str, list[str]]:
    changes: dict[str, list[str]] = {}
    if previous is None:
        return changes

    prev_by_symbol = {h["symbol"]: h for h in previous["holdings"]}
    for holding in current:
        prev = prev_by_symbol.get(holding.symbol)
        if prev is None:
            changes[holding.symbol] = ["New holding since last report."]
            continue

        notes: list[str] = []
        if prev.get("price"):
            pct_move = (holding.price - prev["price"]) / prev["price"] * 100
            if abs(pct_move) >= price_move_pct:
                notes.append(f"Price moved {pct_move:+.1f}% since last report.")
        if prev.get("pe_ratio") and holding.pe_ratio:
            pe_move = (holding.pe_ratio - prev["pe_ratio"]) / prev["pe_ratio"] * 100
            if abs(pe_move) >= pe_band_pct:
                notes.append(f"P/E moved {pe_move:+.1f}% since last report.")
        if prev.get("next_earnings_date") != holding.next_earnings_date:
            notes.append(f"Earnings date changed to {holding.next_earnings_date}.")
        if prev.get("quantity") != holding.quantity:
            notes.append(
                f"Position size changed from {prev['quantity']} to {holding.quantity} shares."
            )
        if notes:
            changes[holding.symbol] = notes

    return changes
