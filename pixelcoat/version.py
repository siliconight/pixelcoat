"""Single source of truth for the Pixelcoat version.

Baked into every recipe, manifest, and build report so output is traceable
to the exact tool revision. Fixed per release, never a timestamp.
"""

__version__ = "0.10.0"

RECIPE_SCHEMA_VERSION = "0.7"

# Matches the Deli Counter / Patina convention: the pipeline's shared
# determinism story.
DEFAULT_SEED = 1999
