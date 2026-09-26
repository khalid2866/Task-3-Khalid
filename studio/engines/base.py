"""Engine adapters — one per row of the Multimodal Engine Matrix.

Each engine exposes the same interface so the 6-stage pipeline is
engine-agnostic:

    result = engine.generate(payload, gateway) -> EngineResult
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EngineResult:
    """Normalized output of any generation engine."""

    image_bytes: bytes | None = None   # RAW / decoded b64 payload
    image_url: str | None = None       # for URL-returning engines (Wan)
    revised_prompt: str | None = None  # e.g. OpenAI's rewritten prompt
    blocked_trace: str | None = None   # moderation_blocked / FILTER / …
    keywords: set[str] = field(default_factory=set)  # prompt concepts rendered
    raw_meta: dict = field(default_factory=dict)


class BaseEngine:
    name: str = "base"

    def generate(self, payload, gateway) -> EngineResult:  # noqa: ANN001, ANN202
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Engine {self.name}>"
