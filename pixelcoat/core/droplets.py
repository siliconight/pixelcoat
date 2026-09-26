"""The drop atlas a rain-drip shader reads: four channels, one texture.

WHAT IT IS FOR. A shader that beads water on a surface needs to know, per
texel, which way the drop's surface tilts, whether there is a drop there at
all, and -- if it is going to animate -- something that makes each drop behave
differently from its neighbour. That is four channels, and the packing is the
one the reference material uses:

    R, G   the drop normal's X and Y. Z is NOT stored: a drop's normal is
           close to straight up almost everywhere, so the shader reconstructs
           it as 1.0 and the error is invisible. Two channels saved.
    B      a per-drop random value, 0.1..1. Every texel of one drop carries
           the SAME number, so a shader can offset that drop's animation by it
           and no two drops run in step. Never 0: a drop whose random value is
           zero never moves, and the reference calls that out.
    A      the SMALL drops, which do not move at all. Surface tension holds a
           droplet below a certain size in place, so these are a separate mask
           rather than small entries in the big-drop field.

WHY THIS IS GENERATED AND NOT PAINTED. The reference builds this texture by
hand -- sculpting drops in Blender, baking a normal map, baking an island
random pass, then recombining the channels in an image editor. That is exactly
the improvisation `USING_THE_FACTORY.md` sends people back from: the owning
tool grows the capability and nothing is hand-authored downstream. It is also
the part of that workflow the author was least happy with ("I have not a good
artistic skill"), and a generator does not have that problem.

IT TILES. Every drop wraps, so a wall does not show a seam where the atlas
repeats. That is the whole reason the placement writes through a wrapped
accumulator rather than clipping at the edge.

WHAT THIS MODULE DOES NOT DO. It does not shade anything. The cost of a
drip pass on GL Compatibility is unmeasured -- and the last figure this repo
published for a `next_pass` was withdrawn (LF 0.115.0) because the pass was
never drawn -- so no shader ships against a number until one exists.
"""

from __future__ import annotations

import numpy as np

from . import maps, procedural_surface as ps

#: A drop is taller than it is wide: surface tension pulls it into a bead and
#: gravity stretches it down the surface. 1.35 is the reference texture's
#: rough proportion, read off its drops rather than derived.
DROP_ASPECT = 1.35

#: The floor on the per-drop random value. A drop carrying 0 would never
#: advance its own animation and would sit frozen while its neighbours ran --
#: the reference names this trap outright.
RANDOM_FLOOR = 0.1


def _wrapped_add(dst: np.ndarray, patch: np.ndarray, cy: int, cx: int) -> None:
    """Accumulate `patch` into `dst` centred on (cy, cx), wrapping at every
    edge. The wrap is what makes the atlas tile: a drop near the border is the
    same drop arriving on the far side, not a drop cut in half."""
    h, w = dst.shape
    ph, pw = patch.shape
    ys = (np.arange(ph) + cy - ph // 2) % h
    xs = (np.arange(pw) + cx - pw // 2) % w
    np.maximum.at(dst, (ys[:, None], xs[None, :]), patch)


def _dome(radius: int, aspect: float) -> np.ndarray:
    """One drop's height: a flattened hemisphere, taller than wide.

    `sqrt(1 - r^2)` is the hemisphere; a drop is not a hemisphere, but the
    shader only ever reads its GRADIENT, and what matters there is that the
    surface is steep at the rim and flat on top. Anything domed does that.
    """
    ry = max(1, int(round(radius * aspect)))
    yy, xx = np.mgrid[-ry:ry + 1, -radius:radius + 1].astype(np.float32)
    r = np.sqrt((xx / max(radius, 1)) ** 2 + (yy / max(ry, 1)) ** 2)
    return np.sqrt(np.clip(1.0 - r * r, 0.0, 1.0)).astype(np.float32)


def _scatter(size: int, count: int, rng, r_lo: int, r_hi: int,
             aspect: float = DROP_ASPECT):
    """(height, id_field): drops placed on a wrapped canvas, plus which drop
    owns each texel. The id field is what lets the B channel give every texel
    of one drop the same random number."""
    height = np.zeros((size, size), np.float32)
    owner = np.zeros((size, size), np.int32)
    for i in range(1, int(count) + 1):
        rad = int(rng.integers(r_lo, max(r_lo + 1, r_hi)))
        patch = _dome(rad, aspect)
        cy = int(rng.integers(0, size))
        cx = int(rng.integers(0, size))
        _wrapped_add(height, patch, cy, cx)
        # A DROP OWNS ALL OF ITSELF, and the first version did not. It claimed
        # only the texels this drop RAISED above what was already there, so a
        # drop landing across an older one came out in two pieces with two
        # different random values -- visible as two-tone drops in the B
        # channel, and in a shader as half a drop animating on its own clock.
        # A later drop sits ON an earlier one, so it takes the whole footprint
        # and the one underneath keeps what is still uncovered.
        _claim_wrapped(owner, patch > 0.0, cy, cx, i)
    return height, owner


def _claim_wrapped(owner: np.ndarray, mask: np.ndarray, cy: int, cx: int,
                   ident: int) -> None:
    """Stamp `ident` over every texel `mask` covers, wrapped like the height."""
    h, w = owner.shape
    ph, pw = mask.shape
    ys = (np.arange(ph) + cy - ph // 2) % h
    xs = (np.arange(pw) + cx - pw // 2) % w
    sub = owner[ys[:, None], xs[None, :]]
    owner[ys[:, None], xs[None, :]] = np.where(mask, ident, sub)


def drop_atlas(size: int = 512, *, seed: int = 1999, big: int = 26,
               small: int = 120, big_radius=(0.045, 0.085),
               small_radius=(0.008, 0.018), aspect: float = DROP_ASPECT,
               strength: float = 3.0) -> np.ndarray:
    """(size, size, 4) uint8 RGBA: the atlas described at the top of this file.

    Radii are FRACTIONS OF THE TILE, not pixels, so the same call gives the
    same drops at 256 and at 1024 -- a texture whose content changed with its
    resolution would make a size bump a look change.
    """
    rng = np.random.default_rng(ps.stream_seed(seed, "droplets"))
    b_lo = max(1, int(big_radius[0] * size))
    b_hi = max(b_lo + 1, int(big_radius[1] * size))
    s_lo = max(1, int(small_radius[0] * size))
    s_hi = max(s_lo + 1, int(small_radius[1] * size))

    big_h, owner = _scatter(size, big, rng, b_lo, b_hi, aspect)
    small_h, _ = _scatter(size, small, rng, s_lo, s_hi, 1.1)

    # THE NORMAL IS OF THE BIG DROPS ONLY. The small ones do not move, so a
    # shader blends them by their own mask; giving them normals here would
    # bead the whole surface whether or not the drip term was on.
    nrm = maps.normal_from_height(big_h, strength=strength,
                                  wrap_x=True, wrap_y=True)

    # One random value per drop, constant across it, floored so none freezes.
    vals = rng.uniform(RANDOM_FLOOR, 1.0, size=owner.max() + 1).astype(np.float32)
    vals[0] = 0.0                       # texel owned by no drop: no drop here
    rand = vals[owner]
    rand[big_h <= 0.0] = 0.0

    out = np.zeros((size, size, 4), np.float32)
    out[..., 0] = nrm[..., 0]           # normal X, already 0..1 encoded
    out[..., 1] = nrm[..., 1]           # normal Y
    out[..., 2] = rand                  # per-drop random, 0 where no drop
    out[..., 3] = np.clip(small_h, 0.0, 1.0)
    return np.rint(np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8)
