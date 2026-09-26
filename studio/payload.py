"""Stage 1 — Prompt Payload Formulation.

Translates user intent (aspect-ratio choice) into exact, strict pixel
payloads and enforces each engine's prompt constraints *before* anything is
transmitted — per the blueprint's critical architecture rule:

    "Passing unsupported dimensions causes immediate API handshake failure.
     Always map user intent to exact strict resolution variables before
     transmitting the payload."
"""
from __future__ import annotations

from dataclasses import dataclass

from .exceptions import PromptTooLongError, UnsupportedDimensionsError

# ── Strict aspect-ratio → pixel payload map (from the blueprint) ──────────────
ASPECT_MAP: dict[str, dict] = {
    "16:9": {
        "width": 1344,
        "height": 768,
        "pixel_volume": 1_032_192,
        "target": "Web banners, presentations",
    },
    "1:1": {
        "width": 1024,
        "height": 1024,
        "pixel_volume": 1_048_576,
        "target": "Avatars, product grids",
    },
    "9:16": {
        "width": 768,
        "height": 1344,
        "pixel_volume": 1_032_192,
        "target": "Mobile reels, wallpapers",
    },
}

# ── Engine constraint matrix (from "Navigating the Multimodal Engine Matrix") ─
ENGINE_SPECS: dict[str, dict] = {
    "gpt-image": {
        "label": "gpt-image series (Azure / Foundry)",
        "prompt_limit": 4_000,
        "output_format": "Base64 JSON (b64_json)",
        "note": "DALL-E 3 retired March 2026 — enterprise systems must migrate to gpt-image.",
        "needs_key": "OPENAI_API_KEY",
    },
    "stability": {
        "label": "Stable Image Core (Stability AI)",
        "prompt_limit": 10_000,
        "output_format": "RAW image bytes or Base64 JSON",
        "note": "Optimized for fast, high-quality REST v2beta iteration.",
        "needs_key": "STABILITY_API_KEY",
    },
    "wan": {
        "label": "Wan Text-to-Image v2 (Alibaba Cloud)",
        "prompt_limit": 1_000,
        "output_format": "Public image URL or PNG binary",
        "note": "Artistic and photorealistic standard resolution.",
        "needs_key": "DASHSCOPE_API_KEY",
    },
    "demo": {
        "label": "Demo engine (offline, no key required)",
        "prompt_limit": 10_000,
        "output_format": "RAW PNG bytes (generated locally)",
        "note": "Local Pillow renderer for testing the full pipeline without API keys.",
        "needs_key": None,
    },
}


@dataclass(frozen=True)
class GenerationPayload:
    """A fully validated, transmission-ready generation request."""

    prompt: str
    engine: str
    aspect: str
    width: int
    height: int
    pixel_volume: int
    target_use: str


def build_generation_payload(prompt: str, engine: str, aspect: str) -> GenerationPayload:
    """Validate user intent and produce the exact payload variables.

    Raises:
        UnsupportedDimensionsError: aspect ratio not in the strict map.
        PromptTooLongError: prompt exceeds the engine's character limit.
        ValueError: unknown engine or empty prompt.
    """
    engine = (engine or "").strip().lower()
    if engine not in ENGINE_SPECS:
        raise ValueError(
            f"Unknown engine '{engine}'. Choose from: {', '.join(sorted(ENGINE_SPECS))}"
        )

    aspect = (aspect or "").strip()
    if aspect not in ASPECT_MAP:
        raise UnsupportedDimensionsError(
            f"Unsupported dimensions '{aspect}'. Allowed aspect ratios are "
            f"{', '.join(sorted(ASPECT_MAP))} — arbitrary sizes are refused to "
            "avoid an API handshake failure."
        )

    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Prompt must not be empty.")

    limit = ENGINE_SPECS[engine]["prompt_limit"]
    if len(prompt) > limit:
        raise PromptTooLongError(
            f"Prompt is {len(prompt)} characters; engine '{engine}' allows a "
            f"maximum of {limit}. Shorten the prompt and try again."
        )

    spec = ASPECT_MAP[aspect]
    return GenerationPayload(
        prompt=prompt,
        engine=engine,
        aspect=aspect,
        width=spec["width"],
        height=spec["height"],
        pixel_volume=spec["pixel_volume"],
        target_use=spec["target"],
    )


def list_aspects() -> list[dict]:
    """UI helper: aspect choices with their exact resolutions."""
    return [
        {"aspect": k, **v} for k, v in ASPECT_MAP.items()
    ]


def list_engines() -> list[dict]:
    """UI helper: engine choices with limits and key requirements."""
    return [
        {"name": k, **v} for k, v in ENGINE_SPECS.items()
    ]
