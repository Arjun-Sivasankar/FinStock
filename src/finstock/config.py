from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class ScreenerWeights:
    value: float
    quality: float
    momentum: float


@dataclass
class ChangeDetectionThresholds:
    price_move_pct: float
    pe_band_pct: float


@dataclass
class NotifyConfig:
    ntfy_topic: str
    schedule_times: list[str]


@dataclass
class Settings:
    t212_env: str
    t212_api_key: str
    finnhub_api_key: str
    fmp_api_key: str
    benchmark_ticker: str
    watchlist: list[str]
    ticker_overrides: dict[str, str]
    screener_weights: ScreenerWeights
    change_detection: ChangeDetectionThresholds
    notify: NotifyConfig

    @property
    def t212_base_url(self) -> str:
        if self.t212_env == "live":
            return "https://live.trading212.com/api/v0"
        if self.t212_env == "demo":
            return "https://demo.trading212.com/api/v0"
        raise ValueError(f"Unknown t212_env: {self.t212_env!r}")


def load_settings(
    config_path: Path | str = "config/config.yaml",
    env_path: Path | str = ".env",
) -> Settings:
    load_dotenv(env_path)
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    return Settings(
        t212_env=raw["t212_env"],
        t212_api_key=os.environ["T212_API_KEY"],
        finnhub_api_key=os.environ["FINNHUB_API_KEY"],
        fmp_api_key=os.environ["FMP_API_KEY"],
        benchmark_ticker=raw["benchmark_ticker"],
        watchlist=list(raw.get("watchlist", [])),
        ticker_overrides=dict(raw.get("ticker_overrides") or {}),
        screener_weights=ScreenerWeights(**raw["screener"]["weights"]),
        change_detection=ChangeDetectionThresholds(**raw["change_detection"]),
        notify=NotifyConfig(
            ntfy_topic=os.environ["NTFY_TOPIC"],
            schedule_times=list(raw["notify"]["schedule_times"]),
        ),
    )
