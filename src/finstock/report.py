from __future__ import annotations

from datetime import datetime
from pathlib import Path

from finstock.analysis.holdings import HoldingAnalysis
from finstock.models import ScreenerResult

DISCLAIMER = (
    "This report is observational research output generated from third-party "
    "data and is **not a recommendation** to buy, sell, or hold any security. "
    "All figures may be delayed or incomplete due to free-tier data limits. "
    "You are the sole decision-maker on any transaction."
)


def render_report(
    generated_at: datetime,
    cash_free: float,
    cash_total: float,
    portfolio_value: float,
    holding_analyses: list[HoldingAnalysis],
    changes_by_symbol: dict[str, list[str]],
    screener_results: list[ScreenerResult],
    first_run: bool,
    recent_orders: list[str],
    recent_dividends: list[str],
) -> str:
    lines = [
        "# FinStock Report",
        "",
        f"Generated: {generated_at.isoformat()}",
        "",
        "## Portfolio overview",
        "",
        f"- Free cash: {cash_free}",
        f"- Total cash: {cash_total}",
        f"- Portfolio value: {portfolio_value}",
        "",
    ]

    if first_run:
        lines.append("_First run — no prior snapshot to compare._")
        lines.append("")

    lines.append("## Recent activity")
    lines.append("")
    lines.append("**Orders (last period):**")
    for entry in recent_orders:
        lines.append(f"- {entry}")
    lines.append("")
    lines.append("**Dividends (last period):**")
    for entry in recent_dividends:
        lines.append(f"- {entry}")
    lines.append("")

    lines.append("## Holdings")
    lines.append("")
    for analysis in holding_analyses:
        lines.append(f"### {analysis.symbol}")
        lines.append("")
        if analysis.symbol in changes_by_symbol:
            lines.append("**Changes since last report:**")
            for note in changes_by_symbol[analysis.symbol]:
                lines.append(f"- {note}")
            lines.append("")
        if analysis.bull_points:
            lines.append("**Bull points:**")
            for point in analysis.bull_points:
                lines.append(f"- {point}")
            lines.append("")
        if analysis.bear_points:
            lines.append("**Bear points:**")
            for point in analysis.bear_points:
                lines.append(f"- {point}")
            lines.append("")
        if analysis.uncertainty_notes:
            lines.append("**Uncertainty / risk notes:**")
            for note in analysis.uncertainty_notes:
                lines.append(f"- {note}")
            lines.append("")

    lines.append("## Screener results")
    lines.append("")
    for rank, result in enumerate(screener_results, start=1):
        lines.append(
            f"{rank}. **{result.symbol}** — composite {result.composite_score:.2f} "
            f"(value {result.value_score:.2f}, quality {result.quality_score:.2f}, "
            f"momentum {result.momentum_score:.2f})"
        )
        for reason in result.reasoning:
            lines.append(f"   - {reason}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(DISCLAIMER)

    return "\n".join(lines)


def save_report(reports_dir: Path, timestamp: datetime, content: str) -> Path:
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{timestamp.strftime('%Y-%m-%d_%H%M')}.md"
    path.write_text(content)
    return path
