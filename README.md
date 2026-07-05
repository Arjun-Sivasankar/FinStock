# FinStock

A personal, strictly read-only investment research tool. Pulls Trading 212
portfolio data plus Finnhub/FMP market data, runs rule-based analysis, and
writes a dated markdown report twice a day. It never places, modifies, or
cancels orders — see `docs/superpowers/specs/2026-07-05-finstock-research-tool-design.md`.

## Setup

1. `uv sync`
2. Copy `.env.example` to `.env` and fill in your API keys
3. Edit `config/config.yaml` for your watchlist and preferences
4. `uv run python -m finstock.main`
5. To schedule twice-daily runs: `powershell scripts/register_task_scheduler.ps1`
