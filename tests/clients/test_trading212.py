import responses

from finstock.clients.trading212 import Trading212Client


@responses.activate
def test_get_portfolio_returns_json():
    responses.get(
        "https://demo.trading212.com/api/v0/equity/portfolio",
        json=[{"ticker": "AAPL_US_EQ", "quantity": 10}],
        status=200,
    )
    client = Trading212Client(api_key="key", base_url="https://demo.trading212.com/api/v0")

    result = client.get_portfolio()

    assert result == [{"ticker": "AAPL_US_EQ", "quantity": 10}]
    assert responses.calls[0].request.headers["Authorization"] == "key"


@responses.activate
def test_get_cash_retries_on_429_then_succeeds():
    responses.get(
        "https://demo.trading212.com/api/v0/equity/account/cash",
        status=429,
    )
    responses.get(
        "https://demo.trading212.com/api/v0/equity/account/cash",
        json={"free": 100.0},
        status=200,
    )
    client = Trading212Client(api_key="key", base_url="https://demo.trading212.com/api/v0")
    client._sleep = lambda seconds: None  # skip real sleeps in test

    result = client.get_cash()

    assert result == {"free": 100.0}


@responses.activate
def test_get_cash_raises_after_exhausting_retries():
    for _ in range(4):
        responses.get(
            "https://demo.trading212.com/api/v0/equity/account/cash",
            status=429,
        )
    client = Trading212Client(api_key="key", base_url="https://demo.trading212.com/api/v0")
    client._sleep = lambda seconds: None

    try:
        client.get_cash()
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
