"""Shared exception types for the Image Generation Studio pipeline.

Each error maps to a named failure in the Project 3 blueprint so the
pipeline can react correctly (fail fast vs. retry vs. polite warning).
"""
from __future__ import annotations


class StudioError(Exception):
    """Base class for all studio pipeline errors."""


class UnsupportedDimensionsError(StudioError):
    """Stage 1 — an aspect ratio outside the strict resolution map was requested.

    Blueprint rule: passing unsupported dimensions causes an immediate API
    handshake failure, so we refuse before any payload is transmitted.
    """


class PromptTooLongError(StudioError):
    """Stage 1 — prompt exceeds the selected engine's character limit."""


class InputBlockedError(StudioError):
    """Stage 3, Gate 1 — pre-generation input filter rejection.

    Error traces: ``sentinel_block`` / ``content_policy_violation``.
    Compute impact: 0 — instant rejection, no GPU cost incurred.
    """

    def __init__(self, message: str, trace: str = "sentinel_block"):
        super().__init__(message)
        self.trace = trace


class OutputBlockedError(StudioError):
    """Stage 3, Gate 2 — post-generation output filter rejection.

    Error traces: ``moderation_blocked`` / ``finish_reason=FILTER``.
    Compute impact: cost already incurred; a blurred placeholder is returned.
    """

    def __init__(self, message: str, trace: str = "moderation_blocked"):
        super().__init__(message)
        self.trace = trace


class NetworkFailure(StudioError):
    """Stage 2 — TCP connection could not be established (ConnectTimeout).

    Architecture rule: FAIL FAST. Do not wait, do not retry the connection.
    """


class InferenceFailure(StudioError):
    """Stage 2 — server connected but too slow (ReadTimeout) or 429/503.

    Architecture rule: keep the connection alive longer and prepare for
    secondary retries with exponential backoff + jitter.
    """


class CorruptedAssetError(StudioError):
    """Stage 5 — pixel-level decode failed (``OSError: broken data stream``).

    The truncated asset is discarded and the pipeline requests a retry.
    """


class QARejectedError(StudioError):
    """Stage 6 — asset failed automated quality assurance."""

    def __init__(self, message: str, lens: str = "aesthetic", score: float = 0.0):
        super().__init__(message)
        self.lens = lens
        self.score = score
