# tests/clients/test_finnhub.py
import responses

from finstock.clients.finnhub import FinnhubClient


@responses.activate
def test_quote_includes_api_token_and_symbol():
    responses.get(
        "https://finnhub.io/api/v1/quote",
        json={"c": 150.0},
        status=200,
    )
    client = FinnhubClient(api_key="fh-key")

    result = client.quote("AAPL")

    assert result == {"c": 150.0}
    req = responses.calls[0].request
    assert "token=fh-key" in req.url
    assert "symbol=AAPL" in req.url


@responses.activate
def test_insider_transactions_retries_on_500():
    responses.get(
        "https://finnhub.io/api/v1/stock/insider-transactions",
        status=500,
    )
    responses.get(
        "https://finnhub.io/api/v1/stock/insider-transactions",
        json={"data": []},
        status=200,
    )
    client = FinnhubClient(api_key="fh-key")
    client._sleep = lambda seconds: None

    result = client.insider_transactions("AAPL")

    assert result == {"data": []}
