"""Pixelcoat has to agree with itself about what version it is.

IT DID NOT, FOR 32 RELEASES. `VERSION` and `pixelcoat/version.py` were created
in the same commit at 0.10.0 (351bf7c, 2026-07-18) and agreed exactly through
0.16.0 (7bedbb1, 2026-08-21). After that `VERSION` advanced 32 times and the
literal in `version.py` never moved, so `tool_version` in every pack manifest,
atlas manifest, batch report and decal -- and the version `pyproject.toml`
publishes, which reads that same attribute -- said 0.16.0 while the tool was on
0.46.0. Nothing caught it because nothing asked.

WHAT THESE PIN. That `__version__` comes FROM `VERSION` rather than from a
second literal beside it; that the wheel fallback still matches the file; and
that `pyproject.toml` keeps deriving rather than being given a number of its
own. The point is not the current value -- it is that there is one place to
change it.

WHY `VERSION` IS THE ONE THAT COUNTS. Level Factory's `_read_tool_version`
(`packages/adapters/sdk.py:172`) reads a repo's `VERSION` file first and only
falls back to a package `__version__`, so `VERSION` is already the number every
build fingerprint carries.
"""

import re
from pathlib import Path

import pytest

from pixelcoat import version as v

_REPO = Path(__file__).resolve().parents[1]
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _version_file_text():
    return (_REPO / "VERSION").read_text(encoding="utf-8").strip()


def test_the_version_file_exists_and_names_a_semver():
    """PIPELINE_MAP.md still says Pixelcoat's version "lives in
    `pixelcoat/version.py`, not a root VERSION file", and lists pixelcoat under
    the tools `verify-manifest` reports UNKNOWN for want of a VERSION source.
    Both statements went stale on 2026-07-18 when 351bf7c added this file."""
    text = _version_file_text()
    assert text, "VERSION is empty -- that is Patina's state, and it reports UNKNOWN"
    assert _SEMVER.match(text.split()[-1]), text


def test_the_module_reads_the_file_rather_than_repeating_it():
    assert v.__version__ == _version_file_text().split()[-1]


def test_the_wheel_fallback_matches_the_file():
    """`_FALLBACK` is what an installed wheel gets, since `VERSION` is not
    package data. It is a second string, so it needs a test; this is that
    test, and it is the whole reason a second string is acceptable."""
    assert v._FALLBACK == _version_file_text().split()[-1], (
        "pixelcoat/version.py's _FALLBACK and the VERSION file disagree. "
        "Change both, or the number an installed copy reports is not the "
        "number a source checkout does.")


def test_pyproject_still_derives_its_version():
    """A literal in pyproject would be a third place to remember. It already
    derives from this module's attribute, which now derives from the file, so
    all three follow one number."""
    text = (_REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'dynamic\s*=\s*\[\s*"version"\s*\]', text)
    assert re.search(r'version\s*=\s*\{\s*attr\s*=\s*'
                     r'"pixelcoat\.version\.__version__"\s*\}', text), (
        "pyproject stopped deriving pixelcoat's version from the module")


def test_the_changelog_leads_with_the_version_that_shipped():
    """The release convention: `VERSION` and the top CHANGELOG heading move
    together. LF's own suite pins the same thing about itself."""
    head = ""
    for line in (_REPO / "CHANGELOG.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## ["):
            head = line
            break
    assert head, "no `## [x.y.z]` heading in CHANGELOG.md"
    assert head.startswith("## [%s]" % _version_file_text().split()[-1]), (
        "VERSION is %r but the CHANGELOG leads with %r"
        % (_version_file_text(), head))


def test_a_missing_version_file_falls_back_instead_of_crashing(tmp_path):
    """An installed wheel has no VERSION beside the package. Reading must
    return None so `__version__` takes the fallback -- not raise on import,
    which would make the package unimportable wherever it is installed."""
    assert v.read_version_file(tmp_path / "nope" / "VERSION") is None


def test_an_empty_version_file_is_not_a_version(tmp_path):
    """Patina ships an empty VERSION and `verify-manifest` reports UNKNOWN for
    it. An empty string is information about an absence; returning it as a
    version would stamp `tool_version: ""` into every manifest."""
    p = tmp_path / "VERSION"
    p.write_text("   \n", encoding="utf-8")
    assert v.read_version_file(p) is None


@pytest.mark.parametrize("text,want", [
    ("Pixelcoat 0.46.0", "0.46.0"),
    ("0.46.0", "0.46.0"),
    ("Pixelcoat 0.46.0\n", "0.46.0"),
])
def test_the_tool_name_is_stripped(tmp_path, text, want):
    """The file carries a name and a number; Level Factory's own reader keeps
    the raw string and normalises later, but a `tool_version` of
    'Pixelcoat 0.46.0' inside a pack manifest is a string nobody can compare."""
    p = tmp_path / "VERSION"
    p.write_text(text, encoding="utf-8")
    assert v.read_version_file(p) == want
