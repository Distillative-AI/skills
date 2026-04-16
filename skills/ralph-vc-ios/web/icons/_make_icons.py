"""Generate the apple-touch-icon + 512px PWA icon using only stdlib.

Re-run via: `python3 web/icons/_make_icons.py`

Authored by Chase Eddies <source@distillative.ai>.
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path


def png(pixels: bytes, w: int, h: int) -> bytes:
    """Encode a raw RGBA buffer as a valid PNG."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit RGBA
    rows = b""
    stride = w * 4
    for y in range(h):
        rows += b"\x00" + pixels[y * stride : (y + 1) * stride]
    idat = zlib.compress(rows, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def icon(size: int) -> bytes:
    """A simple radial-gradient 'R' badge — distinctive enough on the home screen."""
    cx, cy = size / 2, size / 2
    rmax = size / 2
    out = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            dx, dy = x - cx, y - cy
            d = (dx * dx + dy * dy) ** 0.5 / rmax
            if d > 1:
                r = g = b = a = 0  # transparent corners (maskable will square it)
            else:
                # dark navy → electric blue radial
                t = max(0.0, min(1.0, d))
                r = int(10  + (41 - 10) * (1 - t))
                g = int(10  + (98 - 10) * (1 - t))
                b = int(20  + (255 - 20) * (1 - t))
                a = 255
            i = (y * size + x) * 4
            out[i:i+4] = bytes((r, g, b, a))

    # Stamp a chunky "R" using a 5x7 bitmap font.
    font_R = [
        "11110",
        "10001",
        "10001",
        "11110",
        "10100",
        "10010",
        "10001",
    ]
    fh = len(font_R)
    fw = len(font_R[0])
    cell = max(1, size // 9)
    ox = (size - fw * cell) // 2
    oy = (size - fh * cell) // 2
    for ry, row in enumerate(font_R):
        for rx, ch in enumerate(row):
            if ch != "1":
                continue
            for py in range(cell):
                for px in range(cell):
                    x = ox + rx * cell + px
                    y = oy + ry * cell + py
                    if 0 <= x < size and 0 <= y < size:
                        i = (y * size + x) * 4
                        out[i:i+4] = bytes((255, 255, 255, 255))
    return png(bytes(out), size, size)


def main() -> int:
    here = Path(__file__).resolve().parent
    for size, name in [(180, "icon-180.png"), (512, "icon-512.png")]:
        path = here / name
        path.write_bytes(icon(size))
        print(f"wrote {path} ({size}x{size}, {path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
