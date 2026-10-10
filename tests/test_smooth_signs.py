"""A business's sign on its street band: Blue Highway, smooth, at the band's shape (0.62.0).

Roadmap 223, note 10 of the walk of 2026-10-09 generalised. The walker decided "use Blue Highway for
the shop signs", and Zoo 1.90.0 set the name it paints over a door in Blue Highway Condensed. The
pack Level Factory deals a business was still Pixel Operator, thresholded and sampled nearest, and
drawn as a 4:1 cabinet that Lot hangs on a 6:1 band, so every band's letters stood 1.5x too wide
(`docs/findings/street_band_type/` at the factory root).
"""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from pixelcoat.core import signage as sgn
from pixelcoat.core import smooth_type

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROFILE = os.path.join(_ROOT, "profiles", "signs", "delco_1997.json")


def _businesses():
    with open(_PROFILE, encoding="utf-8") as f:
        return [s for s in json.load(f)["signs"] if s.get("style") != "price"]


def test_the_shop_face_is_what_the_font_gives():
    """The minted table is the vendored OTF's, and the mint tool says so."""
    rc = subprocess.run([sys.executable, os.path.join(_ROOT, "tools", "mint_smooth_type.py"),
                         "--check"], capture_output=True, text=True)
    assert rc.returncode == 0, rc.stdout + rc.stderr


def test_the_shop_face_is_zoos_byte_for_byte():
    """The band and the door are one face at one em. Measured 2026-10-10: 162,355 bytes each."""
    zoo = os.path.join(os.path.dirname(_ROOT), "zoo", "zoo_keeper", "core", "smooth_faces",
                       "highway_cond.py")
    if not os.path.isfile(zoo):
        pytest.skip("Zoo is not beside this repo")
    mine = os.path.join(_ROOT, "pixelcoat", "core", "smooth_faces", "highway_cond.py")
    assert open(mine, "rb").read() == open(zoo, "rb").read()


def test_every_business_name_sets_large_on_its_band():
    """Measured, not counted: every name's cap height on a 1536 x 256 band, inside the margins
    `signage` keeps. The longest names stop at the width; none drops under 100 px of the 256.
    Measured 2026-10-10: 112 for DOWN THE SHORE BREWING, the least, and a median of 137."""
    caps = {}
    for s in _businesses():
        caps[s["text"]] = smooth_type.fit_cap(s["text"], 1536 * sgn.SMOOTH_MARGIN_W,
                                              256 * sgn.SMOOTH_MARGIN_H)
    assert all(c is not None for c in caps.values()), [t for t, c in caps.items() if c is None]
    assert min(caps.values()) >= 100, sorted(caps.items(), key=lambda kv: kv[1])[:3]


def test_smooth_lettering_is_anti_aliased_and_the_same_every_time():
    a = sgn.panel_sign("GOOSE MART", (256, 1536), panel="#c8102e", text_color="#fff6e5",
                       face=smooth_type.SHOP_FACE)
    b = sgn.panel_sign("GOOSE MART", (256, 1536), panel="#c8102e", text_color="#fff6e5",
                       face=smooth_type.SHOP_FACE)
    assert all(np.array_equal(a[k], b[k]) for k in a)
    # the letters' edges are partial pixels, not ink-or-nothing
    alb = a["albedo"].astype(int)
    panel, ink = np.array([200, 16, 46]), np.array([255, 246, 229])
    between = ~np.all(alb == panel, axis=-1) & ~np.all(alb == ink, axis=-1)
    assert between.sum() > 1000


def test_the_pixel_path_is_unchanged():
    """No face, no change: the EXIT signs and the CLI's `sign` keep Pixel Operator."""
    out = sgn.panel_sign("EXIT", 96)
    vals = np.unique(out["emissive"][..., 1])
    assert len(vals) <= 3


def test_a_name_that_does_not_set_raises():
    with pytest.raises(ValueError, match="does not set"):
        sgn.panel_sign("SCRAPPLE SUPERMARKET AND DELICATESSEN", (8, 16),
                       face=smooth_type.SHOP_FACE)


def test_a_pack_asks_for_one_of_two_samplings(tmp_path):
    arrays = sgn.panel_sign("BAR", (16, 96), face=smooth_type.SHOP_FACE)
    man = sgn.build_sign_pack(str(tmp_path / "s"), arrays, "sign_bar", interpolation="linear",
                              mipmaps=True)
    assert man["import_hints"]["interpolation"] == "linear"
    assert man["import_hints"]["generate_mipmaps"] is True
    with pytest.raises(ValueError):
        sgn.build_sign_pack(str(tmp_path / "t"), arrays, "sign_t", interpolation="cubic")


def test_theme_signs_draws_the_band_s_shape_smooth_and_filtered(tmp_path):
    """FAILS on 0.61.0: 512 x 128, a 4:1 cabinet, Pixel Operator, nearest."""
    from pixelcoat.cli.main import main
    from PIL import Image
    assert main(["theme-signs", "--theme", "delco_1997", "--out", str(tmp_path / "signs")]) == 0
    idx = json.loads((tmp_path / "signs" / "signs.index.json").read_text(encoding="utf-8"))
    assert idx["signs"]
    for s in idx["signs"]:
        d = tmp_path / "signs" / s["dir"]
        (man_path,) = list(d.glob("*.pack.json"))
        man = json.loads(man_path.read_text(encoding="utf-8"))
        w, h = Image.open(d / man["maps"]["albedo"]).size
        if s["style"] == "price":
            assert man["import_hints"]["interpolation"] == "nearest" and w == 512
            continue
        assert (w, h) == (1536, 256), (s["slug"], w, h)          # Lot's SIGN_ASPECT, 6:1
        assert man["import_hints"]["interpolation"] == "linear"
        assert man["import_hints"]["generate_mipmaps"] is True
