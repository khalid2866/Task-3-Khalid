"""Stage 6 — Automated Quality Assurance.

Two lenses, exactly as specified in the blueprint:

Lens 1 — Aesthetic Classification
    Process:   image → vector-style aesthetic features → score / 10.
    Threshold: score must be > 7.0 / 10.0.
    Action:    assets scoring below threshold are automatically discarded.

    Production swap-in: OpenAI CLIP ViT-L/14 embedding + linear classifier
    (see ``AestheticScorer`` — subclass it to plug the real model in).

Lens 2 — Semantic Alignment Verification
    Process:   image + original text prompt → alignment score.
    Function:  measures how accurately the visual output aligns with the
               requested prompt.
    Action:    flags hallucinated / divergent assets for regeneration.

    Production swap-in: PickScore or CLIP-IQA (see ``SemanticAligner``).
"""
from __future__ import annotations

import logging
import math
import os
import re

from PIL import Image, ImageFilter, ImageStat

from .exceptions import QARejectedError

log = logging.getLogger("studio.qa")

AESTHETIC_THRESHOLD = float(os.environ.get("STUDIO_QA_THRESHOLD", "7.0"))
SEMANTIC_FLAG_THRESHOLD = 0.35

_STOPWORDS = frozenset(
    "a an the and or of in on at to for with from by is are was were be as "
    "it its this that these those i you we they he she them his her our your "
    "my me do does did will would can could should very just so not no "
    "make me a".split()
)


# ── Lens 1 ────────────────────────────────────────────────────────────────────
class AestheticScorer:
    """Local heuristic aesthetic scorer (0–10), standing in for CLIP ViT-L/14.

    Combines four photographic-quality signals; each is normalized to 0–10
    and weighted. Subclass and override ``score()`` to use the real
    CLIP ViT-L/14 embedding + linear classifier.
    """

    def _sharpness(self, gray: Image.Image) -> float:
        lap = gray.filter(ImageFilter.Kernel(
            (3, 3), (0, -1, 0, -1, 4, -1, 0, -1, 0), scale=1))
        st = ImageStat.Stat(lap)
        var = st.var[0]
        return min(10.0, (math.log1p(var) / math.log1p(4000.0)) * 10.0)

    def _colorfulness(self, img: Image.Image) -> float:
        # Hasler & Süsstrunk (2003) colorfulness metric, scaled to 0–10.
        r, g, b = img.split()[:3]
        rs, gs, bs = ImageStat.Stat(r), ImageStat.Stat(g), ImageStat.Stat(b)
        rg = abs(rs.mean[0] - gs.mean[0])
        yb = abs(0.5 * (rs.mean[0] + gs.mean[0]) - bs.mean[0])
        std_rg = math.sqrt(rs.var[0] + gs.var[0])
        std_yb = math.sqrt(0.25 * (rs.var[0] + gs.var[0]) + bs.var[0])
        metric = math.sqrt(rg ** 2 + yb ** 2) + 0.3 * math.sqrt(std_rg ** 2 + std_yb ** 2)
        return min(10.0, metric / 12.0)

    def _contrast(self, gray: Image.Image) -> float:
        st = ImageStat.Stat(gray)
        return min(10.0, math.sqrt(st.var[0]) / 6.4)

    def _exposure_balance(self, gray: Image.Image) -> float:
        mean = ImageStat.Stat(gray).mean[0] / 255.0
        # Ideal mid-tone exposure; penalize crushed blacks / blown whites.
        return max(0.0, 10.0 * (1.0 - abs(mean - 0.5) * 2.2))

    def score(self, path: str) -> dict:
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            small = rgb.resize((256, 256))
            gray = small.convert("L")
            parts = {
                "sharpness": self._sharpness(gray),
                "colorfulness": self._colorfulness(small),
                "contrast": self._contrast(gray),
                "exposure": self._exposure_balance(gray),
            }
        total = (parts["sharpness"] * 0.30 + parts["colorfulness"] * 0.30
                 + parts["contrast"] * 0.25 + parts["exposure"] * 0.15)
        total = round(min(10.0, max(0.0, total)), 2)
        return {"score": total, "parts": {k: round(v, 2) for k, v in parts.items()}}


# ── Lens 2 ────────────────────────────────────────────────────────────────────
class SemanticAligner:
    """Prompt↔image alignment check (0–1), standing in for PickScore/CLIP-IQA.

    Measures keyword coverage: content words from the prompt that the
    engine attests are visually present (engines record detected keywords in
    result metadata), plus a visual-sanity term (non-blank, real edge
    content). Subclass and override ``score()`` to plug in PickScore or
    CLIP-IQA for true vision-language scoring.
    """

    def _prompt_keywords(self, prompt: str) -> set[str]:
        words = re.findall(r"[a-z0-9]+", prompt.lower())
        return {w for w in words if len(w) > 2 and w not in _STOPWORDS}

    def _visual_sanity(self, path: str) -> float:
        with Image.open(path) as img:
            gray = img.convert("L").resize((128, 128))
            st = ImageStat.Stat(gray)
            edge = gray.filter(ImageFilter.FIND_EDGES)
            edge_energy = ImageStat.Stat(edge).mean[0] / 255.0
            non_blank = min(1.0, math.sqrt(st.var[0]) / 40.0)
            return round(min(1.0, 0.5 * non_blank + 0.5 * min(1.0, edge_energy * 8)), 3)

    def score(self, path: str, prompt: str, engine_keywords: set[str] | None = None) -> dict:
        wanted = self._prompt_keywords(prompt)
        engine_keywords = engine_keywords or set()
        coverage = (len(wanted & engine_keywords) / len(wanted)) if wanted else 1.0
        sanity = self._visual_sanity(path)
        # Keyword coverage dominates when the engine reports it; otherwise
        # the visual-sanity term keeps the check honest but lenient.
        if engine_keywords:
            total = round(0.7 * coverage + 0.3 * sanity, 3)
        else:
            total = round(0.5 * coverage + 0.5 * sanity, 3)
        return {
            "score": total,
            "keyword_coverage": round(coverage, 3),
            "visual_sanity": sanity,
            "flagged_for_regeneration": total < SEMANTIC_FLAG_THRESHOLD,
        }


def run_qa(path: str, prompt: str, engine_keywords: set[str] | None = None,
           threshold: float = AESTHETIC_THRESHOLD) -> dict:
    """Run both QA lenses. Raises QARejectedError if Lens 1 fails."""
    lens1 = AestheticScorer().score(path)
    log.info("qa lens1 (aesthetic): %.2f/10 (threshold %.1f)", lens1["score"], threshold)
    if lens1["score"] <= threshold:
        raise QARejectedError(
            f"Asset scored {lens1['score']}/10 on aesthetic QA (threshold "
            f">{threshold}) and was automatically discarded.",
            lens="aesthetic", score=lens1["score"],
        )
    lens2 = SemanticAligner().score(path, prompt, engine_keywords)
    log.info("qa lens2 (semantic): %.3f (flagged=%s)",
             lens2["score"], lens2["flagged_for_regeneration"])
    return {
        "aesthetic": lens1,
        "semantic": lens2,
        "threshold": threshold,
        "verdict": "pass",
    }
