"""Stage 1 tests — strict payload formulation."""
import pytest

from studio import payload
from studio.exceptions import PromptTooLongError, UnsupportedDimensionsError


def test_aspect_map_exact_pixels():
    assert payload.ASPECT_MAP["16:9"]["width"] == 1344
    assert payload.ASPECT_MAP["16:9"]["height"] == 768
    assert payload.ASPECT_MAP["16:9"]["pixel_volume"] == 1_032_192
    assert payload.ASPECT_MAP["1:1"]["pixel_volume"] == 1_048_576
    assert payload.ASPECT_MAP["9:16"]["width"] == 768
    assert payload.ASPECT_MAP["9:16"]["height"] == 1344


def test_supported_aspect_builds_payload():
    p = payload.build_generation_payload("a cat", "demo", "16:9")
    assert (p.width, p.height) == (1344, 768)
    assert p.pixel_volume == 1344 * 768


def test_unsupported_dimensions_refused():
    with pytest.raises(UnsupportedDimensionsError):
        payload.build_generation_payload("a cat", "demo", "4:3")


def test_engine_prompt_limits_enforced():
    long_prompt = "x" * 1001
    with pytest.raises(PromptTooLongError):
        payload.build_generation_payload(long_prompt, "wan", "1:1")
    # same prompt is fine for stability (10k limit)
    p = payload.build_generation_payload(long_prompt, "stability", "1:1")
    assert len(p.prompt) == 1001


def test_empty_prompt_rejected():
    with pytest.raises(ValueError):
        payload.build_generation_payload("   ", "demo", "1:1")


def test_unknown_engine_rejected():
    with pytest.raises(ValueError):
        payload.build_generation_payload("a cat", "midjourney", "1:1")
