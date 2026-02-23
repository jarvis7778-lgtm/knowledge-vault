#!/usr/bin/env python3
"""Auto-crop an X screenshot to the article/content area.

Heuristic: find bounding box where rows/cols contain enough non-white pixels.
Works well to remove X left sidebar and big whitespace.

Usage:
  python3 crop_screenshot.py in.png out.png
"""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image


def nonwhite(p: tuple[int, int, int], thr: int = 245) -> bool:
    r, g, b = p
    return r < thr or g < thr or b < thr


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: crop_screenshot.py in.png out.png")

    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])

    Image.MAX_IMAGE_PIXELS = None
    img = Image.open(inp).convert("RGB")
    w, h = img.size
    pix = img.load()

    step = 10
    thr_ratio = 0.02

    def col_ratio(x: int) -> float:
        non = 0
        total = 0
        for y in range(0, h, step):
            total += 1
            if nonwhite(pix[x, y]):
                non += 1
        return non / total

    def row_ratio(y: int) -> float:
        non = 0
        total = 0
        for x in range(0, w, step):
            total += 1
            if nonwhite(pix[x, y]):
                non += 1
        return non / total

    left = 0
    for x in range(0, w, step):
        if col_ratio(x) > thr_ratio:
            left = x
            break

    right = w - 1
    for x in range(w - 1, 0, -step):
        if col_ratio(x) > thr_ratio:
            right = x
            break

    top = 0
    for y in range(0, h, step):
        if row_ratio(y) > thr_ratio:
            top = y
            break

    bottom = h - 1
    for y in range(h - 1, 0, -step):
        if row_ratio(y) > thr_ratio:
            bottom = y
            break

    pad = 30
    left = max(0, left - pad)
    right = min(w - 1, right + pad)
    top = max(0, top - pad)
    bottom = min(h - 1, bottom + pad)

    cropped = img.crop((left, top, right + 1, bottom + 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out, optimize=True)


if __name__ == "__main__":
    main()
