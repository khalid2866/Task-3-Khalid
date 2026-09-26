"""Web UI for the Image Generation Studio.

Run:  python -m web.app        (then open http://127.0.0.1:5000)
"""
from __future__ import annotations

import os
import sys
import threading
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import studio  # noqa: F401  (loads .env)
from studio import payload, pipeline

from flask import Flask, jsonify, render_template, request, send_from_directory

OUTPUT_DIR = os.environ.get("STUDIO_OUTPUT_DIR", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__)
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _run_job(job_id: str, prompt: str, engine: str, aspect: str) -> None:
    try:
        record = pipeline.run_generation(prompt, engine, aspect, OUTPUT_DIR)
        outcome = {"done": True, "record": record}
    except Exception as exc:  # never leave the UI hanging
        outcome = {"done": True, "error": f"{type(exc).__name__}: {exc}"}
    with _lock:
        _jobs[job_id] = outcome


@app.get("/")
def index():
    return render_template(
        "index.html",
        engines=payload.list_engines(),
        aspects=payload.list_aspects(),
    )


@app.post("/api/generate")
def api_generate():
    data = request.get_json(force=True) or {}
    prompt = (data.get("prompt") or "").strip()
    engine = (data.get("engine") or "demo").strip().lower()
    aspect = (data.get("aspect") or "1:1").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400
    if engine not in pipeline.ENGINES:
        return jsonify({"error": f"Unknown engine '{engine}'."}), 400
    job_id = uuid.uuid4().hex[:8]
    with _lock:
        _jobs[job_id] = {"done": False}
    threading.Thread(target=_run_job, args=(job_id, prompt, engine, aspect),
                     daemon=True).start()
    return jsonify({"job_id": job_id})


@app.get("/api/jobs/<job_id>")
def api_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown job."}), 404
    return jsonify(job)


@app.get("/api/assets")
def api_assets():
    return jsonify(pipeline.list_records(OUTPUT_DIR))


@app.get("/outputs/<path:filename>")
def serve_output(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
