"""Rebuild the admin header/sidebar logo asset from the master artwork.

Why the asset is not just a resize
----------------------------------
``kinjo-logo.png`` is 1254x1254 with roughly 19% blank margin baked into every side,
so the mark itself only occupies about 81% of the canvas. ``object-fit: contain``
honours that whitespace, which means the logo rendered small inside the header badge
no matter what the CSS said — shrinking the badge's padding could never recover it.

This script crops the artwork to its own content, squared on the content's centre so
the 1:1 ratio ``object-fit: contain`` relies on survives, then resizes and quantises.
A small breathing margin is kept so the mark never touches the badge's inner gold ring.

Quantisation is deliberate: at 256 colours the mean absolute error against the true
full-colour downscale is under 0.3/255 — invisible at the 54px the header draws it —
while the file stays roughly 40% smaller than an RGBA PNG.

Usage
-----
    python scripts/build_logo_asset.py [--check]

``--check`` reports what would change and writes nothing.
"""

from __future__ import annotations

import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SOURCE = os.path.join("static", "img", "kinjo-logo.png")
TARGET = os.path.join("static", "img", "kinjo-logo-mark-320.png")
SIZE = 320
COLOURS = 256
BREATHING = 0.04  # margin kept around the mark, as a fraction of its own size
ALPHA_TOLERANCE = 12  # how far a pixel must differ from the background to count as ink


def build() -> bytes:
    from PIL import Image, ImageChops

    img = Image.open(SOURCE).convert("RGB")
    background = img.getpixel((0, 0))

    flat = Image.new("RGB", img.size, background)
    ink = (
        ImageChops.difference(img, flat)
        .convert("L")
        .point(lambda p: 255 if p > ALPHA_TOLERANCE else 0)
    )
    bbox = ink.getbbox()
    if bbox is None:
        raise SystemExit(f"{SOURCE} appears to be a single flat colour")

    left, top, right, bottom = bbox
    side = int(max(right - left, bottom - top) * (1 + 2 * BREATHING))
    cx, cy = (left + right) / 2, (top + bottom) / 2
    crop = (
        round(cx - side / 2),
        round(cy - side / 2),
        round(cx + side / 2),
        round(cy + side / 2),
    )

    # Paste onto a background-coloured canvas so a crop that reaches past the source
    # edge is filled with the logo's own background rather than black.
    canvas = Image.new("RGB", (side, side), background)
    canvas.paste(img.crop(crop), (0, 0))

    resized = canvas.resize((SIZE, SIZE), Image.LANCZOS)
    quantised = resized.quantize(
        colors=COLOURS, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG
    )

    buffer = io.BytesIO()
    quantised.save(buffer, "PNG", optimize=True)

    fill = (right - left) / img.size[0]
    print(f"source          : {SOURCE} {img.size}")
    print(f"content bbox    : {bbox} — mark fills {fill:.1%} of the source canvas")
    print(f"square crop     : {crop} ({side}px)")
    print(f"output          : {SIZE}x{SIZE}, {COLOURS} colours, "
          f"{len(buffer.getvalue()) / 1024:.1f} KB")
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Report only; do not write the asset"
    )
    args = parser.parse_args()

    if not os.path.exists(SOURCE):
        print(f"source not found: {SOURCE}")
        return 1

    data = build()

    existing = None
    if os.path.exists(TARGET):
        with open(TARGET, "rb") as fh:
            existing = fh.read()

    if existing == data:
        print(f"\n{TARGET} is already up to date.")
        return 0

    if args.check:
        current = f"{len(existing) / 1024:.1f} KB" if existing else "absent"
        print(f"\nCHECK ONLY — {TARGET} would change (currently {current}).")
        return 0

    with open(TARGET, "wb") as fh:
        fh.write(data)
    print(f"\nwritten: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
