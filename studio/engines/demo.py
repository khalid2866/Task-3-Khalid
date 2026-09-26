"""Demo engine — offline local renderer (no API key required).

Renders the prompt as a seeded, high-colorfulness composition at the exact
mapped resolution, so every downstream stage (gateway policy, security
gates, chunked transport, pixel-level integrity, both QA lenses) can be
exercised end-to-end without network access or API keys.

The rendered keywords are recorded in result metadata so Lens 2
(semantic alignment) has a real signal to verify.
"""
from __future__ import annotations

import hashlib
import io
import random
import re

from PIL import Image, ImageDraw, ImageFont

from .base import BaseEngine, EngineResult

_STOPWORDS = frozenset(
    "a an the and or of in on at to for with from by is are was were be as "
    "it its this that these those i you we they he she them his her our your "
    "my me do does did will would can could should very just so not no".split()
)


def _keywords(prompt: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", prompt.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


class DemoEngine(BaseEngine):
    name = "demo"

    def generate(self, payload, gateway) -> EngineResult:  # noqa: ANN001
        seed = int(hashlib.sha256(payload.prompt.encode()).hexdigest(), 16) % (2 ** 32)
        rng = random.Random(seed)
        w, h = payload.width, payload.height

        # Vivid two-tone gradient backdrop (bright, saturated → strong QA signals).
        vivid = [(235, 90, 40), (40, 140, 235), (150, 60, 220), (30, 200, 150),
                 (240, 200, 60), (220, 60, 130)]
        top = rng.choice(vivid)
        bottom = rng.choice([c for c in vivid if c != top])
        img = Image.new("RGB", (w, h), top)
        draw = ImageDraw.Draw(img)
        for y in range(h):
            t = y / max(h - 1, 1)
            draw.line([(0, y), (w, y)],
                      fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))

        # Bright starfield dots for sparkle / texture.
        for _ in range(140):
            x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
            r = rng.randint(1, 3)
            bright = rng.randint(200, 255)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(bright, bright, bright))

        # Bold outlined shapes for edge energy and contrast.
        for _ in range(45):
            x0, y0 = rng.randint(0, w), rng.randint(0, h)
            x1, y1 = x0 + rng.randint(30, w // 3), y0 + rng.randint(30, h // 3)
            color = rng.choice([
                (255, 255, 255), (15, 15, 25),
                (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)),
            ])
            if rng.random() < 0.5:
                draw.ellipse([x0, y0, x1, y1], outline=color, width=5)
            else:
                draw.rectangle([x0, y0, x1, y1], outline=color, width=4)

        # Slim caption bar (kept small so it doesn't crush exposure).
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", max(18, w // 40))
            small = ImageFont.truetype("DejaVuSans.ttf", max(12, w // 70))
        except OSError:
            font = ImageFont.load_default()
            small = font
        bar_h = h // 8
        draw.rectangle([0, h - bar_h, w, h], fill=(10, 12, 20))
        caption = payload.prompt[:90]
        draw.text((24, h - bar_h + 12), caption, fill=(235, 240, 250), font=font)
        draw.text((24, h - 30), f"demo engine · {w}x{h} · {payload.aspect}",
                  fill=(140, 160, 190), font=small)

        buf = io.BytesIO()
        img.save(buf, "PNG")
        return EngineResult(
            image_bytes=buf.getvalue(),
            keywords=_keywords(payload.prompt),
            raw_meta={"engine": "demo", "seed": seed},
        )
