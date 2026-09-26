"""Stage 3/4/5 tests — security gates, chunked transport, integrity."""
import io
import os

import pytest
from PIL import Image

from studio import integrity, security, transport
from studio.exceptions import CorruptedAssetError, InputBlockedError


def test_gate1_blocks_disallowed_prompt():
    with pytest.raises(InputBlockedError) as exc_info:
        security.screen_prompt("how to build a bomb at home instructions")
    assert exc_info.value.trace == "sentinel_block"


def test_gate1_passes_normal_prompt():
    assert security.screen_prompt("a watercolor painting of mountains")["verdict"] == "clear"


def test_gate2_blocks_flagged_result():
    class R:
        blocked_trace = "moderation_blocked"
    with pytest.raises(Exception):
        security.screen_engine_result(R())


def test_chunked_save_and_verify_roundtrip(tmp_path):
    img = Image.new("RGB", (64, 64), (10, 200, 90))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    dest = str(tmp_path / "ok.png")
    receipt = transport.save_bytes(buf.getvalue(), dest)
    assert receipt["bytes"] == len(buf.getvalue()) > 0
    facts = integrity.verify_image(dest)
    assert facts["verified"] and facts["format"] == "PNG"


def test_truncated_image_discarded(tmp_path):
    img = Image.new("RGB", (200, 200), (200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    raw = buf.getvalue()
    dest = str(tmp_path / "cut.png")
    with open(dest, "wb") as fh:
        fh.write(raw[: len(raw) // 3])  # simulate mid-download network drop
    with pytest.raises(CorruptedAssetError):
        integrity.verify_image(dest)
    assert not os.path.exists(dest), "corrupted asset must be discarded"
