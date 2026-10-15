#!/usr/bin/env python3
"""Screenshots of edge cases to look over: the player at its smallest size, a very long title,
and a playlist long enough to scroll. Needs the media from tools/make_testmedia.py.

    python tools/edge_cases.py
"""
import base64
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke_test as T  # noqa: E402
from run_skin import user32  # noqa: E402

LONG = T.ROOT / "testmedia" / "long-title.mp4"
LONG_TITLE = ("An Extremely Long Episode Title That Goes On And On, Part Two of Three "
              "(Director's Cut, Remastered 2026)")

_AUTH_HEADER = {
    "Authorization": "Basic " + base64.b64encode(f":{T.HTTP_PASSWORD}".encode()).decode()
}


def http(v, query):
    url = f"http://127.0.0.1:{T.HTTP_PORT}/requests/status.json?{query}"
    req = urllib.request.Request(url, headers=_AUTH_HEADER)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read()


def enqueue(v, path):
    uri = urllib.parse.quote(Path(path).resolve().as_uri(), safe="")
    http(v, f"command=in_enqueue&input={uri}")


def drag(v, x0, y0, x1, y1):
    """Press at (x0, y0) and release at (x1, y1), window coordinates, by posted messages."""
    hwnd = v.main()[0]
    steps = (
        (0x0200, 0, x0, y0),
        (0x0201, 1, x0, y0),
        (0x0200, 1, (x0 + x1) // 2, (y0 + y1) // 2),
        (0x0200, 1, x1, y1),
        (0x0202, 0, x1, y1),
    )
    for msg, wp, x, y in steps:
        lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
        user32.PostMessageW(hwnd, msg, wp, lparam)
        time.sleep(0.25)
    time.sleep(0.8)


def main():
    for media in (T.VIDEO, T.MUSIC):
        if not Path(media).exists():
            raise SystemExit(f"Missing {media}; run `python tools/make_testmedia.py` first.")

    T.SHOTS.mkdir(parents=True, exist_ok=True)
    if not LONG.exists():
        LONG.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(T.VIDEO), "-c", "copy",
             "-metadata", f"title={LONG_TITLE}", str(LONG)],
            check=True,
        )

    music_query = "command=in_enqueue&input=" + urllib.parse.quote(Path(T.MUSIC).resolve().as_uri(), safe="")
    last_built = None
    try:
        # Run dark_full last so dist/ ends on the default layout without rebuilding it twice
        for start in ("dark_side", "dark_mini", "dark_full"):
            T.build(start)
            last_built = start
            v = T.Vlc(f"edge-{start}", (LONG,))
            try:
                v.wait(lambda s: s.get("state") == "playing" and s.get("position", 0) > 0, 15)
                time.sleep(1.5)                    # let the video window and times appear
                if start == "dark_side":
                    for _ in range(30):
                        http(v, music_query)
                    time.sleep(1)
                w, h = v.size()
                v.shot("default")
                if not start.endswith("mini"):
                    drag(v, w - 6, h - 6, 10, 10)  # the resize corner, dragged far past the minimum
                    print(f"{start}: dragged the corner from {w} x {h}; now {v.size()}")
                    v.shot("smallest")
                    time.sleep(1.2)                # a moment later: a long title scrolls
                    v.shot("smallest-later")
            finally:
                v.close()
    finally:
        if last_built != "dark_full":
            T.build("dark_full")

    print(f"screenshots in {T.SHOTS}")


if __name__ == "__main__":
    main()
