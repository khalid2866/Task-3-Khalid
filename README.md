# ◈ Image Generation Studio — Project 3

**Multimodal Image Generation Studio** · Generative AI · Project 3 Industrial Training Kit · DecodeLabs

A production-style text-to-image pipeline implementing the complete Project 3 blueprint:

| # | Blueprint stage | Implementation |
|---|---|---|
| 1 | Prompt Payload Formulation | `studio/payload.py` — aspect ratio → exact pixel payloads; per-engine char limits |
| 2 | Network API Gateway | `studio/gateway.py` — split timeout `(3.05s, 60s)`; ConnectTimeout fails fast; ReadTimeout/429/503 retry with exponential backoff + jitter |
| 3 | Security & Moderation Gates | `studio/security.py` — Gate 1 input filter (instant, 0 compute); Gate 2 output filter (blurred placeholder) |
| 4 | Transport Protocol | `studio/transport.py` — memory-safe 64 KiB chunked streaming straight to disk |
| 5 | Integrity Verification | `studio/integrity.py` — forced `Image.open().load()` pixel decode; truncated assets discarded + retried |
| 6 | Automated QA | `studio/qa.py` — Lens 1 aesthetic score (> 7.0/10 or discard); Lens 2 semantic alignment flags divergent assets |

### Engine matrix (from the blueprint)

| Engine | Prompt limit | Output | Needs |
|---|---|---|---|
| `demo` | 10,000 | local PNG (offline, no key) | nothing |
| `gpt-image` | 4,000 | Base64 JSON (`b64_json`) | `OPENAI_API_KEY` |
| `stability` | 10,000 | RAW bytes (REST v2beta) | `STABILITY_API_KEY` |
| `wan` | 1,000 | public URL → streamed PNG | `DASHSCOPE_API_KEY` |

> DALL-E 3 was retired March 2026 — the OpenAI adapter targets the `gpt-image` series.

### Aspect-ratio → pixel payload map (strict)

| Aspect | Resolution | Pixel volume | Target use |
|---|---|---|---|
| `16:9` | 1344 × 768 | 1,032,192 | Web banners, presentations |
| `1:1` | 1024 × 1024 | 1,048,576 | Avatars, product grids |
| `9:16` | 768 × 1344 | 1,032,192 | Mobile reels, wallpapers |

Unsupported dimensions are **refused before transmission** (blueprint rule: arbitrary sizes cause an immediate API handshake failure).

---

## Requirements

- **Python 3.10+** ([download](https://www.python.org/downloads/))
- Internet only needed for real API engines; the `demo` engine works fully offline.

## Setup

**Windows (PowerShell):**
```powershell
cd image-generation-studio
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then add your API keys if you have them
```

**macOS / Linux (terminal):**
```bash
cd image-generation-studio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your API keys if you have them
```

Or just double-click/run `run.bat` (Windows) / `run.sh` (macOS/Linux) — they create the venv, install deps, and launch the web UI.

## Run it

### Option A — Web studio (recommended)
```bash
python -m web.app
```
Open **http://127.0.0.1:5000** — enter a prompt, pick an engine and aspect ratio, hit **Generate**, and watch each of the 6 pipeline stages report in. Finished images appear in the gallery and in `outputs/`.

### Option B — Command line
```bash
# Offline demo (no API key needed) — exercises the entire pipeline
python -m studio generate "a neon cityscape at night, cinematic lighting" --engine demo --aspect 16:9

# Real engines (needs keys in .env)
python -m studio generate "product photo of a ceramic mug" --engine stability --aspect 1:1
python -m studio generate "portrait of an astronaut" --engine gpt-image --aspect 9:16
python -m studio generate "ink wash mountain landscape" --engine wan --aspect 16:9

# Inspect the blueprint maps
python -m studio list-engines
python -m studio list-aspects
```

### Run the tests
```bash
pytest -v
```

## How it works (pipeline walkthrough)

1. **Payload** — your prompt + aspect choice is validated and mapped to exact `width/height/pixel_volume`; engine char limits enforced.
2. **Gateway** — the engine's API call goes through `timeout=(3.05, 60)`. A `ConnectTimeout` fails fast with a clear diagnosis; `ReadTimeout`/429/503 back off exponentially with jitter and retry (max 5 attempts).
3. **Security** — Gate 1 screens the prompt *before* any compute (blocked → instant rejection, polite message, zero cost). Gate 2 screens the provider's response (blocked → blurred placeholder + polite warning, never a crash).
4. **Transport** — image bytes/URLs are streamed to `outputs/` in 64 KiB chunks; RAM never holds more than one chunk.
5. **Integrity** — `Image.open(path).load()` forces a full pixel decode. A truncated download raises `OSError: broken data stream`, the file is discarded, and the pipeline regenerates once automatically.
6. **QA** — Lens 1 scores aesthetics 0–10 (sharpness, colorfulness, contrast, exposure); below 7.0 the asset is auto-discarded to `outputs/quarantine/`. Lens 2 scores prompt↔image semantic alignment and flags divergent assets for regeneration.

Every run appends a record (prompt, engine, resolution, SHA-256, QA scores, full stage log) to `outputs/manifest.json`.

## Production notes

- **Lens 1**: `AestheticScorer` is a local heuristic. Subclass it and override `score()` to plug in **OpenAI CLIP ViT-L/14 + linear classifier** per the blueprint.
- **Lens 2**: `SemanticAligner` verifies prompt-keyword coverage + visual sanity. Override `score()` to plug in **PickScore / CLIP-IQA** for true vision-language scoring.
- **Wan**: uses DashScope's async task API; if Alibaba changes the endpoint, update `SUBMIT_URL`/`TASK_URL` in `studio/engines/wan.py`.
- **Enterprise export**: generated PNGs in `outputs/` are ready to feed into Unreal Engine 5 (Nanite), Blender (Python `bpy`), or Polycam pipelines per the blueprint's scaling page.

## Project structure

```
image-generation-studio/
├── studio/                 # the 6-stage pipeline
│   ├── payload.py          # stage 1 — aspect maps, engine constraints
│   ├── gateway.py          # stage 2 — split timeouts, backoff+jitter
│   ├── security.py         # stage 3 — dual safety gates
│   ├── transport.py        # stage 4 — chunked binary streaming
│   ├── integrity.py        # stage 5 — forced pixel decode
│   ├── qa.py               # stage 6 — aesthetic + semantic QA
│   ├── pipeline.py         # orchestrator + manifest
│   ├── exceptions.py       # typed pipeline errors
│   ├── __main__.py         # CLI
│   └── engines/            # demo / gpt-image / stability / wan
├── web/                    # Flask studio UI
│   ├── app.py
│   └── templates/ static/
├── tests/                  # pytest suite (17 tests)
├── outputs/                # generated assets + manifest.json
├── requirements.txt
├── .env.example
├── run.sh / run.bat
└── README.md
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `OPENAI_API_KEY is not set` | Use `--engine demo` (no key), or add the key to `.env` |
| `UnsupportedDimensionsError` | Use `16:9`, `1:1`, or `9:16` only — see `python -m studio list-aspects` |
| `PromptTooLongError` | Shorten the prompt to the engine's limit (`list-engines` shows limits) |
| `NetworkFailure` (connect) | Check internet/firewall — the gateway fails fast by design |
| `InferenceFailure` (read) | GPU cluster slow — the pipeline already retried 5× with backoff |
| `qa_rejected` | Aesthetic score ≤ 7.0 — asset moved to `outputs/quarantine/`; try a more descriptive prompt |
| Port 5000 busy | Edit `web/app.py` port or stop the other app |
