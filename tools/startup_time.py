"""Time how long VLC takes to show a skin's main window.

    python tools/startup_time.py dist/VLC-Redesign.vlt "C:/Program Files/VideoLAN/VLC/skins/default.vlt"

Each skin is launched --runs times (with --ignore-config, so the user's settings are
untouched); prints the median seconds from process start to a visible skins2 window.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import socket
import statistics
import subprocess
import time
from pathlib import Path

VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
user32 = ctypes.windll.user32


def skin_window_visible(pid):
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            # skins2 also keeps a small hidden-in-plain-sight helper window of the same class
            if cls.value == "SkinWindowClass" and r.right - r.left >= 300 and r.bottom - r.top >= 100:
                found.append(hwnd)
        return True
    user32.EnumWindows(cb, 0)
    return bool(found)


def once(skin):
    t0 = time.perf_counter()
    p = subprocess.Popen([VLC, "--ignore-config", "--no-one-instance", "-I", "skins",
                          f"--skins2-last={skin}", "--extraintf=rc", "--rc-host=127.0.0.1:4251", "--rc-quiet"])
    try:
        while time.perf_counter() - t0 < 60:
            if skin_window_visible(p.pid):
                return time.perf_counter() - t0
            time.sleep(0.01)
        return float("nan")
    finally:
        time.sleep(0.5)
        try:  # quit cleanly, so VLC deletes the files it unpacked from a .vlt
            with socket.create_connection(("127.0.0.1", 4251), timeout=5) as s:
                s.sendall(b"quit\n")
            p.wait(timeout=10)
        except Exception:
            p.kill()
            p.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("skins", nargs="+")
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    for skin in a.skins:
        path = Path(skin).resolve()
        times = [once(path) for _ in range(a.runs)]
        print(f"{statistics.median(times):6.2f} s  (runs: {', '.join(f'{t:.2f}' for t in times)})  {path}")


if __name__ == "__main__":
    main()
