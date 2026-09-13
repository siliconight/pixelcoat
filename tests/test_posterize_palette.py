"""A near-neutral palette is the FRAGILE case for `posterize`, and the
library had three grammars where the quantiser, not the author, chose the
colour.

`ps.posterize` steps every channel INDEPENDENTLY. A colour whose channels
differ by less than one step (255 / n) therefore has channels that collide
or separate according to where they happen to fall, and the survivor decides
the hue. Measured on `fieldstone_delco`'s first palette at n = 12, step 21.2:

    #6e685d  ->  (116,  93,  93)   a pink
    #7a7266  ->  (116, 116,  93)   an olive
    #8c8578  ->  (139, 139, 116)   a yellow-green

Five warm greys, all inside 20 codes of neutral, came out of one render as a
harlequin of olive and mauve -- which is what the walker would have seen on
every stone wall in the level.

WHY THIS TEST IS SCOPED TO FLAT FILLS. Where a palette colour is modulated
by a noise band, the noise dithers across the quantiser's levels and the
mean colour survives; 35 of the library's grammars have palettes finer than
their own step and look correct for that reason. Where a palette colour is
POURED FLAT into a region -- `aggregate`'s Voronoi cells, `masonry`'s units
-- there is nothing to dither with, and the error is the whole cell. So the
rule is asserted exactly where it bites.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pixelcoat.core import procedural_surface as ps   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAT_FILL = ("aggregate", "masonry")


def _spread(hex_color):
    """The colour's channel spread in 0-255 codes."""
    r, g, b = (v * 255.0 for v in ps.hex_to_rgb(hex_color))
    return max(r, g, b) - min(r, g, b)


def test_a_flat_filled_palette_is_coarser_than_its_own_quantiser():
    offenders = []
    checked = 0
    for path in sorted(glob.glob(os.path.join(HERE, "profiles", "materials",
                                              "*.json"))):
        g = json.load(open(path, encoding="utf-8"))
        n = int(g.get("posterize") or 0)
        if not n:
            continue
        step = 255.0 / n
        for band in FLAT_FILL:
            colors = (g.get(band) or {}).get("colors")
            if not colors:
                continue
            checked += 1
            worst = min(_spread(c) for c in colors)
            if worst < step:
                offenders.append(
                    f"{os.path.basename(path)}: {band} palette's narrowest "
                    f"colour spans {worst:.0f} codes, posterize {n} steps "
                    f"every {step:.1f} -- the quantiser picks the hue")
    assert checked >= 5, f"only {checked} flat-fill palettes found; check the glob"
    assert not offenders, "\n".join(offenders)
