"""Delco's asphalt mints at a weathered road's albedo (0.66.0).

The base colours were minted at #33322f / #3a3936 / #2c2b28 and the pack's albedo map measured 0.035 linear -- darker
than fresh asphalt (about 0.05-0.10) and a third of a weathered road's (0.10-0.20). At Blue Hour the vertical slice's
avenue read as a black band under every street view (the factory's `docs/findings/sodium_pools/`). The map is minted
here as the theme library mints it and its mean is held to an old road's band.

FAILS ON 0.65.0: 0.035.
"""
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


# asphalt_street, an older grammar no Delco theme draws, is left as it was: nothing has seen it on a level.
@pytest.mark.parametrize("grammar", ["asphalt_delco"])
def test_the_asphalt_is_a_weathered_roads_albedo(grammar, tmp_path):
    out = tmp_path / grammar
    r = subprocess.run([sys.executable, "-m", "pixelcoat.cli.main", "proc-pack",
                        os.path.join(ROOT, "profiles", "materials", grammar + ".json"),
                        "--out", str(out), "--asset-id", grammar, "--size", "256"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    a = np.asarray(Image.open(out / (grammar + "_albedo.png")).convert("RGB"), dtype=float) / 255.0
    linear = float((a ** 2.2).mean())
    assert 0.08 <= linear <= 0.20, linear
