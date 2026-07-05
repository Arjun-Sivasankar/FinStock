import textwrap
from pathlib import Path

from finstock.config import load_settings


def test_load_settings_reads_yaml_and_env(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(textwrap.dedent("""\
        t212_env: demo
        benchmark_ticker: SPY
        watchlist: [MSFT, GOOGL]
        ticker_overrides:
          VOD_LON_EQ: VOD.L
        screener:
          weights:
            value: 0.4
            quality: 0.35
            momentum: 0.25
        change_detection:
          price_move_pct: 5.0
          pe_band_pct: 15.0
        notify:
          schedule_times: ["08:00", "18:00"]
    """))
    env_path = tmp_path / ".env"
    env_path.write_text(
        "T212_API_KEY=t212-key\n"
        "FINNHUB_API_KEY=finnhub-key\n"
        "FMP_API_KEY=fmp-key\n"
        "NTFY_TOPIC=my-topic\n"
    )

    settings = load_settings(config_path=config_path, env_path=env_path)

    assert settings.t212_env == "demo"
    assert settings.t212_api_key == "t212-key"
    assert settings.benchmark_ticker == "SPY"
    assert settings.watchlist == ["MSFT", "GOOGL"]
    assert settings.ticker_overrides == {"VOD_LON_EQ": "VOD.L"}
    assert settings.screener_weights.value == 0.4
    assert settings.change_detection.price_move_pct == 5.0
    assert settings.notify.ntfy_topic == "my-topic"
    assert settings.notify.schedule_times == ["08:00", "18:00"]
    assert settings.t212_base_url == "https://demo.trading212.com/api/v0"
