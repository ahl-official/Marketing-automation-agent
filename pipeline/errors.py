"""
Shared error handling and retry utilities.

This module is the direct equivalent of the n8n Error Handler workflow:
any unhandled exception in main.py gets caught, logged, and posted to
the Slack alerts channel with enough detail to debug it.
"""

import functools
import logging
import time
import traceback
from datetime import datetime, timezone

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("research_agent")


def retry(max_tries: int = 3, wait_seconds: float = 4.0, exceptions=(Exception,)):
    """Decorator: retries a function on failure with linear backoff.
    Equivalent to n8n's 'Retry on Fail' node setting."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_tries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.warning(
                        "Attempt %s/%s failed for %s: %s",
                        attempt, max_tries, func.__name__, exc,
                    )
                    if attempt < max_tries:
                        time.sleep(wait_seconds * attempt)
            raise last_exc

        return wrapper

    return decorator


def safe_branch(default=None):
    """Decorator for data-collection branches: on failure, log and return
    a default (usually an empty list) instead of killing the whole run.
    Equivalent to n8n's onError: continueRegularOutput setting."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.error("Branch %s failed, continuing with empty result: %s", func.__name__, exc)
                return default if default is not None else []

        return wrapper

    return decorator


def post_slack_alert(slack_bot_token: str, channel: str, text: str) -> None:
    """Post a message to Slack. Used both for validation-gate failures
    and for hard pipeline errors (see main.py's top-level except block)."""
    try:
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {slack_bot_token}"},
            json={"channel": channel, "text": text},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.error("Slack alert failed to send: %s", data.get("error"))
    except Exception as exc:  # noqa: BLE001
        # Last resort: if even the alert can't be sent, at least log loudly.
        logger.critical("Could not reach Slack to send alert: %s", exc)


def format_exception_alert(workflow_name: str, exc: Exception) -> str:
    return (
        f"*{workflow_name} run failed*\n"
        f"*Error:* {exc}\n"
        f"*Time:* {datetime.now(timezone.utc).isoformat()}\n"
        f"```{''.join(traceback.format_exception(exc))[:2500]}```"
    )
