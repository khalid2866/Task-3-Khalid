"""Wan Text-to-Image v2 engine (Alibaba Cloud Model Studio / DashScope).

Matrix row: artistic and photorealistic standard resolution.
Prompt limit 1,000 chars. Output: public image URL or PNG binary.

Uses DashScope's async task API: submit → poll task status → fetch the
result image URL → stream it via Stage 4. Set DASHSCOPE_API_KEY; override
the model with WAN_MODEL if needed.

Docs: https://www.alibabacloud.com/help/en/model-studio/text-to-image
"""
from __future__ import annotations

import logging
import os
import time

from .base import BaseEngine, EngineResult
from ..exceptions import StudioError

log = logging.getLogger("studio.engines.wan")

SUBMIT_URL = ("https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/"
              "text2image/image-synthesis")
TASK_URL = "https://dashscope-intl.aliyuncs.com/api/v1/tasks/{task_id}"
SIZE_MAP = {"16:9": "1344*768", "1:1": "1024*1024", "9:16": "768*1344"}


class WanEngine(BaseEngine):
    name = "wan"

    def generate(self, payload, gateway) -> EngineResult:  # noqa: ANN001
        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            raise StudioError("DASHSCOPE_API_KEY is not set (see .env.example).")
        model = os.environ.get("WAN_MODEL", "wan2.1-t2i-plus")
        headers = {"Authorization": f"Bearer {api_key}",
                   "X-DashScope-Async": "enable"}

        submit = gateway.resilient_post(SUBMIT_URL, json={
            "model": model,
            "input": {"prompt": payload.prompt},
            "parameters": {"size": SIZE_MAP[payload.aspect], "n": 1},
        }, headers=headers).json()
        task_id = (submit.get("output") or {}).get("task_id")
        if not task_id:
            raise StudioError(f"Wan task submission failed: {str(submit)[:300]}")

        # Poll the async task (gateway read timeout covers each poll).
        for _ in range(40):
            task = gateway.resilient_post(
                TASK_URL.format(task_id=task_id), headers=headers).json()
            status = (task.get("output") or {}).get("task_status")
            if status == "SUCCEEDED":
                results = (task.get("output") or {}).get("results") or []
                url = (results[0] or {}).get("url") if results else None
                if not url:
                    raise StudioError(f"Wan task succeeded with no URL: {str(task)[:300]}")
                return EngineResult(image_url=url,
                                    raw_meta={"model": model, "task_id": task_id})
            if status == "FAILED":
                raise StudioError(f"Wan task failed: {str(task)[:300]}")
            time.sleep(5)

        raise StudioError("Wan task timed out waiting for completion.")
