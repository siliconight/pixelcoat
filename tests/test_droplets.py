"""The drop atlas a rain-drip shader reads.

FOUR CHANNELS, one texture, and the packing is the reference material's:
R,G are the drop normal's XY (Z is reconstructed as 1 in the shader, because a
drop's normal is near-vertical almost everywhere); B is a per-drop random
value that lets each drop run its animation on its own clock; A is the small
drops, which surface tension holds still and which therefore do not animate.

GENERATED, NOT PAINTED. The reference builds this by sculpting drops in
Blender, baking a normal pass and an island-random pass, and recombining the
channels in an image editor -- which is the improvisation
`USING_THE_FACTORY.md` sends people back from, and the part of that workflow
its own author was least happy with.

    python -m pytest tests/test_droplets.py -q
"""

import numpy as np
import pytest

from pixelcoat.core import droplets


@pytest.fixture(scope="module")
def atlas():
    return droplets.drop_atlas(256, seed=1999)


def _ch(a, i):
    return a[..., i].astype(np.float64) / 255.0


# --------------------------------------------------------------------------- #
# The channels carry what the shader reads
# --------------------------------------------------------------------------- #

def test_it_is_four_channel_and_eight_bit(atlas):
    assert atlas.shape == (256, 256, 4)
    assert atlas.dtype == np.uint8


def test_the_normal_channels_sit_around_flat(atlas):
    """0.5 is an encoded zero slope. A drop tilts away from it in both
    directions, so the mean stays near flat while the extremes do not."""
    for i in (0, 1):
        c = _ch(atlas, i)
        assert abs(c.mean() - 0.5) < 0.03
        assert c.min() < 0.35 and c.max() > 0.65


def test_most_of_the_surface_carries_no_drop(atlas):
    """A wall is not covered in water. The B channel is the big-drop mask as
    well as its random value, and zero means no drop here."""
    b = _ch(atlas, 2)
    assert 0.4 < (b == 0).mean() < 0.9


def test_no_drop_carries_a_random_value_of_zero(atlas):
    """A drop whose value is 0 never advances its own animation and sits
    frozen while its neighbours run. The reference names this trap outright,
    which is why there is a floor."""
    b = _ch(atlas, 2)
    live = b[b > 0]
    assert live.min() >= droplets.RANDOM_FLOOR - 1.0 / 255.0


def test_a_drop_is_ONE_value_all_the_way_across(atlas):
    """THE DEFECT THIS CLOSES, visible in the first render as two-tone drops.
    Ownership was claimed only where a drop RAISED the height, so a drop
    landing across an older one came out in two pieces with two random values
    -- half a drop animating on its own clock. A later drop sits ON an earlier
    one and takes its whole footprint.

    Measured as: texels bordering a DIFFERENT drop's value are only the seams
    between touching drops, a small fraction of the drop area."""
    b = (_ch(atlas, 2) * 255).astype(np.int32)
    touching = np.zeros(b.shape, bool)
    for dy, dx in ((0, 1), (1, 0)):
        s = np.roll(np.roll(b, dy, 0), dx, 1)
        touching |= (b > 0) & (s > 0) & (b != s)
    share = touching.sum() / max((b > 0).sum(), 1)
    assert share < 0.05, f"{share:.1%} of drop area borders another drop's value"


def test_the_small_drops_are_small_and_sparse(atlas):
    a = _ch(atlas, 3)
    assert 0.005 < (a > 0.02).mean() < 0.12


# --------------------------------------------------------------------------- #
# It tiles
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("i,name", list(enumerate("RGBA")))
def test_every_channel_tiles(atlas, i, name):
    """The repo's own seam rule: the step across the wrap is no worse than the
    largest step inside. A wall repeats this atlas, and a seam would draw a
    line down it."""
    f = atlas[..., i].astype(np.int32)
    interior = max(np.abs(np.diff(f, axis=0)).max(),
                   np.abs(np.diff(f, axis=1)).max())
    seam = max(np.abs(f[0] - f[-1]).max(),
               np.abs(f[:, 0] - f[:, -1]).max())
    assert seam <= interior * 1.3 + 2, f"{name}: seam {seam} interior {interior}"


def test_a_drop_crossing_the_edge_appears_on_both_sides(atlas):
    b = _ch(atlas, 2)
    assert (b[:, 0] > 0).sum() > 0 and (b[:, -1] > 0).sum() > 0


# --------------------------------------------------------------------------- #
# Determinism and scale
# --------------------------------------------------------------------------- #

def test_the_same_seed_gives_the_same_atlas():
    a = droplets.drop_atlas(128, seed=7)
    b = droplets.drop_atlas(128, seed=7)
    assert np.array_equal(a, b)


def test_a_different_seed_moves_the_drops():
    a = droplets.drop_atlas(128, seed=7)
    b = droplets.drop_atlas(128, seed=8)
    assert not np.array_equal(a, b)


def test_radii_are_fractions_of_the_tile_not_pixels():
    """A texture whose content changed with its resolution would make a size
    bump a LOOK change. The drop area a tile covers must hold roughly steady
    across sizes."""
    cov = []
    for size in (128, 256, 512):
        b = droplets.drop_atlas(size, seed=3)[..., 2]
        cov.append(float((b > 0).mean()))
    assert max(cov) - min(cov) < 0.08, cov


def test_the_count_is_honoured():
    b = droplets.drop_atlas(256, seed=5, big=8, small=10)[..., 2]
    vals = set(np.unique(b).tolist()) - {0}
    assert 4 <= len(vals) <= 8      # some drops land wholly under later ones


def test_no_drops_at_all_is_a_flat_normal_and_an_empty_mask():
    a = droplets.drop_atlas(64, seed=1, big=0, small=0)
    assert (a[..., 2] == 0).all()
    assert (a[..., 3] == 0).all()
    for i in (0, 1):
        assert abs(_ch(a, i).mean() - 0.5) < 0.01
