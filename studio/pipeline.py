"""Pipeline orchestrator — runs the 6 blueprint stages in order.

    1. Prompt Payload Formulation  (payload.build_generation_payload)
    2. Network API Gateway         (gateway timeouts/backoff live inside engines)
    3. Security & Moderation Gates (security.screen_prompt / screen_engine_result)
    4. Transport Protocol          (transport.save_bytes / download_stream)
    5. Integrity Verification      (integrity.verify_image — forced .load())
    6. Automated Quality Assurance (qa.run_qa — both lenses)

Every run produces a stage log and a manifest record in the output dir.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import uuid

from . import gateway, integrity, payload, qa, security, transport
from .engines.base import BaseEngine, EngineResult
from .engines.demo import DemoEngine
from .engines.gpt_image import GptImageEngine
from .engines.stability import StabilityEngine
from .engines.wan import WanEngine
from .exceptions import (
    CorruptedAssetError,
    InputBlockedError,
    OutputBlockedError,
    QARejectedError,
    StudioError,
)

log = logging.getLogger("studio.pipeline")

ENGINES: dict[str, BaseEngine] = {
    "demo": DemoEngine(),
    "gpt-image": GptImageEngine(),
    "stability": StabilityEngine(),
    "wan": WanEngine(),
}

MANIFEST_NAME = "manifest.json"


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _load_manifest(output_dir: str) -> list[dict]:
    path = os.path.join(output_dir, MANIFEST_NAME)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError:
                return []
    return []


def _save_manifest(output_dir: str, records: list[dict]) -> None:
    path = os.path.join(output_dir, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)


class StageLog:
    """Timestamped record of each pipeline stage's outcome."""

    def __init__(self) -> None:
        self.stages: list[dict] = []

    def add(self, stage: str, status: str, detail: str = "") -> None:
        self.stages.append({
            "stage": stage, "status": status, "detail": detail,
            "at": _utcnow(),
        })

    def as_list(self) -> list[dict]:
        return self.stages


def run_generation(prompt: str, engine_name: str = "demo", aspect: str = "1:1",
                   output_dir: str = "outputs") -> dict:
    """Execute the full 6-stage pipeline. Returns the manifest record."""
    os.makedirs(output_dir, exist_ok=True)
    job_id = uuid.uuid4().hex[:8]
    slog = StageLog()
    record: dict = {
        "job_id": job_id, "prompt": prompt, "engine": engine_name,
        "aspect": aspect, "status": "started", "started_at": _utcnow(),
        "stages": slog.as_list(),
    }

    def fail(status: str, message: str) -> dict:
        record.update({"status": status, "error": message,
                       "finished_at": _utcnow()})
        _persist(record, output_dir)
        return record

    try:
        # ── Stage 1: Prompt Payload Formulation ──────────────────────────
        try:
            gen_payload = payload.build_generation_payload(prompt, engine_name, aspect)
        except StudioError as exc:
            slog.add("1 · Prompt Payload Formulation", "rejected", str(exc))
            return fail("rejected", str(exc))
        slog.add("1 · Prompt Payload Formulation", "ok",
                 f"{gen_payload.width}x{gen_payload.height} "
                 f"({gen_payload.pixel_volume:,} px) · target: {gen_payload.target_use}")
        record.update({"width": gen_payload.width, "height": gen_payload.height,
                       "pixel_volume": gen_payload.pixel_volume})

        # ── Stage 3a: Gate 1 — pre-generation input filtering ────────────
        try:
            clearance = security.screen_prompt(gen_payload.prompt)
        except InputBlockedError as exc:
            slog.add("3 · Security Gate 1 (input)", "blocked",
                     f"trace={exc.trace}; 0 compute cost")
            record["polite_message"] = security.POLITE_MESSAGES["sentinel_block"]
            return fail("blocked_input", str(exc))
        slog.add("3 · Security Gate 1 (input)", "ok", "prompt clear")

        # ── Stage 2: Network API Gateway (inside engine call) ────────────
        engine = ENGINES[gen_payload.engine]
        try:
            result: EngineResult = engine.generate(gen_payload, gateway)
        except InputBlockedError as exc:  # provider-side prompt rejection
            slog.add("3 · Security Gate 1 (input)", "blocked",
                     f"provider trace={exc.trace}; 0 compute cost")
            record["polite_message"] = str(exc)
            return fail("blocked_input", str(exc))
        except OutputBlockedError as exc:  # provider filtered the output
            return _handle_output_blocked(exc, gen_payload, slog, record, output_dir)
        slog.add("2 · Network API Gateway", "ok",
                 f"engine={engine.name} · timeout=(3.05s, 60s) · backoff+jitter armed")

        # ── Stage 3b: Gate 2 — post-generation output filtering ──────────
        try:
            security.screen_engine_result(result)
        except OutputBlockedError as exc:
            return _handle_output_blocked(exc, gen_payload, slog, record, output_dir)
        slog.add("3 · Security Gate 2 (output)", "ok", "output clear")

        # ── Stage 4: Transport Protocol ──────────────────────────────────
        filename = f"{job_id}.png"
        dest = os.path.join(output_dir, filename)
        if result.image_url:
            receipt = transport.download_stream(result.image_url, dest)
            slog.add("4 · Transport Protocol", "ok",
                     f"chunked stream ({receipt['chunk_size'] // 1024} KiB chunks) · "
                     f"{receipt['bytes']:,} bytes · sha256 {receipt['sha256'][:12]}…")
        elif result.image_bytes:
            receipt = transport.save_bytes(result.image_bytes, dest)
            slog.add("4 · Transport Protocol", "ok",
                     f"chunked write ({receipt['chunk_size'] // 1024} KiB slices) · "
                     f"{receipt['bytes']:,} bytes · sha256 {receipt['sha256'][:12]}…")
        else:
            slog.add("4 · Transport Protocol", "failed", "engine returned no image")
            return fail("failed", "Engine returned no image bytes or URL.")
        record.update({"file": filename, "bytes": receipt["bytes"],
                       "sha256": receipt["sha256"]})

        # ── Stage 5: Integrity Verification (+ auto-retry on corruption) ──
        try:
            facts = integrity.verify_image(dest)
        except CorruptedAssetError as exc:
            slog.add("5 · Integrity Verification", "corrupted",
                     f"{exc} — requesting one regeneration retry")
            # One automatic regeneration retry, then give up gracefully.
            try:
                retry_result = engine.generate(gen_payload, gateway)
                if retry_result.image_url:
                    transport.download_stream(retry_result.image_url, dest)
                else:
                    transport.save_bytes(retry_result.image_bytes or b"", dest)
                facts = integrity.verify_image(dest)
                slog.add("5 · Integrity Verification", "ok", "retry produced a valid asset")
            except StudioError as exc2:
                slog.add("5 · Integrity Verification", "failed", str(exc2))
                return fail("failed", f"Asset corrupted and retry failed: {exc2}")
        else:
            slog.add("5 · Integrity Verification", "ok",
                     f"forced pixel decode passed · {facts['format']} "
                     f"{facts['width']}x{facts['height']} {facts['mode']}")

        # ── Stage 6: Automated Quality Assurance ─────────────────────────
        try:
            qa_report = qa.run_qa(dest, gen_payload.prompt, result.keywords)
        except QARejectedError as exc:
            slog.add("6 · Automated QA (Lens 1 aesthetic)", "rejected",
                     f"score {exc.score}/10 ≤ threshold — asset discarded")
            quarantine = os.path.join(output_dir, "quarantine")
            os.makedirs(quarantine, exist_ok=True)
            os.replace(dest, os.path.join(quarantine, filename))
            record.update({"file": f"quarantine/{filename}",
                           "qa": {"aesthetic_score": exc.score, "verdict": "rejected"}})
            return fail("qa_rejected", str(exc))
        slog.add("6 · Automated QA (Lens 1 aesthetic)", "ok",
                 f"score {qa_report['aesthetic']['score']}/10 > "
                 f"{qa_report['threshold']}")
        slog.add("6 · Automated QA (Lens 2 semantic)", "ok",
                 f"alignment {qa_report['semantic']['score']} · "
                 f"flagged_for_regeneration={qa_report['semantic']['flagged_for_regeneration']}")
        record["qa"] = qa_report
        if result.revised_prompt:
            record["revised_prompt"] = result.revised_prompt

        record.update({"status": "complete", "finished_at": _utcnow()})
        _persist(record, output_dir)
        log.info("pipeline: job %s complete → %s", job_id, dest)
        return record

    except (StudioError, OSError) as exc:  # graceful catch-all, no crashes
        slog.add("pipeline", "failed", f"{type(exc).__name__}: {exc}")
        return fail("failed", f"{type(exc).__name__}: {exc}")


def _handle_output_blocked(exc: OutputBlockedError, gen_payload, slog,
                           record: dict, output_dir: str) -> dict:
    slog.add("3 · Security Gate 2 (output)", "blocked",
             f"trace={exc.trace}; compute cost incurred — blurred placeholder issued")
    placeholder = os.path.join(output_dir, f"{record['job_id']}_blocked.png")
    security.blurred_placeholder(gen_payload.width, gen_payload.height, placeholder)
    record.update({"file": os.path.basename(placeholder),
                   "polite_message": security.POLITE_MESSAGES["moderation_blocked"]})
    record.update({"status": "blocked_output", "error": str(exc),
                   "finished_at": _utcnow()})
    _persist(record, output_dir)
    return record


def _persist(record: dict, output_dir: str) -> None:
    records = _load_manifest(output_dir)
    records = [r for r in records if r.get("job_id") != record["job_id"]]
    records.insert(0, record)
    _save_manifest(output_dir, records)


def list_records(output_dir: str = "outputs") -> list[dict]:
    return _load_manifest(output_dir)
