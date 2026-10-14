"""Static checks of a built theme.xml, run by build.py after every build.

    python tools/check_theme.py [path/to/theme.xml]

skins2 skips what it does not understand: an unknown action or variable becomes a
warning in VLC's log and the control silently does nothing. This catches those mistakes
before VLC runs: every image, font, action, variable and text token must be one skins2
knows (the lists below come from VLC 3.0's modules/gui/skins2 sources), and every control
must lie inside its layout.
"""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

# parser/interpreter.cpp: the commands registered by name
COMMANDS = {
    "none", "dialogs.changeSkin()", "dialogs.fileSimple()", "dialogs.file()", "dialogs.directory()",
    "dialogs.disc()", "dialogs.net()", "dialogs.playlist()", "dialogs.messages()", "dialogs.prefs()",
    "dialogs.fileInfo()", "dialogs.streamingWizard()", "dialogs.popup()", "dialogs.audioPopup()",
    "dialogs.videoPopup()", "dialogs.miscPopup()", "dvd.nextTitle()", "dvd.previousTitle()",
    "dvd.nextChapter()", "dvd.previousChapter()", "dvd.rootMenu()", "playlist.load()", "playlist.save()",
    "playlist.add()", "playlist.next()", "playlist.previous()", "playlist.setRandom(true)",
    "playlist.setRandom(false)", "playlist.setLoop(true)", "playlist.setLoop(false)",
    "playlist.setRepeat(true)", "playlist.setRepeat(false)", "playlist.del()", "playtree.del()",
    "playlist.sort()", "playtree.sort()", "vlc.fullscreen()", "vlc.play()", "vlc.pause()", "vlc.stop()",
    "vlc.faster()", "vlc.slower()", "vlc.mute()", "vlc.volumeUp()", "vlc.volumeDown()", "vlc.minimize()",
    "vlc.onTop()", "vlc.snapshot()", "vlc.toggleRecord()", "vlc.nextFrame()", "vlc.quit()",
    "equalizer.enable()", "equalizer.disable()",
}
# src/vlcproc.cpp and the window manager: boolean variables
BOOLS = {
    "true", "false", "playlist.isRandom", "playlist.isLoop", "playlist.isRepeat", "playtree.isRandom",
    "playtree.isLoop", "playtree.isRepeat", "vlc.isPlaying", "vlc.isStopped", "vlc.isPaused",
    "vlc.isSeekable", "dvd.isActive", "vlc.canRecord", "vlc.isRecording", "vlc.isFullscreen",
    "vlc.hasVout", "vlc.hasAudio", "vlc.isMute", "equalizer.isEnabled", "vlc.isOnTop",
}
PERCENTS = {"time", "volume", "equalizer.preamp", "playtree.slider", *(f"equalizer.band({i})" for i in range(10))}
TOKENS = set("HTtLlDdVNFBSR")          # utils/var_text.cpp: $H $T $t ...
IMAGE_ACTIONS = {"none", "move", "resizeE", "resizeS", "resizeSE"}   # an Image's `action`
IMAGE_ATTRS = ("image", "up", "down", "over", "up1", "down1", "over1", "up2", "down2", "over2",
               "bgimage", "itemimage", "openimage", "closedimage")


# VLC's own definition of the format; VideoLAN's skin guide says a skin that breaks it may
# not load. Checked when VLC is installed in the usual place.
VLC_DTD = Path(r"C:\Program Files\VideoLAN\VLC\skins\skin.dtd")


def dtd_problems(root, dtd_path=VLC_DTD, theme_path=None):
    """Validate against VLC's DTD. With lxml this is full validation (element order and
    counts included); without it, a smaller check: every element declared, inside a parent
    that allows it, with only declared attributes and all the #REQUIRED ones."""
    if not dtd_path.exists():
        return []
    try:
        from lxml import etree
    except ImportError:
        etree = None
    if etree and theme_path:
        dtd = etree.DTD(str(dtd_path))
        if dtd.validate(etree.parse(str(theme_path))):
            return []
        return sorted({f"DTD: line {e.line}: {e.message}" for e in dtd.error_log.filter_from_errors()})
    text = re.sub(r"<!--.*?-->", "", dtd_path.read_text(encoding="utf-8"), flags=re.S)
    children = {name: set(re.findall(r"[A-Za-z]\w*", spec)) - {"EMPTY"}
                for name, spec in re.findall(r"<!ELEMENT\s+(\w+)\s+(.*?)>", text, re.S)}
    attrs = {name: dict(re.findall(r'(\w+)\s+CDATA\s+(#REQUIRED|#IMPLIED|"[^"]*")', body))
             for name, body in re.findall(r"<!ATTLIST\s+(\w+)(.*?)>", text, re.S)}
    problems = []
    for parent in root.iter():
        for el in parent:
            if el.tag not in children.get(parent.tag, ()):
                problems.append(f"DTD: <{el.tag}> is not allowed inside <{parent.tag}>")
    for el in root.iter():
        declared = attrs.get(el.tag, {})
        where = f"DTD: <{el.tag} id={el.get('id')!r}>"
        for a in el.attrib:
            if a not in declared:
                problems.append(f"{where} has undeclared attribute {a}")
        for a, default in declared.items():
            if default == "#REQUIRED" and a not in el.attrib:
                problems.append(f"{where} lacks required attribute {a}")
    return sorted(set(problems))


def check(theme_path):
    theme_path = Path(theme_path)
    root = ET.parse(theme_path).getroot()
    errors = dtd_problems(root, theme_path=theme_path)
    err = errors.append

    # ids skins2 keeps in one map per kind must be unique across the whole theme
    seen = {}
    for el in root.iter():
        kind = {"Bitmap": "bitmap", "SubBitmap": "bitmap", "Font": "font", "Window": "window",
                "Layout": "layout", "PopupMenu": "popup"}.get(el.tag, "control")
        if el.get("id") and el.tag not in ("ThemeInfo", "SliderBackground"):
            key = (kind, el.get("id"))
            if key in seen:
                err(f"{kind} id {el.get('id')} is used twice")
            seen[key] = el

    bitmaps = {}
    for b in root.iter("Bitmap"):
        sheet = Image.open(theme_path.parent / b.get("file"))
        bitmaps[b.get("id")] = sheet.size
        for sb in b.iter("SubBitmap"):
            x, y, w, h = (int(sb.get(k)) for k in ("x", "y", "width", "height"))
            if x + w > sheet.width or y + h > sheet.height:
                err(f"SubBitmap {sb.get('id')} lies outside {b.get('file')}")
            if sb.get("id") in bitmaps:
                err(f"bitmap id {sb.get('id')} defined twice")
            bitmaps[sb.get("id")] = (w, h)
    fonts = {f.get("id") for f in root.iter("Font")}
    for f in root.iter("Font"):
        if not (theme_path.parent / f.get("file")).exists():
            err(f"font {f.get('id')}: missing file {f.get('file')}")
    popups = {p.get("id") for p in root.iter("PopupMenu")}
    windows = {w.get("id"): {l.get("id") for l in w.iter("Layout")} for w in root.iter("Window")}
    layouts = {l for ls in windows.values() for l in ls}
    bools = BOOLS | {f"{w}.isVisible" for w in windows} | {f"{w}.isMaximized" for w in windows} \
        | {f"{l}.isActive" for l in layouts}

    def action_ok(action):
        for part in (p.strip() for p in action.split(";")):
            if part in COMMANDS:
                continue
            m = re.fullmatch(r"(\w+)\.(show|hide|maximize|unmaximize)\(\)", part)
            if m and (m.group(1) in windows or (m.group(2) == "show" and m.group(1) in popups)):
                continue
            m = re.fullmatch(r"(\w+)\.setLayout\((\w+)\)", part)
            if m and m.group(1) in windows and m.group(2) in windows[m.group(1)]:
                continue
            return False
        return True

    def bool_ok(expr):
        return all(w in ("and", "or", "not") or w in bools for w in expr.split())

    for win in root.iter("Window"):
        for layout in win.iter("Layout"):
            lw, lh = int(layout.get("width")), int(layout.get("height"))
            ids = set()
            for el in layout.iter():
                if el is layout:
                    continue
                where = f"{layout.get('id')}/{el.tag} {el.get('id')}"
                if el.get("id") in ids:
                    err(f"{where}: id used twice in the layout")
                ids.add(el.get("id"))
                for attr in IMAGE_ATTRS:
                    v = el.get(attr)
                    if v and v != "none" and v not in bitmaps:
                        err(f"{where}: {attr}={v} is not a bitmap")
                if el.get("font") and el.get("font") not in fonts:
                    err(f"{where}: unknown font {el.get('font')}")
                for attr in ("visible", "state"):
                    if el.get(attr) and not bool_ok(el.get(attr)):
                        err(f"{where}: {attr}='{el.get(attr)}' uses an unknown variable")
                if el.tag == "Image":
                    if el.get("action", "none") not in IMAGE_ACTIONS:
                        err(f"{where}: an Image's action can only be {sorted(IMAGE_ACTIONS)}")
                    if el.get("action2") and not action_ok(el.get("action2")):
                        err(f"{where}: unknown action2 '{el.get('action2')}'")
                else:
                    for attr in ("action", "action1", "action2"):
                        if el.get(attr) and not action_ok(el.get(attr)):
                            err(f"{where}: unknown {attr} '{el.get(attr)}'")
                if el.tag == "Slider" and el.get("value") and el.get("value") not in PERCENTS:
                    err(f"{where}: unknown slider value '{el.get('value')}'")
                if el.tag == "SliderBackground":
                    w, h = bitmaps.get(el.get("image"), (0, 0))
                    if w % int(el.get("nbhoriz")) or h % int(el.get("nbvert")):
                        err(f"{where}: {w}x{h} frames do not divide into {el.get('nbhoriz')} x {el.get('nbvert')}")
                for tok in re.findall(r"\$(.)", el.get("text", "") + el.get("tooltiptext", "")):
                    if tok not in TOKENS:
                        err(f"{where}: unknown text token ${tok}")
                # the control's default rectangle must lie inside the layout
                if el.tag in ("Image", "Button", "Checkbox", "Text", "Video", "Playtree") \
                        and el.get("x") and not _inside_panel(layout, el):
                    x, y = int(el.get("x")), int(el.get("y"))
                    w = int(el.get("width") or 0) or bitmaps.get(el.get("image") or el.get("up") or el.get("up1"), (0, 0))[0]
                    h = int(el.get("height") or 0) or bitmaps.get(el.get("image") or el.get("up") or el.get("up1"), (0, 0))[1]
                    if x < 0 or y < 0 or x + w > lw or y + h > lh:
                        err(f"{where}: {w}x{h} at {x},{y} falls outside the {lw}x{lh} layout")
    for item in root.iter("MenuItem"):
        if not action_ok(item.get("action")):
            err(f"menu item '{item.get('label')}': unknown action '{item.get('action')}'")
    return errors


def _inside_panel(layout, el):
    """Controls in a Panel are positioned relative to it, so the layout bounds check skips them."""
    return any(el in list(p.iter()) and el is not p for p in layout.iter("Panel"))


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "dist/VLC-Redesign/theme.xml"
    problems = check(path)
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
