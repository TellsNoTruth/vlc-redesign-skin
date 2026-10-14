"""Create the media tools/smoke_test.py plays: a 90 s test-pattern video and a 2 min MP3
with an embedded cover. Needs ffmpeg on PATH.

    python tools/make_testmedia.py
"""
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "testmedia"


def main():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is not on PATH")
    OUT.mkdir(exist_ok=True)

    # a cover of purple rings; smoke_test.py looks for its purple
    s = 600
    cover = Image.new("RGB", (s, s), (8, 8, 10))
    d = ImageDraw.Draw(cover)
    for i, r in enumerate(range(280, 20, -26)):
        d.ellipse((s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r), outline=(40 + i * 18, 30 + i * 9, 90 + i * 14), width=6)
    cover.save(OUT / "cover.png")

    run = lambda *args: subprocess.run([ffmpeg, "-v", "error", "-y", *args], check=True)
    run("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
        "-t", "90", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-metadata", "title=Test Pattern",
        str(OUT / "test-video.mp4"))
    run("-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-i", str(OUT / "cover.png"), "-t", "120",
        "-map", "0:a", "-map", "1:v", "-c:a", "libmp3lame", "-b:a", "128k", "-c:v", "png", "-disposition:v", "attached_pic",
        "-id3v2_version", "3", "-metadata", "title=untangle", "-metadata", "artist=juxtopposed", str(OUT / "untangle.mp3"))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
