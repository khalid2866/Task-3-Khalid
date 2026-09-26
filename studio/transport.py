"""Stage 4 — Transport Protocol (memory-safe binary streaming).

The blueprint's anti-pattern: loading a high-res image entirely into RAM
with a basic ``requests.get()``. The solution:

    Rule 1: Never load a high-res image fully into RAM at once.
    Rule 2: Enable chunking — ``stream=True`` in the request.
    Rule 3: Write sequentially with ``iter_content(chunk_size=65536)`` to
            pipe data safely, directly to the local binary file system.
"""
from __future__ import annotations

import hashlib
import logging
import os

from . import gateway

log = logging.getLogger("studio.transport")

CHUNK_SIZE = 65536  # 64 KiB — the blueprint's specified chunk size


def download_stream(url: str, dest_path: str,
                    chunk_size: int = CHUNK_SIZE) -> dict:
    """Stream a remote binary payload to disk in fixed-size chunks.

    Returns a receipt with byte count and SHA-256 digest. Nothing larger
    than one chunk is ever held in RAM.
    """
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    resp = gateway.resilient_get_stream(url)
    sha = hashlib.sha256()
    total = 0
    try:
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                fh.write(chunk)
                sha.update(chunk)
                total += len(chunk)
    finally:
        resp.close()
    log.info("transport: streamed %d bytes -> %s (sha256=%s…)",
             total, dest_path, sha.hexdigest()[:12])
    return {
        "bytes": total,
        "sha256": sha.hexdigest(),
        "chunk_size": chunk_size,
        "path": dest_path,
    }


def save_bytes(data: bytes, dest_path: str) -> dict:
    """Persist in-memory bytes (b64_json / RAW engines) via chunked writes.

    Even bytes we already hold are written in 64 KiB slices so the write
    path is identical to the streaming path.
    """
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    sha = hashlib.sha256()
    total = 0
    with open(dest_path, "wb") as fh:
        for i in range(0, len(data), CHUNK_SIZE):
            chunk = data[i:i + CHUNK_SIZE]
            fh.write(chunk)
            sha.update(chunk)
            total += len(chunk)
    return {
        "bytes": total,
        "sha256": sha.hexdigest(),
        "chunk_size": CHUNK_SIZE,
        "path": dest_path,
    }
