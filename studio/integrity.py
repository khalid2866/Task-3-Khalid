"""Stage 5 — Integrity Verification (forced pixel-level decode).

The trap: standard metadata checks (``imghdr.what()``) and
``Image.verify()`` only read block structure / CRC headers at the start of
the file, so they report success even when the connection dropped
mid-download — a silent, truncated disaster.

The fix: ``Image.open(path).load()`` inside ``try/except``. ``.load()``
forces Pillow to fully decode the entire image stream, pixel by pixel. A
truncated file raises ``OSError: broken data stream``; the pipeline then
discards the corrupted asset and automatically requests a retry.
"""
from __future__ import annotations

import logging
import os

from PIL import Image

from .exceptions import CorruptedAssetError

log = logging.getLogger("studio.integrity")


def verify_image(path: str) -> dict:
    """Force a full pixel decode; raise CorruptedAssetError if truncated.

    Returns image facts (format, size, mode) on success.
    """
    try:
        with Image.open(path) as img:
            img.load()  # ← the rigorous pixel-level decode
            facts = {
                "format": img.format,
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
            }
    except OSError as exc:
        # Discard the corrupted asset so it can never ship downstream.
        try:
            os.remove(path)
        except OSError:
            pass
        log.warning("integrity: discarded truncated asset %s (%s)", path, exc)
        raise CorruptedAssetError(
            f"Downloaded file failed pixel-level integrity verification "
            f"({exc}); the corrupted asset was discarded."
        ) from exc
    log.info("integrity: verified %s (%dx%d %s)", path,
             facts["width"], facts["height"], facts["format"])
    return {"path": path, "verified": True, **facts}
