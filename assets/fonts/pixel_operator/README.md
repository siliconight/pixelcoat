# Pixel Operator

The typeface this pipeline sets text in: signs, price boards, labels.

- **Name:** Pixel Operator (previously 8-bit Operator)
- **Designer:** Jayvee Enaguas (HarvettFox96)
- **Licence:** CC0 1.0 Universal -- public domain. No attribution is
  required and none is claimed; `LICENSE.txt` beside these files is the
  dedication as it shipped.
- **Source:** Font Library (fontlibrary.org/en/font/pixel-operator);
  the designer's own source repository is notabug.org/HarvettFox96/ttf-pixeloperator.
- **Fetched:** 2026-09-13, from the Font Library archive
  `pixel-operator.zip` (106,431 bytes, CC-0 as stated on the catalogue
  page and in the bundled LICENSE.txt).

WHY THIS ONE. It had to be CC0 rather than merely free: a licence that
asks for attribution puts a condition on every level this factory ships,
and the deliverable is a pipeline somebody else points at their own game.
It had to be sans serif and it had to be a PIXEL face -- Pixelcoat renders
at nearest-neighbour and a sign is read at a texel scale, so a typeface
drawn on a grid stays crisp where an outline face goes soft. Pixel
Operator is drawn for 16 px (and `PixelOperator8` for 8 px), so text set
at an exact multiple of its grid lands on whole pixels.

WHAT REPLACED WHAT. `core/signage.py` carried a hand-typed 5x7 bitmap of
38 glyphs, which is what drew every sign through 2026-09-13. The walker,
that day: "the fonts are lazy for now". It stays as the fallback for a
build with no font file present, and nothing else uses it.
