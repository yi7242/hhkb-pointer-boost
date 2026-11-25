#!/usr/bin/env python3
"""Generate the app icons without Pillow.

- windows/hhkb_pointer_boost.ico (32-bit color, multi-size)
- mac/AppIcon.png (1024 px, converted to .icns by mac/build.sh)

The macOS menu bar icon is drawn in mac/main.swift from the same rectangles;
keep both in sync when changing the design.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUTPUT = REPO / "windows" / "hhkb_pointer_boost.ico"
MAC_OUTPUT = REPO / "mac" / "AppIcon.png"
MAC_SIZE = 1024
SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
SUPERSAMPLE = 4
MAC_SUPERSAMPLE = 2

BACKGROUND = (0x33, 0x36, 0x3B)  # HHKB charcoal
GLYPH = (0xFF, 0xFF, 0xFF)
ACCENT = (0xFF, 0xB3, 0x00)

# Shapes in unit coordinates (0..1, y grows downward).
H_RECTS = (
    (0.15, 0.22, 0.30, 0.78),  # left stem
    (0.46, 0.22, 0.61, 0.78),  # right stem
    (0.15, 0.43, 0.61, 0.57),  # crossbar
)
PLUS_RECTS = (
    (0.73, 0.36, 0.85, 0.64),  # vertical
    (0.65, 0.44, 0.93, 0.56),  # horizontal
)
BG_INSET = 0.03
BG_RADIUS = 0.22


def in_rects(x: float, y: float, rects) -> bool:
    return any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in rects)


def in_background(x: float, y: float) -> bool:
    lo, hi, r = BG_INSET, 1 - BG_INSET, BG_RADIUS
    if not (lo <= x < hi and lo <= y < hi):
        return False
    cx = min(max(x, lo + r), hi - r)
    cy = min(max(y, lo + r), hi - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def render(size: int, n: int = SUPERSAMPLE) -> bytes:
    """Return top-down BGRA pixels, sampling n x n points per pixel."""
    out = bytearray()
    for py in range(size):
        for px in range(size):
            r = g = b = a = 0.0
            for sy in range(n):
                for sx in range(n):
                    x = (px + (sx + 0.5) / n) / size
                    y = (py + (sy + 0.5) / n) / size
                    if not in_background(x, y):
                        continue
                    if in_rects(x, y, H_RECTS):
                        color = GLYPH
                    elif in_rects(x, y, PLUS_RECTS):
                        color = ACCENT
                    else:
                        color = BACKGROUND
                    r += color[0]
                    g += color[1]
                    b += color[2]
                    a += 1
            if a:
                out += bytes((round(b / a), round(g / a), round(r / a), round(255 * a / n**2)))
            else:
                out += b"\0\0\0\0"
    return bytes(out)


def bmp_entry(size: int, bgra: bytes) -> bytes:
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    row = size * 4
    pixels = b"".join(bgra[y * row:(y + 1) * row] for y in reversed(range(size)))
    mask_row = ((size + 31) // 32) * 4
    return header + pixels + bytes(mask_row * size)


def png_entry(size: int, bgra: bytes) -> bytes:
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            b, g, r, a = bgra[(y * size + x) * 4:(y * size + x) * 4 + 4]
            raw += bytes((r, g, b, a))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    images = []
    for size in SIZES:
        bgra = render(size)
        images.append((size, png_entry(size, bgra) if size >= 256 else bmp_entry(size, bgra)))

    offset = 6 + 16 * len(images)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    for size, data in images:
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    OUTPUT.write_bytes(bytes(directory) + b"".join(data for _, data in images))
    print(f"wrote {OUTPUT}")

    MAC_OUTPUT.write_bytes(png_entry(MAC_SIZE, render(MAC_SIZE, MAC_SUPERSAMPLE)))
    print(f"wrote {MAC_OUTPUT}")


if __name__ == "__main__":
    main()
