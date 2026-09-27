"""drywall_orangepeel_delco: neither spots nor static.

The 0.51.0 grammar drew 8 cm Worley cells at 0.42 weight and read as a
spotted hide on every interior wall; the first replacement traded the
spots for texel-scale static and failed the ac1 floor in
`test_theme_profiles.py` (CHANGELOG 0.52.0). Real orange peel is 2-5 mm and
sub-texel at this pack's 7.8 mm/texel, so no grammar here can draw the
finish; what it CAN avoid is both failure modes, and this measures both.
The ac1 floor itself stays in `test_theme_profiles.py`.
"""
import os

import numpy as np

from pixelcoat.core import material_grammar as mg
from tools import art_standard_audit as audit

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_MATERIALS = os.path.join(_ROOT, "profiles", "materials")
_SEED = 1999
GID = "drywall_orangepeel_delco"

#: the wavelength band an 8 cm Worley cell lives in, mm
BLOB_MM = (40.0, 150.0)
#: shipped 0.51.0 measured 48.0%; 0.52.0 9.2%; the flat sibling 10.0%
BLOB_SHARE_MAX = 0.25
#: under 20 mm is two texels and below: the static band. The retracted
#: Worley-at-120 candidate measured 33%; 0.52.0 18%; the sibling 26%
GRAIN_MM = (0.0, 20.0)
GRAIN_SHARE_MAX = 0.25


def _load(gid):
    return mg.MaterialGrammar.load(os.path.join(_MATERIALS, gid + ".json"))


def _synth(gid):
    g = _load(gid)
    px = mg.pack_size_for(g.meters_per_tile)
    return g, px, mg.synthesize(g, size=px, seed=_SEED)


def _luma01(albedo_u8):
    a = albedo_u8[..., :3].astype(np.float64)
    return (0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]) / 255.0


def band_share(albedo_u8, meters_per_tile, lo_mm, hi_mm):
    """Share of the tile's luminance variance whose wavelength, in mm on
    the wall, falls in [lo_mm, hi_mm]. Radial power spectrum; DC excluded.
    The tile is square, so one axis sets the scale."""
    a = _luma01(albedo_u8)
    a = a - a.mean()
    px = a.shape[0]
    mm_per_px = meters_per_tile * 1000.0 / px
    f = np.abs(np.fft.fftshift(np.fft.fft2(a))) ** 2
    cy, cx = np.array(f.shape) // 2
    yy, xx = np.indices(f.shape)
    k = np.hypot(yy - cy, xx - cx)
    wl = np.where(k > 0, (px / np.maximum(k, 1e-9)) * mm_per_px, np.inf)
    tot = f[k > 0].sum()
    return float(f[(wl >= lo_mm) & (wl <= hi_mm)].sum() / tot)


def _wrap_no_worse_than_interior(arr):
    a = arr.astype(np.int32)
    if a.ndim == 2:
        a = a[..., None]
    rows = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))
    cols = np.abs(np.diff(a, axis=1)).mean(axis=(0, 2))
    wy = float(np.abs(a[0] - a[-1]).mean())
    wx = float(np.abs(a[:, 0] - a[:, -1]).mean())
    return (wy, float(rows.max())), (wx, float(cols.max()))


def test_orange_peel_is_not_a_blob_field():
    """The cheetah print, as a number. Fails against the 0.51.0 grammar
    (48%) and passes the 0.52.0 one (13.5%), with the flat `drywall_delco`
    at 10% as the floor a plain wall sits on."""
    g, _, s = _synth(GID)
    share = band_share(s["albedo"], g.meters_per_tile, *BLOB_MM)
    assert share <= BLOB_SHARE_MAX, share
    # ...and the metric can see a blob field: the grammar that was the
    # defect, rebuilt from the shipped numbers, sits well over the line.
    raw = dict(g.__dict__)
    raw["bands"] = {"macro": 0.18, "meso": 0.42, "micro": 0.3}
    raw["meso"] = {"generator": "worley_f1", "cells": 24}
    raw["micro"] = {"generator": "fbm", "cells": 40, "octaves": 2}
    old = mg.MaterialGrammar.from_dict(raw)
    px = mg.pack_size_for(old.meters_per_tile)
    was = band_share(mg.synthesize(old, size=px, seed=_SEED)["albedo"],
                     old.meters_per_tile, *BLOB_MM)
    assert was > 1.5 * BLOB_SHARE_MAX, was    # measured 0.480


def test_orange_peel_is_not_static_either():
    """The other failure mode, the one the first replacement had. Worley at
    120 cells passed the blob gate and put a third of the tile's variance
    under 20 mm -- ac1 0.27 -- which is the digital noise the theme test's
    floor exists for. Flatter than it was, not flat: some contrast stays."""
    g, _, s = _synth(GID)
    grain = band_share(s["albedo"], g.meters_per_tile, *GRAIN_MM)
    assert grain <= GRAIN_SHARE_MAX, grain
    lum = _luma01(s["albedo"])
    assert 0.02 <= lum.std() <= 0.06, lum.std()
    raw = dict(g.__dict__)
    raw["bands"] = {"macro": 0.18, "meso": 0.22, "micro": 0.4}
    raw["meso"] = {"generator": "worley_f1", "cells": 120}
    raw["micro"] = {"generator": "fbm", "cells": 160, "octaves": 2}
    c = mg.MaterialGrammar.from_dict(raw)
    px = mg.pack_size_for(c.meters_per_tile)
    was = band_share(mg.synthesize(c, size=px, seed=_SEED)["albedo"],
                     c.meters_per_tile, *GRAIN_MM)
    assert was > GRAIN_SHARE_MAX, was    # measured 0.333


def test_orange_peel_tiles_and_meets_the_art_standard():
    """Held to the audit's own budget rather than to zero, because the
    0.51.0 grammar was ALSO blown on 2.2% of its texels against a 1%
    budget -- a light base colour under an 0.42 blob band -- and nothing
    had ever measured it. 0.52.0 measures 0.18%."""
    g, _, s = _synth(GID)
    for key, arr in s.items():
        for wrap, worst in _wrap_no_worse_than_interior(arr):
            assert wrap <= worst + 1e-6, (key, wrap, worst)
    row = audit.measure(g, mg.synthesize(g, size=256, seed=_SEED))
    b = audit.ENV_BUDGET
    assert row["crushed_frac"] <= b["crushed_frac"], row["crushed_frac"]
    assert row["blown_frac"] <= b["blown_frac"], row["blown_frac"]
    assert row["value_range"] <= b["value_range"], row["value_range"]
    assert row["rough_mean"] >= b["rough_mean_min"], row["rough_mean"]
    assert not row["emissive"]
    assert set(s) == {"albedo", "roughness"}, sorted(s)
