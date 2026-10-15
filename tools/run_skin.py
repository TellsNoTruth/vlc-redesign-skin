#!/usr/bin/env python3
"""Launch VLC with the built skin, optionally play something, screenshot VLC's windows, quit.

    python tools/run_skin.py --media testmedia/test-video.mp4 --wait 5 --out shots/video
    python tools/run_skin.py --rc "seek 40" "volume 400" --out shots/seek

VLC runs with --ignore-config, so the user's own VLC settings are neither read nor
changed. Playback is driven through VLC's rc interface on 127.0.0.1:4250, not the mouse.
Windows are captured with PrintWindow, which renders only VLC's own window: never grab
the screen, which would capture whatever happens to be in front of it.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import socket
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
RC_PORT = 4250

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()
for f in (user32.GetWindowDC, gdi32.CreateCompatibleDC, gdi32.CreateCompatibleBitmap, gdi32.SelectObject):
    f.restype = ctypes.c_void_p
user32.GetWindowDC.argtypes = [wt.HWND]
user32.PrintWindow.argtypes = [wt.HWND, ctypes.c_void_p, wt.UINT]
user32.PrintWindow.restype = wt.BOOL
user32.ReleaseDC.argtypes = [wt.HWND, ctypes.c_void_p]
user32.ReleaseDC.restype = ctypes.c_int
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL
user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetWindowRect.restype = wt.BOOL
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.GetDIBits.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, wt.UINT, wt.UINT,
    ctypes.c_void_p, ctypes.c_void_p, wt.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteObject.restype = wt.BOOL
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.restype = wt.BOOL


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


def print_window(hwnd, w, h):
    """The window's own pixels, even when other windows cover it (PW_RENDERFULLCONTENT)."""
    if w <= 0 or h <= 0:
        return None
    wdc = user32.GetWindowDC(hwnd)
    if not wdc:
        return None
    dc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, w, h) if dc else None
    old = gdi32.SelectObject(dc, bmp) if bmp else None
    try:
        if not bmp or not user32.PrintWindow(hwnd, dc, 2):
            return None
        # Deselect bmp from dc before calling GetDIBits and DeleteObject (required by MSDN)
        gdi32.SelectObject(dc, old)
        old = None
        hdr = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(dc, bmp, 0, h, buf, ctypes.byref(hdr), 0):
            return None
        return Image.frombytes("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1)
    finally:
        if old and dc:
            gdi32.SelectObject(dc, old)
        if bmp:
            gdi32.DeleteObject(bmp)
        if dc:
            gdi32.DeleteDC(dc)
        user32.ReleaseDC(hwnd, wdc)


def post_mouse(pid, events):
    """Post mouse messages to the largest VLC window, so hover and click states can be
    captured without moving the user's cursor."""
    WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
    wins = windows_of(pid)
    if not wins:
        raise RuntimeError(f"No visible VLC windows found for PID {pid}")
    hwnd = wins[0][0]
    for ev in events:
        kind, xy = ev.split(":", 1)
        x, y = (int(v) for v in xy.split(",", 1))
        lp = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
        time.sleep(0.15)
        if kind == "click":
            user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)
            time.sleep(0.05)
            user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)
            time.sleep(0.3)
        elif kind != "move":
            raise ValueError(f"Unknown mouse event kind {kind!r} in {ev!r}; expected 'move' or 'click'")


def windows_of(pid):
    """Return visible windows belonging to `pid`, sorted largest-first by area."""
    found = []

    @WNDENUMPROC
    def cb(hwnd, _):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left > 40 and r.bottom - r.top > 20:
                cls = ctypes.create_unicode_buffer(128)
                user32.GetClassNameW(hwnd, cls, 128)
                found.append((hwnd, cls.value, (r.left, r.top, r.right, r.bottom)))
        return True

    user32.EnumWindows(cb, 0)
    found.sort(key=lambda w: -((w[2][2] - w[2][0]) * (w[2][3] - w[2][1])))
    return found


def rc(*commands):
    if not commands:
        return
    with socket.create_connection(("127.0.0.1", RC_PORT), timeout=5) as s:
        for i, c in enumerate(commands):
            s.sendall((c + "\n").encode("utf-8"))
            if c.strip() == "quit":
                return
            if i + 1 < len(commands):
                time.sleep(0.6)
        time.sleep(0.6)
        s.sendall(b"logout\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skin", default=str(ROOT / "dist" / "VLC-Redesign" / "theme.xml"))
    ap.add_argument("--media", nargs="*", default=[])
    ap.add_argument("--wait", type=float, default=4)
    ap.add_argument("--rc", nargs="*", default=[], help="rc commands sent after the wait")
    ap.add_argument("--after", type=float, default=1.5, help="seconds between rc commands and the capture")
    ap.add_argument("--out", default="shots/run")
    ap.add_argument("--keep", action="store_true", help="leave VLC running")
    ap.add_argument("--extra", nargs="*", default=[], help="extra VLC arguments")
    ap.add_argument("--mouse", nargs="*", default=[],
                    help="mouse events posted to the main window before the capture, e.g. move:60,20 "
                         "click:120,215 (window coordinates; the real cursor is not moved)")
    a = ap.parse_args()

    out = Path(a.out) if Path(a.out).is_absolute() else ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    log = out.with_suffix(".log")
    log.unlink(missing_ok=True)

    skin = Path(a.skin).resolve()
    media_paths = [str(Path(m).resolve() if Path(m).exists() else (ROOT / m).resolve()) for m in a.media]
    args = [
        VLC, "--ignore-config", "--no-one-instance", "-I", "skins", f"--skins2-last={skin}",
        "--extraintf=rc", f"--rc-host=127.0.0.1:{RC_PORT}", "--rc-quiet",
        "--file-logging", f"--logfile={log}", "--log-verbose=2", "--no-qt-video-autoresize",
        *a.extra, *media_paths,
    ]
    proc = subprocess.Popen(args)
    try:
        time.sleep(a.wait)
        if a.rc:
            rc(*a.rc)
            time.sleep(a.after)
        if a.mouse:
            post_mouse(proc.pid, a.mouse)
            time.sleep(0.8)
        wins = windows_of(proc.pid)
        if not wins:
            print("no VLC windows found", file=sys.stderr)
        for i, (hwnd, cls, rect) in enumerate(wins):
            path = out.with_name(f"{out.name}-{i}.png")
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            img = print_window(hwnd, w, h)
            if img is None:
                print(f"PrintWindow failed for {cls}", file=sys.stderr)
                continue
            img.save(path)
            print(f"{path}  {cls}  {w}x{h} at {rect[0]},{rect[1]}")
    finally:
        if not a.keep:
            try:
                rc("quit")
                proc.wait(timeout=8)
            except Exception:
                proc.kill()
                proc.wait(timeout=5)
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        bad = [l for l in lines if "skins2" in l and ("error" in l or "warning" in l)]
        print(f"{log}: {len(lines)} lines, {len(bad)} skins2 warnings/errors")
        for l in bad[:40]:
            print("  ", l)


if __name__ == "__main__":
    main()
