"""Folder batch processing (TDD §6.2).

One style profile for the whole folder, or presets mapped by filename
pattern (fnmatch, first match wins, template as fallback). Each image
processes deterministically in sorted order; a failed file is recorded
and the batch continues (§6.2.4); every asset gets its own pack
manifest as usual; optional atlas generation combines the compatible
outputs at the end (§6.2.6).

Templates are ordinary recipe JSON — a saved .pixelcoat.json works
as-is. ``asset_id`` and ``source.path`` are injected per file, so a
template may omit them. Asset ids come from the file stem; collisions
(same stem in different subfolders under --recursive) disambiguate by
prefixing parent folder names until unique — deterministically.
"""

from __future__ import annotations

import copy
import fnmatch
import json
import os
import time

from ..recipe import Recipe
from ..version import __version__
from . import atlas as atlas_mod
from . import pipeline

_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga")


def run_batch(input_dir: str, out_dir: str,
              template: dict | None = None,
              pattern_map: list[tuple[str, dict]] | None = None,
              recursive: bool = False,
              atlas_name: str | None = None,
              gutter: int = 2, pow2: bool = False) -> dict:
    t0 = time.perf_counter()
    files = _scan(input_dir, recursive)
    if not files:
        raise ValueError(f"no images found under {input_dir}")
    ids = _asset_ids(files, input_dir)

    os.makedirs(out_dir, exist_ok=True)
    built: list[dict] = []
    failures: list[dict] = []
    for path in files:
        rel = os.path.relpath(path, input_dir)
        try:
            recipe = _make_recipe(path, ids[path], template,
                                  pattern_map or [])
            recipe.validate()
            report = pipeline.build(recipe, out_dir)
            built.append({"file": rel, "asset_id": ids[path],
                          "maps": report["maps"],
                          "warnings": report.get("warnings", []),
                          "duration_seconds": report["duration_seconds"]})
        except Exception as e:                    # noqa: BLE001 — §6.2.4:
            failures.append({"file": rel, "error": str(e)})
            continue                              # a bad file never stops
                                                  # the batch

    batch: dict = {
        "tool_version": __version__,
        "input": os.path.abspath(input_dir),
        "processed": len(built),
        "failed": len(failures),
        "entries": built,
        "failures": failures,
    }

    if atlas_name and built:
        packs = [os.path.join(out_dir, e["asset_id"],
                              f"{e['asset_id']}.pack.json") for e in built]
        try:
            batch["atlas"] = atlas_mod.build_atlas(
                packs, atlas_name, out_dir, gutter=gutter, pow2=pow2)
        except ValueError as e:
            batch["atlas_error"] = str(e)

    batch["duration_seconds"] = round(time.perf_counter() - t0, 4)
    with open(os.path.join(out_dir, "batch_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(batch, f, indent=2)
    return batch


def _scan(input_dir: str, recursive: bool) -> list[str]:
    out: list[str] = []
    if recursive:
        for root, _dirs, names in sorted(os.walk(input_dir)):
            out += [os.path.join(root, n) for n in sorted(names)
                    if n.lower().endswith(_EXTENSIONS)]
    else:
        out = [os.path.join(input_dir, n)
               for n in sorted(os.listdir(input_dir))
               if n.lower().endswith(_EXTENSIONS)]
    return out


def _asset_ids(files: list[str], input_dir: str) -> dict[str, str]:
    """File stem, prefixed with parent folders until unique."""
    ids: dict[str, str] = {}
    taken: set[str] = set()
    for path in files:                            # sorted: deterministic
        rel = os.path.relpath(path, input_dir)
        parts = os.path.normpath(rel).split(os.sep)
        parts[-1] = os.path.splitext(parts[-1])[0]
        for depth in range(1, len(parts) + 1):
            cand = "_".join(parts[-depth:])
            if cand not in taken:
                break
        else:                                     # identical rel path is
            cand = f"{cand}_{len(taken)}"         # impossible; belt-and-
        taken.add(cand)                           # braces anyway
        ids[path] = cand
    return ids


def _make_recipe(path: str, asset_id: str, template: dict | None,
                 pattern_map: list[tuple[str, dict]]) -> Recipe:
    raw = None
    base = os.path.basename(path)
    for pattern, preset in pattern_map:           # ordered: first wins
        if fnmatch.fnmatch(base, pattern):
            raw = preset
            break
    if raw is None:
        raw = template
    if raw is None:
        return Recipe(asset_id=asset_id, source_path=os.path.abspath(path))
    raw = copy.deepcopy(raw)
    raw["asset_id"] = asset_id
    raw["source"] = {"path": os.path.abspath(path)}
    return Recipe.from_dict(raw, where=base)
