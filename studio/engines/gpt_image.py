"""gpt-image series engine (OpenAI / Azure / Foundry).

Matrix row: DALL-E 3 retired March 2026 — enterprise systems must migrate to
gpt-image. Prompt limit 4,000 chars. Output: Base64 JSON (b64_json).

Aspect → provider size mapping (gpt-image-1 sizes):
    16:9 → 1536x1024 · 1:1 → 1024x1024 · 9:16 → 1024x1536
"""
from __future__ import annotations

import base64
import logging
import os

from .base import BaseEngine, EngineResult
from ..exceptions import InputBlockedError, OutputBlockedError, StudioError

log = logging.getLogger("studio.engines.gpt_image")

API_URL = "https://api.openai.com/v1/images/generations"
SIZE_MAP = {"16:9": "1536x1024", "1:1": "1024x1024", "9:16": "1024x1536"}


class GptImageEngine(BaseEngine):
    name = "gpt-image"

    def generate(self, payload, gateway) -> EngineResult:  # noqa: ANN001
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise StudioError("OPENAI_API_KEY is not set (see .env.example).")
        model = os.environ.get("GPT_IMAGE_MODEL", "gpt-image-1")

        body = {
            "model": model,
            "prompt": payload.prompt,
            "size": SIZE_MAP[payload.aspect],
            "response_format": "b64_json",
            "n": 1,
        }
        resp = gateway.resilient_post(
            API_URL, json=body,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        data = resp.json()

        # Provider-side moderation signals → Gate 2 equivalents.
        err = data.get("error") or {}
        if err.get("code") == "content_policy_violation":
            raise InputBlockedError(err.get("message", "Prompt rejected by provider."),
                                    trace="content_policy_violation")

        items = data.get("data") or []
        if not items:
            raise StudioError(f"Empty response from gpt-image API: {str(data)[:300]}")
        item = items[0]
        if item.get("finish_reason") == "FILTER":
            raise OutputBlockedError("Provider filtered the output image.",
                                     trace="finish_reason=FILTER")
        b64 = item.get("b64_json")
        if not b64:
            raise StudioError("gpt-image response contained no b64_json payload.")
        return EngineResult(
            image_bytes=base64.b64decode(b64),
            revised_prompt=item.get("revised_prompt"),
            raw_meta={"model": model, "size": body["size"]},
        )
