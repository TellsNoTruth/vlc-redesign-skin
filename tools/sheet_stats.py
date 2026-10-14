"""Report the built skin's sprite sheets: size, how much of each is used, memory once decoded.

    python tools/sheet_stats.py
"""
import re
from pathlib import Path

from PIL import Image

SKIN = Path(__file__).resolve().parent.parent / "dist" / "VLC-Redesign"

xml = (SKIN / "theme.xml").read_text(encoding="utf-8")
for sid, f, body in re.findall(r'<Bitmap id="(sheet\d+)" file="([^"]+)"[^>]*>(.*?)</Bitmap>', xml, re.S):
    im = Image.open(SKIN / f)
    w, h = im.size
    used = sum(int(a) * int(b) for a, b in re.findall(r'width="(\d+)" height="(\d+)"', body))
    print(f"{sid}: {w}x{h}, {body.count('<SubBitmap')} images, {used / (w * h):.0%} of the sheet used, "
          f"{(SKIN / f).stat().st_size // 1024} KiB on disk, {w * h * 4 / 1e6:.1f} MB decoded")
