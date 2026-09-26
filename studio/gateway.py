"""Stage 2 — Network API Gateway.

Implements the blueprint's split-timeout timeline and exception-handling
matrix:

* ``timeout=(3.05, 60)`` — 3.05s connect timeout (3s + 0.05s TCP
  retransmission buffer), 60s read timeout for slow iterative diffusion on
  remote GPU clusters.
* ``requests.exceptions.ConnectTimeout`` → NETWORK FAILURE → **FAIL FAST**,
  no retry (routing issue / firewall / downed server).
* ``requests.exceptions.ReadTimeout`` → INFERENCE FAILURE → keep the
  connection alive longer, retry with **exponential backoff + jitter**.
* Retry selectively on HTTP 429 (Too Many Requests) and 503
  (Service Unavailable) only — never hammer a dying server.
"""
from __future__ import annotations

import logging
import random
import time

import requests

from .exceptions import InferenceFailure, NetworkFailure, StudioError

log = logging.getLogger("studio.gateway")

# Blueprint-specified split timeout: (connect, read) in seconds.
CONNECT_TIMEOUT = 3.05
READ_TIMEOUT = 60.0
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

MAX_ATTEMPTS = 5
BACKOFF_BASE = 2.0        # wait = min(2**attempt, cap)
BACKOFF_CAP = 30.0        # seconds, before jitter
RETRYABLE_STATUS = {429, 503}


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with full jitter (rule 2 of the resilience page)."""
    delay = min(BACKOFF_BASE ** attempt, BACKOFF_CAP)
    return delay + random.uniform(0, 1.0)


def resilient_post(url: str, *, json=None, data=None, files=None,
                   headers: dict | None = None,
                   timeout: tuple[float, float] = TIMEOUT,
                   max_attempts: int = MAX_ATTEMPTS) -> requests.Response:
    """POST with split timeouts, fail-fast connect handling and smart retries."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(
                url, json=json, data=data, files=files,
                headers=headers or {}, timeout=timeout,
            )
        except requests.exceptions.ConnectTimeout as exc:
            # NETWORK FAILURE — fail fast, do not wait, do not retry.
            raise NetworkFailure(
                "Could not establish a TCP connection within "
                f"{timeout[0]}s (routing issue, strict firewall, or downed "
                f"server): {exc}"
            ) from exc
        except requests.exceptions.ReadTimeout as exc:
            # INFERENCE FAILURE — server connected but slow; retry w/ backoff.
            last_error = InferenceFailure(
                f"Server took too long to send data (overloaded GPU cluster "
                f"or massive payload): {exc}"
            )
        except requests.exceptions.RequestException as exc:
            last_error = StudioError(f"Request failed: {exc}")
        else:
            if resp.status_code in RETRYABLE_STATUS:
                last_error = InferenceFailure(
                    f"HTTP {resp.status_code} from API gateway — retrying with "
                    "backoff instead of hammering the server."
                )
            elif 400 <= resp.status_code < 600:
                raise StudioError(
                    f"HTTP {resp.status_code}: {resp.text[:500]}"
                )
            else:
                return resp

        if attempt < max_attempts:
            delay = _backoff_delay(attempt)
            log.warning("gateway: attempt %d failed (%s); retrying in %.1fs",
                        attempt, last_error, delay)
            time.sleep(delay)

    raise last_error  # type: ignore[misc]


def resilient_get_stream(url: str, *, headers: dict | None = None,
                         timeout: tuple[float, float] = TIMEOUT,
                         max_attempts: int = MAX_ATTEMPTS) -> requests.Response:
    """Streaming GET with the same resilience policy (used by Stage 4)."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, headers=headers or {},
                                timeout=timeout, stream=True)
        except requests.exceptions.ConnectTimeout as exc:
            raise NetworkFailure(
                f"Could not establish a TCP connection within {timeout[0]}s: {exc}"
            ) from exc
        except requests.exceptions.ReadTimeout as exc:
            last_error = InferenceFailure(f"Read timeout while streaming: {exc}")
        except requests.exceptions.RequestException as exc:
            last_error = StudioError(f"Streaming request failed: {exc}")
        else:
            if resp.status_code in RETRYABLE_STATUS:
                resp.close()
                last_error = InferenceFailure(
                    f"HTTP {resp.status_code} while streaming — retrying with backoff."
                )
            elif 400 <= resp.status_code < 600:
                resp.close()
                raise StudioError(f"HTTP {resp.status_code} while streaming: {url}")
            else:
                return resp

        if attempt < max_attempts:
            delay = _backoff_delay(attempt)
            log.warning("gateway: stream attempt %d failed (%s); retrying in %.1fs",
                        attempt, last_error, delay)
            time.sleep(delay)

    raise last_error  # type: ignore[misc]
