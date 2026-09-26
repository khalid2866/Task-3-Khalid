"""Stage 3 — Security & Moderation Gates (dual gates).

Gate 1 (pre-generation, input filtering):
    Input Payload → [Gate 1] → GPU Node
                        ↓ (rejected)
                   REJECTION (Input) — trace: sentinel_block /
                   content_policy_violation — 0 compute cost, instant rejection.

Gate 2 (post-generation, output filtering):
    GPU Node → [Gate 2] → user
                    ↓ (rejected)
               REJECTION (Output) — trace: moderation_blocked /
               finish_reason=FILTER — compute cost incurred; a blurred
               placeholder is returned instead of the asset.

Architecture rule: catch safety-related exceptions gracefully — never crash
the application; surface polite warnings to the end-user.
"""
from __future__ import annotations

import logging
import re

from PIL import Image, ImageFilter

from .exceptions import InputBlockedError, OutputBlockedError

log = logging.getLogger("studio.security")

# Local pre-filter patterns (Gate 1). Provider APIs run their own
# (stronger) moderation as well; this gate saves a wasted API call and
# demonstrates the 0-compute-cost instant rejection path.
_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    (r"\b(how to (make|build|create).{0,40}(bomb|explosive|weapon|bioweapon))\b", "weapons_instructions"),
    (r"\b(child|minor|underage).{0,30}(sexual|nude|explicit)\b", "csam"),
    (r"\b(sexual|explicit|pornographic).{0,30}(child|minor|kid)\b", "csam"),
    (r"\b(self.?harm|suicide).{0,30}(instructions|how to)\b", "self_harm"),
]


def screen_prompt(prompt: str) -> dict:
    """Gate 1 — pre-generation input filtering.

    Returns a clearance record; raises InputBlockedError on rejection.
    """
    lowered = prompt.lower()
    for pattern, category in _BLOCKED_PATTERNS:
        if re.search(pattern, lowered):
            log.warning("gate1: input rejected (category=%s)", category)
            raise InputBlockedError(
                "This prompt can't be used because it may violate content policy. "
                "Please adjust the wording and try again.",
                trace="sentinel_block",
            )
    return {"gate": 1, "verdict": "clear", "trace": None}


def screen_engine_result(result) -> dict:
    """Gate 2 — post-generation output filtering.

    Inspects the engine result for provider moderation flags.
    Raises OutputBlockedError on rejection; otherwise returns clearance.
    """
    trace = getattr(result, "blocked_trace", None)
    if trace in ("moderation_blocked", "FILTER", "content_policy_violation"):
        log.warning("gate2: output rejected (trace=%s)", trace)
        raise OutputBlockedError(
            "The generated image was blocked by the safety filter, so it can't "
            "be displayed. Try rephrasing your prompt.",
            trace="moderation_blocked" if trace != "FILTER" else "finish_reason=FILTER",
        )
    return {"gate": 2, "verdict": "clear", "trace": None}


def blurred_placeholder(width: int, height: int, path: str) -> str:
    """Build the blurred placeholder returned after a Gate 2 rejection."""
    img = Image.new("RGB", (width, height), (38, 44, 58))
    img = img.filter(ImageFilter.GaussianBlur(radius=24))
    img.save(path, "PNG")
    return path


# Polite, user-facing copy for each safety outcome (never a stack trace).
POLITE_MESSAGES = {
    "sentinel_block": (
        "Your prompt was stopped by the input safety filter before any "
        "image was generated (no usage was consumed). Please rephrase it "
        "and try again."
    ),
    "moderation_blocked": (
        "The image that came back was stopped by the output safety filter, "
        "so it can't be shown. Try a different prompt."
    ),
}
