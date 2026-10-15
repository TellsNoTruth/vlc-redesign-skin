#!/usr/bin/env python3
"""Create the media tools/smoke_test.py plays: a 90 s test-pattern video and a 2 min MP3
with an embedded cover. Needs ffmpeg on PATH.

    python tools/make_testmedia.py
"""
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "testmedia"


def make_cover(path: Path, size: int = 600) -> None:
    """Draw a cover of purple rings; smoke_test.py looks for its purple."""
    c = size // 2
    cover = Image.new("RGB", (size, size), (8, 8, 10))
    d = ImageDraw.Draw(cover)
    for i, r in enumerate(range(280, 20, -26)):
        color = (40 + i * 18, 30 + i * 9, 90 + i * 14)
        d.ellipse((c - r, c - r, c + r, c + r), outline=color, width=6)
    cover.save(path, format="PNG", optimize=True)


def main():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is not on PATH")
    OUT.mkdir(parents=True, exist_ok=True)

    cover_path = OUT / "cover.png"
    video_path = OUT / "test-video.mp4"
    music_path = OUT / "untangle.mp3"

    make_cover(cover_path)

    jobs = (
        (
            video_path,
            [
                ffmpeg, "-hide_banner", "-v", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=90",
                "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=90",
                "-t", "90",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-movflags", "+faststart",
                "-metadata", "title=Test Pattern",
                str(video_path),
            ],
        ),
        (
            music_path,
            [
                ffmpeg, "-hide_banner", "-v", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100:duration=120",
                "-i", str(cover_path),
                "-t", "120",
                "-map", "0:a", "-map", "1:v",
                "-c:a", "libmp3lame", "-b:a", "128k",
                "-c:v", "copy", "-disposition:v", "attached_pic",
                "-id3v2_version", "3",
                "-metadata:s:v", "title=Album cover",
                "-metadata:s:v", "comment=Cover (front)",
                "-metadata", "title=untangle",
                "-metadata", "artist=juxtopposed",
                str(music_path),
            ],
        ),
    )

    procs = [(target, cmd, subprocess.Popen(cmd)) for target, cmd in jobs]
    try:
        for target, cmd, proc in procs:
            rc = proc.wait()
            if rc != 0:
                target.unlink(missing_ok=True)
                raise subprocess.CalledProcessError(rc, cmd)
    except BaseException:
        for target, _, proc in procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
                target.unlink(missing_ok=True)
        raise

    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
