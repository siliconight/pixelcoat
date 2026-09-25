"""What a pack manifest says about the files it names.

A PACK MANIFEST NAMED FILENAMES AND SAID NOTHING ABOUT WHAT WAS IN THEM, and
that turned out to be a live defect rather than an untidiness. A consumer that
wants to know "did this material change" reaches for the manifest -- it is one
small JSON beside a directory of PNGs, and hashing it is the obvious cheap
thing. Level Factory's Zoo adapter did exactly that, and it was wrong:

    asphalt_delco.pack.json    fd4678dbc03ab70f -> fd4678dbc03ab70f  IDENTICAL
    asphalt_delco_albedo.png   68e2fd2cb8509e28 -> 500265cbf2630a20  differs

(`asphalt_delco` rebuilt with a different `base_colors`, 2026-09-24 -- a pure
appearance retune, which is what a grammar edit usually is.) The kit job's
fingerprint did not move, the cache hit, and because Zoo bakes these maps into
a GLB, what shipped was the previously baked material. Level Factory 0.111.0
fixed the consumer by hashing every map a pack names; this fixes the PRODUCER,
so the next consumer does not have to know.

`map_sha256` IS A CLAIM, NOT A SUBSTITUTE FOR HASHING THE FILES. It is written
by the process that wrote them, so it proves what the producer emitted and not
what is on disk now. A consumer whose question is "have these bytes changed
since I last looked" should still hash the bytes -- that is why LF 0.111.0
stays as it is. What this buys is threefold and none of it is the same thing:

  * A manifest that MOVES when the pixels move, so the obvious cheap thing a
    consumer does is no longer silently wrong.
  * A check that a pack is INTACT: a map that no longer matches its digest was
    truncated, half-written or edited, which is a corrupt pack and is worth
    saying at the adapter boundary rather than discovering in Blender.
  * One hash computed once at build time in place of every consumer re-hashing
    every PNG on every fingerprint.

THE NAME FOLLOWS `source_sha256`, which `pipeline_pixel` and
`pipeline_generation_7` have carried since 0.7 -- the same idea pointed at the
input. Additive, so `pixelcoat-pack/2` does not move: its own writer says
"additive over pack/1 -- downstream tools that only know pack/1 keep reading
maps/tileable/meters_per_tile the same way", and a tool that does not know
`map_sha256` reads the pack exactly as before.

ONE FUNCTION, FIVE IMPORTERS, and deliberately. Five places write a pack
manifest -- the grammar library, the gen7 pipeline, the pixel pipeline, decals
and signage -- and `packages/core/hashing.py` says what a second copy costs:
"a second copy is the drift this toolchain keeps paying for ... so it is one
function with two importers."
"""

from __future__ import annotations

import hashlib
import os

#: What a map whose file is not on disk records. A pack that NAMES a map it
#: did not write is broken, and a digest block that quietly omitted it would
#: make the broken pack and a complete one hash the same -- the very failure
#: this module exists to stop. LF's Zoo fingerprint uses the same marker for
#: the same reason.
MISSING = "<missing>"


def map_sha256(pack_dir: str, maps: dict) -> dict:
    """``{map key: sha256 hex}`` for every map ``maps`` names, read from disk.

    READ BACK RATHER THAN HASHED IN MEMORY, on purpose. The digest should
    describe the bytes a consumer will open, so a PNG encoder that is not
    byte-deterministic, a short write or a file that never landed shows up here
    instead of being asserted away. Pixelcoat's pack write IS deterministic
    (`test_pack_write_is_deterministic`), which makes the read-back cheap
    insurance rather than a workaround.

    ``maps`` is ``{key: filename}`` relative to ``pack_dir``, exactly as the
    manifest's own ``maps`` block carries it.
    """
    out: dict[str, str] = {}
    for key in sorted(maps):
        path = os.path.join(pack_dir, str(maps[key]))
        try:
            with open(path, "rb") as f:
                out[key] = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            out[key] = MISSING
    return out


def verify(pack_dir: str, manifest: dict) -> list[str]:
    """Why ``manifest`` disagrees with the files beside it, as sentences.

    Empty means every map it names is present and matches its digest. A
    manifest with no ``map_sha256`` returns empty too: packs written before
    0.47.0 have nothing to disagree with, and reporting them as faults would
    turn an upgrade into a wall of findings about files that are fine.
    """
    claimed = manifest.get("map_sha256")
    if not isinstance(claimed, dict) or not claimed:
        return []
    maps = manifest.get("maps")
    if not isinstance(maps, dict):
        return ["pack manifest carries map_sha256 but no maps block"]

    problems: list[str] = []
    actual = map_sha256(pack_dir, maps)
    for key in sorted(set(claimed) | set(actual)):
        want, got = claimed.get(key), actual.get(key)
        if want is None:
            problems.append(f"map '{key}' is named but has no digest")
        elif got is None:
            problems.append(f"digest names map '{key}', which the pack does not")
        elif got == MISSING:
            problems.append(f"map '{key}' ({maps.get(key)}) is not on disk")
        elif got != want:
            problems.append(
                f"map '{key}' ({maps.get(key)}) does not match its digest: "
                f"manifest says {want[:16]}, file is {got[:16]}")
    return problems
