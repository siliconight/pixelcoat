"""Single source of truth for the Pixelcoat version.

Baked into every recipe, manifest, and build report so output is traceable
to the exact tool revision. Fixed per release, never a timestamp.

IT WAS NOT A SINGLE SOURCE, AND THAT IS WHY IT IS DERIVED NOW. `VERSION` and
this module were created together at 0.10.0 (commit 351bf7c, 2026-07-18) and
agreed exactly through 0.16.0 (7bedbb1, 2026-08-21). Then 32 releases moved
`VERSION` and none moved the literal here, so every pack manifest, atlas
manifest, batch report and decal written since August claimed to have been
built by 0.16.0 -- and `pyproject.toml`, which reads this attribute, published
the same. Not a deliberate divergence like Lot's (PIPELINE_MAP.md says so of
Lot and says nothing of the kind here): two strings to keep in sync, and a
second place to remember is a place to forget.

`VERSION` IS THE ONE THAT COUNTS, so it is the one that is read. Level
Factory's `_read_tool_version` (`packages/adapters/sdk.py:172`) tries a repo's
`VERSION` file FIRST and only falls back to a package `__version__`, so
`VERSION` is already the number every build fingerprint carries. Making this
module follow it points the manifests at the number the pipeline already
trusts, and it inverts the direction of the neglect: the file people actually
edit at release time is the one that decides.

`_FALLBACK` covers an installed wheel, where `VERSION` is not package data.
`tests/test_version_is_single_sourced.py` fails when it disagrees with the
file, so the pair cannot drift the way the old literal did.
"""

from pathlib import Path

#: Used only when `VERSION` is not on disk (an installed wheel). Pinned to the
#: file by a test -- do not edit one without the other.
_FALLBACK = "0.46.1"

#: The repo root, two levels up from this module: <repo>/pixelcoat/version.py
VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def read_version_file(path: Path | None = None) -> str | None:
    """The semver in a `VERSION` file, or None if there is nothing to read.

    The file reads ``Pixelcoat 0.46.0`` -- a name and a number -- so the name
    is stripped. A file that exists but holds no version returns None rather
    than an empty string: an empty `VERSION` is the state Patina is in and it
    reports UNKNOWN downstream, which is information and not a version.
    """
    p = VERSION_FILE if path is None else path
    try:
        text = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    return text.split()[-1]


__version__ = read_version_file() or _FALLBACK

RECIPE_SCHEMA_VERSION = "0.7"

# Matches the Deli Counter / Patina convention: the pipeline's shared
# determinism story.
DEFAULT_SEED = 1999
