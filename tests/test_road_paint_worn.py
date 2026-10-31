"""Delco's road paint is a 1999 street's: dirty and chipped (0.67.0).

It read crisp and new on the vertical slice's avenue: 90 % coverage, an off-white at 0.87. The map is minted here as the
theme library mints it; its gaps and its brightness are held to a worn line's.

FAILS ON 0.66.0: a tenth gone and 0.87 bright.
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def test_the_delco_road_paint_is_worn(tmp_path):
    out = tmp_path / "p"
    r = subprocess.run([sys.executable, "-m", "pixelcoat.cli.main", "proc-pack",
                        os.path.join(ROOT, "profiles", "materials", "road_paint_delco.json"),
                        "--out", str(out), "--asset-id", "road_paint_delco", "--size", "512"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    a = np.asarray(Image.open(out / "road_paint_delco_albedo.png").convert("RGBA"), dtype=float) / 255.0
    gone = float((a[..., 3] < 0.5).mean())
    assert 0.15 <= gone <= 0.25, gone
    assert float(a[..., :3][a[..., 3] >= 0.5].mean()) <= 0.8
