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
TOKENS = set("HTtLlDdVNFBSR$")          # utils/var_text.cpp: $H$T $t ... ($$escapes$)
IMAGE_ACTIONS = {"none", "move", "resizeE", "resizeS", "resizeSE"}   # an Image's `action`
IMAGE_ATTRS = ("image", "up", "down", "over", "up1", "down1", "over1", "up2", "down2", "over2",
               "bgimage", "itemimage", "openimage", "closedimage")
BOUNDED_CONTROLS = {"Image", "Button", "Checkbox", "Text", "Video", "Playtree"}

# VLC's own definition of the format; VideoLAN's skin guide says a skin that breaks it may
# not load. Checked when VLC is installed in the usual place on Windows or Linux.
_DTD_CANDIDATES = (
    Path(r"C:\Program Files\VideoLAN\VLC\skins\skin.dtd"),
    Path(r"C:\Program Files (x86)\VideoLAN\VLC\skins\skin.dtd"),
    Path("/usr/share/vlc/skins2/skin.dtd"),
    Path("/usr/local/share/vlc/skins2/skin.dtd"),
)
VLC_DTD = next((p for p in _DTD_CANDIDATES if p.exists()), _DTD_CANDIDATES[0])


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
    children = {name: set(re.findall(r"[A-Za-z]\w*", spec)) - {"EMPTY", "PCDATA", "ANY"}
                for name, spec in re.findall(r"<!ELEMENT\s+(\w+)\s+(.*?)>", text, re.S)}
    attrs = {}
    for name, body in re.findall(r"<!ATTLIST\s+(\w+)(.*?)>", text, re.S):
        el_attrs = attrs.setdefault(name, {})
        for attr, default in re.findall(
            r'(\w+)\s+(?:CDATA|ID|IDREF|IDREFS|\([^)]*\))\s+(#REQUIRED|#IMPLIED|(?:#FIXED\s+)?"[^"]*"|(?:#FIXED\s+)?\'[^\']*\')',
            body,
        ):
            el_attrs[attr] = default

    problems = set()
    for el in root.iter():
        allowed_children = children.get(el.tag, ())
        for child in el:
            if child.tag not in allowed_children:
                problems.add(f"DTD: <{child.tag}> is not allowed inside <{el.tag}>")
        declared = attrs.get(el.tag, {})
        where = f"DTD: <{el.tag} id={el.get('id')!r}>"
        for a in el.attrib:
            if a not in declared:
                problems.add(f"{where} has undeclared attribute {a}")
        for a, default in declared.items():
            if default == "#REQUIRED" and a not in el.attrib:
                problems.add(f"{where} lacks required attribute {a}")
    return sorted(problems)


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
        el_id = el.get("id")
        if el_id and el.tag not in ("ThemeInfo", "SliderBackground"):
            key = (kind, el_id)
            if key in seen:
                err(f"{kind} id {el_id} is used twice")
            seen[key] = el

    bitmaps = {}
    for b in root.iter("Bitmap"):
        bmp_id, bmp_file = b.get("id"), b.get("file")
        bmp_path = theme_path.parent / bmp_file if bmp_file else None
        if not bmp_path or not bmp_path.is_file():
            err(f"bitmap {bmp_id}: missing file {bmp_file}")
            continue
        with Image.open(bmp_path) as sheet:
            sw, sh = sheet.size
        bitmaps[bmp_id] = (sw, sh)
        for sb in b.iter("SubBitmap"):
            x, y, w, h = (int(sb.get(k, 0)) for k in ("x", "y", "width", "height"))
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > sw or y + h > sh:
                err(f"SubBitmap {sb.get('id')} lies outside {bmp_file}")
            bitmaps[sb.get("id")] = (w, h)

    fonts = {"defaultfont"} | {f.get("id") for f in root.iter("Font") if f.get("id")}
    for f in root.iter("Font"):
        font_file = f.get("file")
        if not font_file or not (theme_path.parent / font_file).is_file():
            err(f"font {f.get('id')}: missing file {font_file}")

    popups = {p.get("id") for p in root.iter("PopupMenu") if p.get("id")}
    windows = {w.get("id"): {l.get("id") for l in w.iter("Layout") if l.get("id")}
               for w in root.iter("Window") if w.get("id")}
    layouts = {l for ls in windows.values() for l in ls}
    bools = (BOOLS
             | {f"{w}.isVisible" for w in windows}
             | {f"{w}.isMaximized" for w in windows}
             | {f"{l}.isActive" for l in layouts})

    def action_ok(action):
        if not action or not action.strip():
            return False
        for part in (p.strip() for p in action.split(";")):
            if part in COMMANDS:
                continue
            m = re.fullmatch(r"(\w+)\.(show|hide|maximize|unmaximize)\(\)", part)
            if m and (m.group(1) in windows or (m.group(2) in ("show", "hide") and m.group(1) in popups)):
                continue
            m = re.fullmatch(r"(\w+)\.setLayout\((\w+)\)", part)
            if m and m.group(1) in windows and m.group(2) in windows[m.group(1)]:
                continue
            return False
        return True

    def bool_ok(expr):
        tokens = re.findall(r"\(\vert{}\)|[^\s()]+", expr or "")
        if not tokens:
            return False
        depth = 0
        expect_operand = True
        for tok in tokens:
            if expect_operand:
                if tok == "(":
                    depth += 1
                elif tok == "not":
                    continue
                elif tok in bools:
                    expect_operand = False
                else:
                    return False
            else:
                if tok == ")":
                    depth -= 1
                    if depth < 0:
                        return False
                elif tok in ("and", "or"):
                    expect_operand = True
                else:
                    return False
        return not expect_operand and depth == 0

    for win in root.iter("Window"):
        for layout in win.iter("Layout"):
            lw, lh = int(layout.get("width", 0)), int(layout.get("height", 0))
            in_panel = {child for p in layout.iter("Panel") for child in p.iter() if child is not p}
            for el in layout.iter():
                if el is layout:
                    continue
                where = f"{layout.get('id')}/{el.tag} {el.get('id')}"
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
                    nbh, nbv = int(el.get("nbhoriz", 1)), int(el.get("nbvert", 1))
                    ph, pv = int(el.get("padhoriz", 0)), int(el.get("padvert", 0))
                    fw, fh = w - (nbh - 1) * ph, h - (nbv - 1) * pv
                    if w and h and (nbh <= 0 or nbv <= 0 or fw <= 0 or fh <= 0 or fw % nbh or fh % nbv):
                        err(f"{where}: {w}x{h} frames do not divide into {nbh} x {nbv}")
                for attr in ("text", "tooltiptext", "help"):
                    val = el.get(attr, "")
                    for tok in re.findall(r"\$(.|)", val, re.S):
                        if tok not in TOKENS:
                            err(f"{where}: unknown text token ${tok}")
                # the control's default rectangle must lie inside the layout
                if el.tag in BOUNDED_CONTROLS and el not in in_panel:
                    x, y = int(el.get("x", 0)), int(el.get("y", 0))
                    bmp_w, bmp_h = bitmaps.get(el.get("image") or el.get("up") or el.get("up1"), (0, 0))
                    w = int(el.get("width") or 0) or bmp_w
                    h = int(el.get("height") or 0) or bmp_h
                    if x < 0 or y < 0 or x + w > lw or y + h > lh:
                        err(f"{where}: {w}x{h} at {x},{y} falls outside the {lw}x{lh} layout")
    for item in root.iter("MenuItem"):
        if not action_ok(item.get("action", "")):
            err(f"menu item '{item.get('label')}': unknown action '{item.get('action')}'")
    return errors


def _inside_panel(layout, el):
    """Controls in a Panel are positioned relative to it, so the layout bounds check skips them."""
    return any(el in p.iter() and el is not p for p in layout.iter("Panel"))


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "dist/VLC-Redesign/theme.xml"
    problems = check(path)
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
