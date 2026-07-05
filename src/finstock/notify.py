from __future__ import annotations

import requests


def send_notification(ntfy_topic: str, title: str, message: str) -> bool:
    try:
        resp = requests.post(
            f"https://ntfy.sh/{ntfy_topic}",
            data=message.encode("utf-8"),
            headers={"Title": title},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException:
        return False
