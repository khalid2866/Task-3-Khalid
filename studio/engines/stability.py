"""Stable Image Core engine (Stability AI — REST v2beta).

Matrix row: optimized for fast, high-quality REST v2beta iteration.
Prompt limit 10,000 chars. Output: RAW image bytes or Base64 JSON.

Docs: https://platform.stability.ai/docs/api-reference#tag/Generate
"""
from __future__ import annotations

import logging
import os

from .base import BaseEngine, EngineResult
from ..exceptions import InputBlockedError, OutputBlockedError, StudioError

log = logging.getLogger("studio.engines.stability")

API_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"


class StabilityEngine(BaseEngine):
    name = "stability"

    def generate(self, payload, gateway) -> EngineResult:  # noqa: ANN001
        api_key = os.environ.get("STABILITY_API_KEY", "")
        if not api_key:
            raise StudioError("STABILITY_API_KEY is not set (see .env.example).")

        # v2beta accepts aspect_ratio directly; we keep the studio's strict map
        # as the source of truth and pass the ratio through.
        resp = gateway.resilient_post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "image/*",
            },
            data={
                "prompt": payload.prompt,
                "aspect_ratio": payload.aspect,
                "output_format": "png",
            },
        )
        finish = resp.headers.get("finish-reason", "")
        if finish == "FILTER":
            raise OutputBlockedError("Stability filtered the output image.",
                                     trace="finish_reason=FILTER")
        if finish == "CONTENT_FILTERED":
            raise InputBlockedError("Stability rejected the prompt.",
                                    trace="content_policy_violation")
        ctype = resp.headers.get("Content-Type", "")
        if "image/" not in ctype:
            raise StudioError(f"Unexpected Stability response: {resp.text[:300]}")
        return EngineResult(
            image_bytes=resp.content,
            raw_meta={"finish_reason": finish or "SUCCESS",
                      "seed": resp.headers.get("seed", "")},
        )
