import logging
import time
from email.utils import parsedate_to_datetime

import requests

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _retry_after_seconds(header_value: str | None) -> float | None:
    if not header_value:
        return None

    try:
        seconds = float(header_value)
        return max(0.0, seconds)
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(header_value)
        return max(0.0, retry_at.timestamp() - time.time())
    except (TypeError, ValueError, OverflowError):
        return None


def _backoff_seconds(attempt: int, base_delay: float) -> float:
    return base_delay * (2 ** (attempt - 1))


def request_with_retries(
    method: str,
    url: str,
    *,
    timeout: float,
    max_retries: int = 2,
    retryable_status_codes: set[int] | None = None,
    base_delay: float = 1.0,
    raise_for_status: bool = True,
    operation_name: str | None = None,
    **kwargs,
) -> requests.Response:
    """Send an HTTP request with retry support for transient failures."""
    retry_statuses = retryable_status_codes or RETRYABLE_STATUS_CODES
    max_attempts = max_retries + 1
    method_upper = method.upper()
    op_name = operation_name or f"{method_upper} {url}"

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.request(method_upper, url, timeout=timeout, **kwargs)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as err:
            if attempt == max_attempts:
                raise
            delay = _backoff_seconds(attempt, base_delay)
            logger.warning(
                "%s failed with %s (attempt %d/%d), retrying in %.1fs",
                op_name,
                err.__class__.__name__,
                attempt,
                max_attempts,
                delay,
            )
            time.sleep(delay)
            continue

        if response.status_code in retry_statuses and attempt < max_attempts:
            delay = _retry_after_seconds(response.headers.get("Retry-After"))
            if delay is None:
                delay = _backoff_seconds(attempt, base_delay)
            logger.warning(
                "%s returned %d (attempt %d/%d), retrying in %.1fs",
                op_name,
                response.status_code,
                attempt,
                max_attempts,
                delay,
            )
            time.sleep(delay)
            continue

        if raise_for_status:
            response.raise_for_status()
        return response

    raise RuntimeError(f"Unreachable retry branch for {op_name}")
