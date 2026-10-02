# Blue Highway

A highway-sign sans: printed lettering on machines, marquees and labels.

- **Name:** Blue Highway (Regular, Bold, Condensed)
- **Designer:** Ray Larabie, Typodermic Fonts, 1998
- **Licence:** CC0 1.0 Universal -- public domain. The package's own
  `read-this.html` says: "This Typodermic font has been released under CC0 1.0
  Universal, a public-domain dedication. You may use it for personal or
  commercial work without buying a license, paying a fee, or asking
  permission." `LICENSE.txt` beside this file is the CC0 1.0 dedication text.
- **Source:** typodermicfonts.com/public-domain/, `blue-highway.zip`. That
  page separates "that exact public-domain font" from same-named commercial
  families; these files are from the public-domain page and nowhere else.
- **Fetched:** 2026-10-02, with the walker's permission for the download.
  `Blue Highway Rg.otf` 35,744 bytes, sha256 `669c655efdc35c9153d52a8adb0676f3f6ebbb73072d439eb89de83f6b59d283`;
  `Blue Highway Bd.otf` 36,352 bytes, sha256 `a5be69737776727b3c5d239c77686a6387b3aea001e7232a50100d5d53e972f7`;
  `Blue Highway Cd.otf` 35,128 bytes, sha256 `a7bf7a024689b13454e8701ec3c8e3d0567cbd2c67ffb2105d06fc55b379989b`.
  The archive's Display and Linocut cuts are not vendored: nothing sets them.

WHY AN OUTLINE FACE. Every face here before it is a pixel face, set on its
own grid and sampled without filtering. The walker, 2026-10-02: "this looks
like it is made with a 90s GPU ... replace the retro look". A printed
marquee's letter has an outline. Zoo mints these into anti-aliased coverage
tables (`tools/mint_smooth_type.py`, Zoo 1.46.0) because Blender's Python has
no rasteriser.

WHY THIS ONE: a 1998 face in the manner of road-sign lettering -- the plain,
legible sans a 1997 machine's legends and a strip-mall sign were set in --
and CC0, which is the factory's rule (docs/proposals/CC0_FONTS.md).
