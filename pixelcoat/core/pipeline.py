"""Pipeline dispatch (Gen7 roadmap, Slice 1).

``build`` is still the one public entry point; it routes a recipe to its
processing graph. ``pixel`` is the original fixed graph, unchanged and
living in pipeline_pixel.py; ``generation_7`` is the layered-material
graph in pipeline_generation_7.py. Recipes without a mode are pixel.
"""

from __future__ import annotations

from ..recipe import Recipe
from . import pipeline_generation_7, pipeline_pixel

# Re-exported: tests and tools may reach for the padding helper here.
from .pipeline_pixel import _pad_extrude  # noqa: F401


def build(recipe: Recipe, out_dir: str) -> dict:
    """Run a recipe. Writes the pack into ``out_dir/<asset_id>/`` and
    returns the build report dict."""
    if recipe.processing_mode == "pixel":
        return pipeline_pixel.build_pixel(recipe, out_dir)
    if recipe.processing_mode == "generation_7":
        return pipeline_generation_7.build_generation_7(recipe, out_dir)
    raise ValueError(
        f"Unsupported processing mode: {recipe.processing_mode}")
