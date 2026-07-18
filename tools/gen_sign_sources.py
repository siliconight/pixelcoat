#!/usr/bin/env python3
"""Generate DELCO signage SOURCE images for Pixelcoat (pixelcoat repo tool).

Six 1990s-strip-mall sign faces, 512x256, bold type on cabinet fields with
simple period ornamentation. These are SOURCES — Pixelcoat's recipes do the
PS1 crush (downsample, palette, dither, emissive split). Deterministic:
same script, same bytes.

Usage:  python tools/gen_sign_sources.py <out_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 512, 256


def _font(size: int) -> ImageFont.FreeTypeFont:
    for cand in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/impact.ttf",
    ):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _center_text(d: ImageDraw.ImageDraw, text: str, cy: int, size: int,
                 fill, stroke, stroke_w: int = 6) -> None:
    f = _font(size)
    l, t, r, b = d.textbbox((0, 0), text, font=f, stroke_width=stroke_w)
    d.text(((W - (r - l)) / 2 - l, cy - (b - t) / 2 - t), text, font=f,
           fill=fill, stroke_fill=stroke, stroke_width=stroke_w)


def _cabinet(bg, border, border_w=14) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), border)
    d = ImageDraw.Draw(img)
    d.rectangle([border_w, border_w, W - border_w, H - border_w], fill=bg)
    return img, d


def sign_deli(out: Path) -> None:
    img, d = _cabinet((248, 240, 214), (128, 24, 24))
    _center_text(d, "GABAGOOL'S", 66, 62, (128, 24, 24), (248, 240, 214), 4)
    _center_text(d, "DELI", 152, 104, (24, 96, 40), (248, 240, 214), 8)
    d.rectangle([40, 212, W - 40, 226], fill=(128, 24, 24))
    _center_text(d, "HOAGIES - COLD CUTS", 236, 24, (60, 50, 40), (248, 240, 214), 2)
    img.save(out / "sign_deli.png")


def sign_pawn(out: Path) -> None:
    img, d = _cabinet((24, 20, 48), (232, 196, 64))
    for i, cx in enumerate((W / 2 - 70, W / 2, W / 2 + 70)):
        d.ellipse([cx - 26, 22, cx + 26, 74], fill=(232, 196, 64),
                  outline=(180, 140, 30), width=4)
    _center_text(d, "PAWN", 138, 96, (232, 196, 64), (24, 20, 48), 8)
    _center_text(d, "CASH 4 GOLD - LOANS", 218, 30, (240, 236, 220), (24, 20, 48), 3)
    img.save(out / "sign_pawn.png")


def sign_auto(out: Path) -> None:
    img, d = _cabinet((188, 40, 32), (240, 236, 224))
    d.polygon([(0, 0), (150, 0), (90, H), (0, H)], fill=(32, 44, 92))
    _center_text(d, "DELCO", 62, 56, (240, 236, 224), (32, 44, 92), 5)
    _center_text(d, "AUTO PARTS", 148, 74, (240, 236, 224), (110, 16, 12), 7)
    _center_text(d, "FOREIGN & DOMESTIC", 222, 26, (255, 220, 90), (110, 16, 12), 3)
    img.save(out / "sign_auto.png")


def sign_open(out: Path) -> None:
    img, d = _cabinet((16, 16, 20), (200, 40, 40))
    _center_text(d, "OPEN", 104, 120, (255, 70, 60), (60, 8, 8), 10)
    _center_text(d, "24 HOURS", 208, 44, (90, 200, 255), (16, 16, 20), 4)
    img.save(out / "sign_open.png")


def sign_beer(out: Path) -> None:
    img, d = _cabinet((14, 30, 22), (240, 220, 120))
    _center_text(d, "COLD", 78, 84, (240, 220, 120), (14, 30, 22), 7)
    _center_text(d, "BEER", 178, 96, (120, 220, 255), (14, 30, 22), 8)
    img.save(out / "sign_beer.png")


def sign_checks(out: Path) -> None:
    img, d = _cabinet((240, 232, 200), (20, 80, 44))
    _center_text(d, "CHECKS CASHED", 84, 52, (20, 80, 44), (240, 232, 200), 5)
    d.rectangle([48, 130, W - 48, 138], fill=(20, 80, 44))
    _center_text(d, "LOTTERY - ATM", 186, 44, (168, 32, 32), (240, 232, 200), 4)
    img.save(out / "sign_checks.png")


ALL = (sign_deli, sign_pawn, sign_auto, sign_open, sign_beer, sign_checks)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "sign_sources")
    out.mkdir(parents=True, exist_ok=True)
    for fn in ALL:
        fn(out)
    print(f"[signage] {len(ALL)} sources -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
