# tests/test_notify.py
import responses

from finstock.notify import send_notification


@responses.activate
def test_send_notification_posts_to_ntfy_topic():
    responses.post("https://ntfy.sh/my-topic", status=200)

    result = send_notification("my-topic", title="FinStock report ready", message="Cash: 1000")

    assert result is True
    assert responses.calls[0].request.headers["Title"] == "FinStock report ready"


@responses.activate
def test_send_notification_returns_false_on_failure():
    responses.post("https://ntfy.sh/my-topic", status=500)

    result = send_notification("my-topic", title="FinStock report ready", message="Cash: 1000")

    assert result is False
