# tests/clients/test_fmp.py
import pytest
import responses

from finstock.clients.fmp import FMPClient, FMPNotEntitledError


@responses.activate
def test_key_metrics_increments_calls_made():
    responses.get(
        "https://financialmodelingprep.com/api/v3/key-metrics/AAPL",
        json=[{"peRatio": 18.0}],
        status=200,
    )
    client = FMPClient(api_key="fmp-key")

    result = client.key_metrics("AAPL")

    assert result == [{"peRatio": 18.0}]
    assert client.calls_made == 1


@responses.activate
def test_not_entitled_response_raises_without_retry():
    responses.get(
        "https://financialmodelingprep.com/api/v3/ratios/AAPL",
        status=403,
    )
    client = FMPClient(api_key="fmp-key")

    with pytest.raises(FMPNotEntitledError):
        client.ratios("AAPL")

    assert len(responses.calls) == 1  # no retry on 403
    assert client.calls_made == 0
