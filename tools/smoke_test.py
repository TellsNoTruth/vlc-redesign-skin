"""Run the skin in VLC and check that its controls do what they should.

    python tools/smoke_test.py

For each scenario this builds the skin to open on the layout under test, starts VLC with
--ignore-config (the user's settings are neither read nor changed), clicks controls by
posting mouse messages to the skin's window (the real cursor does not move), and checks
the effect through VLC's HTTP interface or the window's pixels. Each step's screenshot goes
to shots/smoke/ for a look-over. Exits 1 if any check fails. Rebuilds the default skin at
the end.

Click positions follow the layouts in build.py at their default sizes (1280 x 720 player,
391 x 339 mini player, 400 x 496 equalizer); move a control there and update it here.
"""
import base64
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_skin import VLC, print_window, user32, windows_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "shots" / "smoke"
SKIN = ROOT / "dist" / "VLC-Redesign" / "theme.xml"
VIDEO, MUSIC = ROOT / "testmedia" / "test-video.mp4", ROOT / "testmedia" / "untangle.mp3"
PORT, HTTP_PORT, HTTP_PASSWORD = 4252, 4253, "smoke"
BENIGN = ("unable to attach stream_directory", "no XML found in theme", "failed to open font")

# palette colours the checks look for (skinlib/palette.py)
PANEL = {"dark": (0x0F, 0x0F, 0x0F), "light": (0xC2, 0xC1, 0xC1)}
ACCENT = (0xD3, 0x79, 0x18)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  (' + detail + ')' if detail else ''}")


def near(c1, c2, tol=12):
    return all(abs(a - b) <= tol for a, b in zip(c1, c2))


class Vlc:
    """One VLC process running the skin, read through its HTTP interface and driven by
    mouse messages posted to the skin's window."""

    def __init__(self, scenario, media=()):
        self.scenario = scenario
        self.log = SHOTS / f"{scenario}.log"
        self.proc = subprocess.Popen([
            VLC, "--ignore-config", "--no-one-instance", "-I", "skins", f"--skins2-last={SKIN}",
            "--extraintf=rc:http", f"--rc-host=127.0.0.1:{PORT}", "--rc-quiet",
            "--http-host=127.0.0.1", f"--http-port={HTTP_PORT}", f"--http-password={HTTP_PASSWORD}",
            "--no-qt-video-autoresize", "--file-logging", f"--logfile={self.log}", "--log-verbose=2",
            *map(str, media)])
        deadline = time.time() + 15
        while time.time() < deadline and not self.skin_windows():
            time.sleep(0.1)
        while time.time() < deadline and self.status() is None:
            time.sleep(0.2)
        self.step = 0

    # --- VLC's state, from its HTTP interface (the rc text interface interleaves
    #     unprompted "status change" lines with answers and is unreliable to read) ---
    def status(self):
        """state ('playing', 'paused', 'stopped'), position (0-1), volume (256 = 100 %), title."""
        auth = base64.b64encode(f":{HTTP_PASSWORD}".encode()).decode()
        req = urllib.request.Request(f"http://127.0.0.1:{HTTP_PORT}/requests/status.json",
                                     headers={"Authorization": f"Basic {auth}"})
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                s = json.load(r)
        except (OSError, ValueError):
            return None
        meta = s.get("information", {}).get("category", {}).get("meta", {})
        return {"state": s.get("state"), "position": s.get("position", 0), "volume": s.get("volume", -1),
                "title": meta.get("title") or meta.get("filename")}

    def wait(self, predicate, timeout=6):
        """Poll the status until predicate(status) holds; return the last status."""
        deadline = time.time() + timeout
        s = self.status() or {}
        while not predicate(s) and time.time() < deadline:
            time.sleep(0.3)
            s = self.status() or {}
        return s

    # --- windows ----------------------------------------------------------------
    def skin_windows(self):
        """Visible skins2 windows, largest first: (hwnd, (left, top, right, bottom))."""
        wins = [(h, r) for h, cls, r in windows_of(self.proc.pid)
                if cls == "SkinWindowClass" and r[2] - r[0] >= 300 and r[3] - r[1] >= 50]
        return sorted(wins, key=lambda w: -(w[1][2] - w[1][0]) * (w[1][3] - w[1][1]))

    def main(self):
        return self.skin_windows()[0]

    def size(self, win=None):
        _, r = win or self.main()
        return r[2] - r[0], r[3] - r[1]

    def click(self, x, y, win=None, settle=0.8):
        hwnd = (win or self.main())[0]
        lp = (y << 16) | x
        user32.PostMessageW(hwnd, 0x200, 0, lp)        # WM_MOUSEMOVE: skins2 needs the hover first
        time.sleep(0.15)
        user32.PostMessageW(hwnd, 0x201, 1, lp)        # WM_LBUTTONDOWN
        time.sleep(0.05)
        user32.PostMessageW(hwnd, 0x202, 0, lp)        # WM_LBUTTONUP
        user32.PostMessageW(hwnd, 0x200, 0, (2 << 16) | 2)   # move away so hover looks don't linger
        time.sleep(settle)

    def shot(self, label, win=None):
        hwnd, r = win or self.main()
        img = print_window(hwnd, r[2] - r[0], r[3] - r[1])
        self.step += 1
        img.save(SHOTS / f"{self.scenario}-{self.step:02d}-{label}.png")
        return img

    def close(self):
        try:  # quit through rc, so VLC exits cleanly
            with socket.create_connection(("127.0.0.1", PORT), timeout=3) as s:
                s.sendall(b"quit\n")
        except OSError:
            pass
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        lines = self.log.read_text(encoding="utf-8", errors="replace").splitlines() if self.log.exists() else []
        bad = [l for l in lines if l.startswith("skins2") and ("error" in l or "warning" in l)
               and not any(b in l for b in BENIGN)]
        check(f"{self.scenario}: no skins2 errors or warnings in VLC's log", not bad, "; ".join(bad[:3]))


def build(start):
    subprocess.run([sys.executable, str(ROOT / "build.py"), "--start", start], check=True,
                   stdout=subprocess.DEVNULL)


def time_fraction(v):
    time.sleep(.5)
    return (v.status() or {}).get("position", -1)


# --- scenarios ----------------------------------------------------------------------

def full_player():
    print("dark player, video then music queued")
    build("dark_full")
    v = Vlc("full", (VIDEO, MUSIC))
    W, H, bar = 1280, 720, 720 - 54 + 27          # bar centre line
    check("window opens at 1280 x 720", v.size() == (W, H), f"{v.size()}")
    # the first start after a build can be slow; give playback time to begin
    check("video starts", v.wait(lambda s: s.get("state") == "playing" and s.get("position", 0) > 0,
                                 timeout=20).get("state") == "playing")
    v.shot("playing")

    v.click(85, bar)
    check("play/pause button pauses", v.wait(lambda s: s.get("state") == "paused").get("state") == "paused")
    v.click(85, bar)
    check("play/pause button resumes", v.wait(lambda s: s.get("state") == "playing").get("state") == "playing")

    lo, length = 260, W - 694                      # seek handle centre at 0 and its travel
    v.click(lo + round(.75 * length), bar)
    frac = time_fraction(v)
    check("clicking the seek track at 75% seeks there", abs(frac - .75) < .04, f"at {frac:.0%}")
    v.shot("seeked")

    v.click(988 + 22, bar)                         # volume wedge starts at W - 292, 88 wide
    vol = (v.wait(lambda s: abs(s.get("volume", -1) - 128) <= 12, 3)).get("volume", -1)
    check("clicking the volume wedge at 25% sets 50% volume", abs(vol - 128) <= 12, f"volume {vol}/256")
    before = v.shot("volume").crop((W - 327, H - 41, W - 297, H - 13))
    v.click(W - 312, bar)
    after = v.shot("muted").crop((W - 327, H - 41, W - 297, H - 13))
    check("mute button swaps to the muted icon", before.tobytes() != after.tobytes())
    v.click(W - 312, bar)
    unmuted = v.shot("unmuted").crop((W - 327, H - 41, W - 297, H - 13))
    check("pressing it again swaps back", unmuted.tobytes() == before.tobytes())

    title = v.status()["title"]
    v.click(135, bar)
    new = v.wait(lambda s: s.get("title") and s.get("title") != title).get("title")
    check("next button plays the next item", new and new != title, f"{title!r} -> {new!r}")
    time.sleep(1)
    cover = v.shot("music").crop((400, 120, 880, 520))
    # the test cover's rings are purple; nothing of the skin's own is
    px = cover.get_flattened_data()
    purple = sum(1 for r, g, b in px if b > 100 and b > g + 40) / len(px)
    check("music shows its cover", purple > .02, f"{purple:.0%} of the cover area purple")
    v.click(35, bar)
    back = v.wait(lambda s: s.get("title") == title).get("title")
    check("previous button goes back", back == title, f"{back!r}")

    v.click(W - 184 + 15, bar - 2)
    time.sleep(.5)
    wins = v.skin_windows()
    eq = next((w for w in wins if v.size(w) == (400, 496)), None)
    check("audio button opens the equalizer", eq is not None)
    if eq:
        v.shot("eq", eq)
        v.click(270 + 50, 28, eq)                  # the toggle, where its knob goes when on
        knob = v.shot("eq-on", eq).getpixel((270 + 50, 28))
        check("equalizer toggle turns on", near(knob, ACCENT, 20), f"knob {knob}")
        v.click(270 + 50, 28, eq)
        v.click(352 + 18, 28, eq)                  # close
        time.sleep(.5)
        check("equalizer close button hides it", all(v.size(w) != (400, 496) for w in v.skin_windows()))

    v.click(89 + 14, 20)                           # top bar sidebar toggle
    px = v.shot("sidebar").getpixel((300, 600))
    check("sidebar button opens the playlist layout", near(px, PANEL["dark"], 4), f"pixel {px}")
    shuffle_off = v.shot("sidebar").crop((301, 58, 329, 86))
    v.click(315, 72)
    shuffle_on = v.shot("shuffled").crop((301, 58, 329, 86))
    check("shuffle button lights up", shuffle_off.tobytes() != shuffle_on.tobytes()
          and any(near(p, ACCENT, 30) for p in shuffle_on.get_flattened_data()))
    v.click(315, 72)
    states = [v.shot("repeat").crop((339, 58, 367, 86)).tobytes()]
    for _ in range(3):
        v.click(353, 72)
        states.append(v.shot("repeat").crop((339, 58, 367, 86)).tobytes())
    check("repeat cycles off, all, one, off", len(set(states[:3])) == 3 and states[3] == states[0])
    v.click(W - 50 + 15, bar - 2)                  # bar playlist button closes the sidebar
    px = v.shot("closed-sidebar").getpixel((300, 600))
    check("playlist button closes the sidebar", not near(px, PANEL["dark"], 4), f"pixel {px}")

    v.click(W - 114 + 18, 20)                      # maximize
    time.sleep(.5)
    w, h = v.size()
    check("maximize fills the screen's work area", w > W and h > H, f"{w} x {h}")
    v.click(w - 114 + 18, 20)                      # restore, now at the maximized size's position
    time.sleep(.5)
    check("restore returns to the previous size", v.size() == (W, H), f"{v.size()}")
    v.close()


def light_player():
    print("light player, music only")
    build("light_full")
    v = Vlc("light", (MUSIC,))
    check("light player opens", v.size() == (1280, 720), f"{v.size()}")
    v.wait(lambda s: s.get("state") == "playing")
    time.sleep(1)
    img = v.shot("music")
    check("light theme chrome", near(img.getpixel((5, 300)), (0xAB, 0xAB, 0xAB), 4), f"{img.getpixel((5, 300))}")
    v.click(1280 - 42 + 18, 20)                    # close button quits VLC
    try:
        v.proc.wait(timeout=8)
        check("close button quits VLC", True)
    except subprocess.TimeoutExpired:
        check("close button quits VLC", False)
    v.close()


def mini_player():
    print("dark mini player, video")
    build("dark_mini")
    v = Vlc("mini", (VIDEO,))
    check("mini player opens at 391 x 339", v.size() == (391, 339), f"{v.size()}")
    v.wait(lambda s: s.get("state") == "playing")
    v.shot("playing")
    v.click(63, 298)
    check("mini play/pause pauses", v.wait(lambda s: s.get("state") == "paused").get("state") == "paused")
    v.click(12 + round(.75 * 367), 233)
    frac = time_fraction(v)
    check("clicking the mini seek bar at 75% seeks there", abs(frac - .75) < .05, f"at {frac:.0%}")
    v.shot("seeked")
    v.click(336, 298)                              # expand to the full player
    time.sleep(.5)
    check("expand button opens the full player", v.size() == (1280, 720), f"{v.size()}")
    v.shot("expanded")
    v.close()


def light_mini():
    print("light mini player, nothing playing")
    build("light_mini")
    v = Vlc("minilight")
    check("light mini player opens", v.size() == (391, 339), f"{v.size()}")
    v.shot("stopped")
    v.click(304, 298)                              # playlist button: full player with sidebar
    time.sleep(.5)
    px = v.shot("sidebar").getpixel((300, 600))
    check("mini playlist button opens the sidebar layout", v.size() == (1280, 720) and near(px, PANEL["light"], 4),
          f"{v.size()}, pixel {px}")
    v.close()


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    for old in SHOTS.glob("*"):
        old.unlink()
    try:
        for scenario in (full_player, light_player, mini_player, light_mini):
            scenario()
    finally:
        build("dark_full")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed; screenshots in {SHOTS}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
