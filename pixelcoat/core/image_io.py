"""Image load/save + source hashing (TDD 7.1). Sources are never modified."""

from __future__ import annotations

import hashlib

import numpy as np
from PIL import Image


def load(path: str) -> tuple[np.ndarray, str]:
    """Load an image as float RGBA (0..1) plus the sha256 of the file bytes."""
    with open(path, "rb") as f:
        data = f.read()
    sha = hashlib.sha256(data).hexdigest()
    im = Image.open(path)
    im.load()
    arr = np.asarray(im.convert("RGBA"), np.float32) / 255.0
    return arr, sha


def save_png(arr: np.ndarray, path: str) -> None:
    """Save float RGBA/RGB (0..1) as PNG."""
    a = (np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    mode = "RGBA" if a.shape[-1] == 4 else "RGB"
    Image.fromarray(a, mode).save(path)
