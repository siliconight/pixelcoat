"""A crown card's cutout made of leaves, not discs (0.65.0, the factory's roadmap 324).

The walker, 2026-10-30, of the vertical slice's street trees: "try the card-based trees". The foliage pack's cutout was
a Worley field at 7 cells a tile -- a dozen plate-sized discs on a 4 m card -- so a card crown read as green circles.
`cutout.leaves` scatters small leaves in sprays inside the card's ellipse.
"""
import json
import pathlib

import numpy as np

from pixelcoat.core import material_grammar as G

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _keep(seed=7):
    return G.leaf_scatter((256, 256), {"sprays": 10, "per": 120, "length": 7.0}, seed, {"rx": 0.46, "ry": 0.44})


def test_the_foliage_profile_asks_for_leaves():
    """FAILS ON 0.64.0: the profile's cutout was the Worley discs."""
    d = json.loads((ROOT / "profiles" / "materials" / "foliage_delco.json").read_text(encoding="utf-8"))
    assert d["cutout"].get("leaves"), d["cutout"]
    assert d["transparency"]["alpha_mode"] == "scissor"


def _pieces(keep):
    """Connected pieces of a mask, 4-neighbour, wrapped as the tile is -- a flood fill, no SciPy."""
    h, w = keep.shape
    seen = np.zeros_like(keep)
    n = 0
    for y, x in zip(*np.nonzero(keep)):
        if seen[y, x]:
            continue
        n += 1
        stack = [(y, x)]
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            for ny, nx in (((cy + 1) % h, cx), ((cy - 1) % h, cx), (cy, (cx + 1) % w), (cy, (cx - 1) % w)):
                if keep[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
    return n


def test_many_small_leaves_not_a_few_discs():
    """Connected pieces of the cutout: a leaf scatter's sprays break into many; seven Worley cells make about a
    dozen."""
    keep, _shade = _keep()
    n = _pieces(keep)
    assert n >= 30, n
    assert 0.05 < keep.mean() < 0.6, keep.mean()


def test_the_leaves_stay_inside_the_cards_ellipse_and_differ_in_shade():
    keep, shade = _keep()
    h, w = keep.shape
    fy, fx = np.meshgrid((np.arange(h) + 0.5) / h, (np.arange(w) + 0.5) / w, indexing="ij")
    dx, dy = np.minimum(fx, 1.0 - fx), np.minimum(fy, 1.0 - fy)
    outside = (dx / 0.46) ** 2 + (dy / 0.44) ** 2 > 1.35       # a leaf may reach a little past its centre's ellipse
    assert not keep[outside].any()
    assert len(np.unique(np.round(shade[keep], 3))) > 20


def test_deterministic_for_a_seed():
    a, sa = _keep(3)
    b, sb = _keep(3)
    c, _sc = _keep(4)
    assert (a == b).all() and (sa == sb).all() and not (a == c).all()
