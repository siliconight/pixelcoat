"""Delco's sidewalk is flecked with gum and patched with grime (0.68.0).

A 1999 Philly sidewalk; the vertical slice's slabs were clean. The map is minted here as the theme library mints it
and its near-black flecks counted.

FAILS ON 0.67.0: 0.1 % of the tile under the cut, the mortar's corners; with the gum 1.7 %.
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def test_the_delco_sidewalk_is_flecked_with_gum(tmp_path):
    out = tmp_path / "s"
    r = subprocess.run([sys.executable, "-m", "pixelcoat.cli.main", "proc-pack",
                        os.path.join(ROOT, "profiles", "materials", "sidewalk_delco.json"),
                        "--out", str(out), "--asset-id", "sidewalk_delco", "--size", "256"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    luma = np.asarray(Image.open(out / "sidewalk_delco_albedo.png").convert("L"), dtype=float) / 255.0
    flecks = float((luma < 0.28).mean())
    assert 0.01 <= flecks <= 0.04, flecks
