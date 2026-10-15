#!/usr/bin/env python3
"""Report the built skin's sprite sheets: size, how much of each is used, memory once decoded.

    python tools/sheet_stats.py [path/to/theme.xml]
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

DEFAULT_THEME = Path(__file__).resolve().parent.parent / "dist" / "VLC-Redesign" / "theme.xml"


def report(theme_path: Path = DEFAULT_THEME) -> None:
    theme_path = Path(theme_path)
    if theme_path.is_dir():
        theme_path = theme_path / "theme.xml"
    if not theme_path.is_file():
        raise SystemExit(f"Missing {theme_path}; run `python build.py` first.")

    skin_dir = theme_path.parent
    root = ET.parse(theme_path).getroot()

    total_disk = 0
    total_bytes = 0
    standalone_count = 0
    standalone_disk = 0
    standalone_bytes = 0

    for bmp in root.iter("Bitmap"):
        sid = bmp.get("id", "")
        rel_file = bmp.get("file", "")
        bmp_path = skin_dir / rel_file
        if not bmp_path.is_file():
            print(f"{sid}: missing file {rel_file}", file=sys.stderr)
            continue

        with Image.open(bmp_path) as im:
            w, h = im.size

        area = w * h
        disk_bytes = bmp_path.stat().st_size
        decoded_bytes = area * 4
        total_disk += disk_bytes
        total_bytes += decoded_bytes

        subs = list(bmp.findall("SubBitmap"))
        if subs:
            used = sum(int(sb.get("width", 0)) * int(sb.get("height", 0)) for sb in subs)
            usage = used / area if area else 0.0
            print(
                f"{sid}: {w}x{h}, {len(subs)} images, {usage:.0%} of the sheet used, "
                f"{disk_bytes / 1024:.1f} KiB on disk, {decoded_bytes / 1e6:.1f} MB decoded"
            )
        else:
            standalone_count += 1
            standalone_disk += disk_bytes
            standalone_bytes += decoded_bytes

    if standalone_count:
        print(
            f"standalone: {standalone_count} bitmap(s), "
            f"{standalone_disk / 1024:.1f} KiB on disk, {standalone_bytes / 1e6:.1f} MB decoded"
        )
    print(f"total: {total_disk / 1024:.1f} KiB on disk, {total_bytes / 1e6:.1f} MB decoded")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("theme", nargs="?", default=str(DEFAULT_THEME),
                    help="path to theme.xml or skin directory (default: dist/VLC-Redesign/theme.xml)")
    args = ap.parse_args()
    report(Path(args.theme))


if __name__ == "__main__":
    main()
