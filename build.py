#!/usr/bin/env python3
"""Build the VLC Redesign skin for VLC 3.0 (skins2) from the Figma reference.

    python build.py

Writes dist/VLC-Redesign/ (theme.xml, img/, fonts/) and dist/VLC-Redesign.vlt.
Load either in VLC with Tools > Preferences > Interface > "Use custom skin", or run

    vlc.exe -I skins --skins2-last="C:\\dev\\vlcskin\\dist\\VLC-Redesign.vlt"

docs/notes.md explains what of the Figma design is in the skin and what skins2 cannot do.

Every image is drawn knowing the surface it will sit on (`on=`), because skins2 cannot
blend partly transparent pixels with what is beneath them; see paint.solidify.
"""
import argparse
import gzip
import shutil
import tarfile
import tempfile
from pathlib import Path

import sys

from skinlib import paint as P
from skinlib.palette import DARK, LIGHT, THEMES
from skinlib.skin import Layout, Skin

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import check_theme  # noqa: E402  (tools/ is not a package)

NAME = "VLC-Redesign"
DIST = ROOT / "dist"
OUT = DIST / NAME
ICONS = P.Icons()

# The widest seek track whose fill can follow the handle (see progress()): a track this
# wide belongs to a 5,190 px wide window. Longer only costs memory in VLC.
MAX_TRACK = 4500

STOPPED, ACTIVE = "vlc.isStopped", "not vlc.isStopped"
ART_VIEW = "not vlc.isStopped and not vlc.hasVout"


def lid(t, kind):
    """Layout ids: dark_full, dark_side, dark_mini, dark_eq, dark_fsc and the light_ ones."""
    return f"{t['name']}_{kind}"


def other(t):
    return LIGHT if t is DARK else DARK


def switch_theme(t, kind):
    o = other(t)
    return (f"main.setLayout({lid(o, kind)});eqwin.setLayout({lid(o, 'eq')});"
            f"fullscreenController.setLayout({lid(o, 'fsc')})")


class Art:
    """Theme-bound bitmap factory. Ids are prefixed with the theme name; `on` names the
    palette colour of the surface an image sits on, and its edges are composited onto it."""

    def __init__(self, skin, t):
        self.skin, self.t = skin, t

    def get(self, key, make, on=None, opaque=False):
        """opaque fills the whole image with the surface colour, not just its edges: skins2
        clicks only hit opaque pixels, so a button drawn as a bare icon is clickable only
        on the icon's strokes."""
        def draw():
            img = make() if callable(make) else make
            if on:
                return (P.flatten if opaque else P.solidify)(img, self.t[on])
            return img
        return self.skin.bitmap(f"{self.t['name']}.{key}{'@' + on if on else ''}{'.o' if opaque else ''}", draw)

    def px(self, color_key):
        """A 1 x 1 pixel of a palette colour, for scaled fills."""
        return self.get(f"px.{color_key}", lambda: P.solid(1, 1, self.t[color_key]))

    def states(self, key, draw, specs, on):
        """Three images (up, over, down) from draw(*spec) for each spec in specs."""
        return tuple(self.get(f"{key}.{name}", lambda s=spec: draw(*s), on, opaque=True)
                     for name, spec in zip(("up", "over", "down"), specs))

    def icon_button(self, icon, w=30, h=28, ix=3, iy=2, r=6, active=False, on="chrome"):
        """A flat icon button: just the icon, with a rounded highlight on hover.
        Active buttons draw the icon in the accent colour."""
        t = self.t

        def draw(bg, color):
            img = P.blank(w, h)
            if bg:
                img.alpha_composite(P.rrect(w, h, (0, 0, w, h), r, t[bg]))
            img.alpha_composite(ICONS.tint(icon, t[color]), (ix, iy))
            return img
        fg = ("accent", "accent_hover", "accent_down") if active else ("icon", "icon_hover", "icon_down")
        return self.states(f"ib.{icon}.{w}x{h}.{ix}.{iy}{'.on' if active else ''}", draw,
                           ((None, fg[0]), ("hover_bg", fg[1]), ("down_bg", fg[2])), on)

    def accent_button(self, icon, w, h, r=6, on="chrome"):
        """The orange play/pause pill."""
        t = self.t

        def draw(bg):
            img = P.rrect(w, h, (0, 0, w, h), r, t[bg])
            img.alpha_composite(ICONS.tint(icon, t["on_accent"]), ((w - 24) // 2, (h - 24) // 2))
            return img
        return self.states(f"ab.{icon}.{w}x{h}", draw, (("accent",), ("accent_hover",), ("accent_down",)), on)

    def window_button(self, icon, danger=False, on="chrome"):
        """Title-bar buttons (36 x 24). Close turns red on hover, as on Windows."""
        t = self.t

        def draw(bg, color):
            img = P.blank(36, 24)
            if bg:
                img.alpha_composite(P.rrect(36, 24, (0, 0, 36, 24), 5, bg))
            img.alpha_composite(ICONS.tint(icon, color), (6, 0))
            return img
        over_bg = t["close_hover"] if danger else t["hover_bg"]
        over_fg = "#FFFFFF" if danger else t["icon_hover"]
        down_bg = P.mix(t["close_hover"], "#000000", .15) if danger else t["down_bg"]
        return self.states(f"wb.{icon}", draw, ((None, t["icon"]), (over_bg, over_fg), (down_bg, over_fg)), on)

    def labelled_button(self, key, icon, label, w, h, ix, iy, tx, base, size, on, colors=("icon", "icon_hover", "icon_down")):
        """An icon followed by text, e.g. the top bar's 'Open media'."""
        t = self.t

        def draw(bg, color):
            img = P.blank(w, h)
            if bg:
                img.alpha_composite(P.rrect(w, h, (0, 0, w, h), 6, t[bg]))
            img.alpha_composite(ICONS.tint(icon, t[color]), (ix, iy))
            return P.text(img, tx, base, label, size, t[color])
        return self.states(key, draw, ((None, colors[0]), ("hover_bg", colors[1]), ("down_bg", colors[2])), on)

    def handle(self, w, h, r, colors, on, key):
        t = self.t
        return self.states(f"{key}.{w}x{h}", lambda c: P.rrect(w, h, (0, 0, w, h), r, t[c]),
                           tuple((c,) for c in colors), on)

    def nothing(self):
        return self.skin.bitmap("transparent", lambda: P.blank(1, 1))


def progress(L, art, *, x0, x1, y, h, inset, r_track, r_fill, handle, anchor_l, anchor_s,
             bg, on="chrome", handle_on="fill", fill_key="fill",
             handle_keys=("handle", "handle_hover", "accent_down"),
             value="time", tip="$T / $D", visible=ACTIVE, draw_track=True, name="seek"):
    """A track with a fill that follows the slider value, as in the Figma seek bar.

    skins2 sliders have no fill, so this stacks three things:
      1. a slider whose cursor is a very long strip of fill colour ending at the handle
         (it reaches far to the left, past the start of the track),
      2. an opaque image that repaints whatever lies left of the track, hiding that overflow,
      3. a second slider on the same curve with the real handle; being on top, its
         background takes the clicks, so clicking the track seeks as usual.

    x0/x1: track edges (x1 exclusive) in layout coords; y: track top; h: track height.
    handle: (w, h, r). bg(x0, y0, x1, y1) returns the opaque image under a layout rectangle.
    on: surface around the track. anchor_l pins things left of the track; anchor_s is for
    the parts that stretch with it.
    """
    t = art.t
    hw, hh, hr = handle
    fh = h - 2 * inset
    lo = x0 + inset + hw // 2                 # handle centre at value 0
    hi = x1 - inset - (hw - hw // 2)          # ... and at value 1
    length = hi - lo
    cy = y + h // 2                           # centre line of track, fill and handle

    if draw_track:
        cap = r_track
        whole = lambda: P.rrect(cap * 3, h, (0, 0, cap * 3, h), r_track, t["track"])
        L.image(art.get(f"{name}.cap.l.{h}.{r_track}", lambda: whole().crop((0, 0, cap, h)), on),
                x0, y, anchor=anchor_l, hint=f"{name}track")
        L.image(art.get(f"{name}.mid.{h}", lambda: P.solid(1, h, t["track"])), x0 + cap, y,
                w=x1 - x0 - 2 * cap, h=h, resize="scale", anchor=anchor_s, hint=f"{name}track")
        L.image(art.get(f"{name}.cap.r.{h}.{r_track}", lambda: whole().crop((cap * 2, 0, cap * 3, h)), on),
                x1 - cap, y, anchor="br" if anchor_s == "bottom" else anchor_l, hint=f"{name}track")

    # 1. the fill: a cursor whose centre column sits on the value and whose strip ends at
    #    the handle's right edge. skins2 centres a cursor on the value, so the strip is the
    #    left half of an image whose right half is empty. It must reach back to the start of
    #    the track (the mask hides any more); a stretching track can grow up to MAX_TRACK.
    reach = (MAX_TRACK if anchor_s != "tl" else length) + hw // 2 + 1

    def strip():
        img = P.blank(2 * reach + 1, fh)
        img.paste(P.solid(reach + hw - hw // 2, fh, t[fill_key]), (0, 0))
        return img
    L.slider(value, lo, cy - fh // 2, f"(0,{fh // 2}),({length},{fh // 2})",
             up=art.get(f"fill.{fh}.{hw}.{fill_key}.{reach}", strip), anchor=anchor_s, visible=visible,
             hint=f"{name}fill")

    # 2. the mask over the overflow left of the track, with the fill's rounded start
    fy = cy - fh // 2

    def mask():
        w = x0 + inset + 40
        img = bg(0, y, w, y + h)
        img.alpha_composite(P.rrect(w, h, (x0, 0, w + 40, h), r_track, t["track"]))
        img.alpha_composite(P.rrect(w, h, (x0 + inset, inset, w + 40, h - inset), r_fill, t[fill_key]))
        return img.crop((0, fy - y, lo, fy - y + fh))
    L.image(art.skin.bitmap(f"{L.id}.{name}.mask", mask), 0, fy, anchor=anchor_l, visible=visible,
            hint=f"{name}mask")

    # 3. the interactive handle, on the same curve but centred on its own height
    up, over, down = art.handle(hw, hh, hr, handle_keys, handle_on, key=f"{name}.handle")
    L.slider(value, lo, cy - hh // 2, f"(0,{hh // 2}),({length},{hh // 2})", up=up, over=over, down=down,
             thickness=max(h // 2, hh // 2), tip=tip, anchor=anchor_s, visible=visible, hint=name)


# --- the control bar (Figma "Controls", 491:1779) ------------------------------------

def control_bar(L, art, oy, W, *, fixed, bg, last):
    """The 54 px bar along the bottom. Positions are those of the Figma component: the left
    group pinned left, the right group pinned right, the seek track stretching between.
    last(x, y, anchor) draws the rightmost button."""
    t = art.t
    A = (lambda a: "tl") if fixed else (lambda a: a)
    f16 = L.skin.font(16)
    base = oy + 33 - P.ascent(16)   # the Figma digits sit on y = 33 of the bar

    progress(L, art, x0=254, x1=W - 428, y=oy + 13, h=28, inset=2, r_track=6, r_fill=4,
             handle=(8, 24, 4), anchor_l=A("bl"), anchor_s=A("bottom"), bg=bg)

    L.button(art.icon_button("previous"), 20, oy + 13, "playlist.previous()", "Previous", anchor=A("bl"))
    L.toggle("vlc.isPlaying", art.accent_button("play", 54, 28), art.accent_button("pause", 54, 28),
               "vlc.play()", "vlc.pause()", "Play", "Pause", x=58, y=oy + 13, anchor=A("bl"))
    L.button(art.icon_button("next"), 120, oy + 13, "playlist.next()", "Next", anchor=A("bl"))
    L.text("$T", 170, base, 76, f16, t["text"], align="center", anchor=A("bl"), visible=ACTIVE)

    L.text("$D", W - 420, base, 76, f16, t["text"], align="center", anchor=A("br"), visible=ACTIVE)
    L.toggle("vlc.isMute", art.icon_button("volume"), art.icon_button("mute"), "vlc.mute()", "vlc.mute()",
               "Mute", "Unmute", x=W - 327, y=oy + 13, anchor=A("br"))
    frames = art.get("volume.frames", lambda: P.volume_frames(t), on="chrome")
    L.slider("volume", W - 292, oy + 13, "(0,27),(87,27)", up=art.nothing(), w=88, h=28,
             tip="Volume: $V%", anchor=A("br"), background=(frames, 9, 10), hint="volume")

    L.toggle("eqwin.isVisible", art.icon_button("audio", 30, 32, 3, 4),
               art.icon_button("audio", 30, 32, 3, 4, active=True), "eqwin.show()", "eqwin.hide()",
               "Equalizer", "Hide equalizer", x=W - 184, y=oy + 11, anchor=A("br"))
    L.button(art.icon_button("subtitles", 30, 32, 3, 4), W - 142, oy + 11, "dialogs.popup()",
             "Subtitles, tracks and the rest of VLC's menu", anchor=A("br"))
    L.button(art.icon_button("playback_settings", 30, 32, 3, 4), W - 100, oy + 11, "playback_menu.show()",
             "Playback", anchor=A("br"))
    last(W - 50, oy + 11, A("br"))


# --- the main window --------------------------------------------------------------

def top_bar(L, art, kind):
    """Figma 'topbar' (from Player - Music, 4767:23728): 40 px with the cone, menu, sidebar
    toggle and media button on the left, the title centred, window buttons on the right."""
    t, W = art.t, L.w
    chrome = art.px("chrome")
    L.image(chrome, 0, 0, W, 40, anchor="top", resize="scale", action="move",
            action2="main.maximize()", visible="not main.isMaximized", hint="titlebar")
    L.image(chrome, 0, 0, W, 40, anchor="top", resize="scale", action="move",
            action2="main.unmaximize()", visible="main.isMaximized", hint="titlebar")

    def cone(bg):
        img = P.blank(38, 28)
        if bg:
            img.alpha_composite(P.rrect(38, 28, (0, 0, 38, 28), 6, t[bg]))
        img.alpha_composite(ICONS.raw("vlc"), (7, 2))
        return img
    L.button(art.states("tb.cone", cone, ((None,), ("hover_bg",), ("down_bg",)), "chrome"),
             6, 6, "dialogs.popup()", "VLC menu")
    L.button(art.icon_button("more", 28, 28, 2, 2), 51, 6, f"{lid(t, kind)}_menu.show()", "Menu")
    if kind == "side":
        L.button(art.icon_button("sidebar", 28, 28, 2, 2, active=True), 89, 6,
                 f"main.setLayout({lid(t, 'full')})", "Hide playlist")
    else:
        L.button(art.icon_button("sidebar", 28, 28, 2, 2), 89, 6, f"main.setLayout({lid(t, 'side')})",
                 "Show playlist")
    L.image(art.get("tb.divider", lambda: ICONS.tint("divider", t["text_dim"]), "chrome"), 117, 8)

    # the Figma breadcrumb shows the media's folder, which skins2 cannot know: it opens media
    label = "Open media"
    L.button(art.labelled_button("tb.crumb", "folder", label, 32 + P.text_width(label, 14) + 10, 28,
                                 2, 2, 32, 19, 14, "chrome"),
             141, 6, "dialogs.fileSimple()", "Open a file")

    f14 = L.skin.font(14)
    y = 25 - P.ascent(14)
    L.text("$N", 330, y, W - 660, f14, t["text"], align="center", anchor="top", visible=ACTIVE)
    L.text("VLC Media Player", 330, y, W - 660, f14, t["text"], align="center", anchor="top", visible=STOPPED)

    L.button(art.window_button("minimize"), W - 150, 8, "vlc.minimize()", "Minimize", anchor="tr")
    L.button(art.window_button("maximize"), W - 114, 8, "main.maximize()", "Maximize", anchor="tr",
             visible="not main.isMaximized")
    L.button(art.window_button("maximize"), W - 114, 8, "main.unmaximize()", "Restore", anchor="tr",
             visible="main.isMaximized")
    L.button(art.window_button("fullscreen"), W - 78, 8, "vlc.fullscreen()", "Fullscreen", anchor="tr")
    L.button(art.window_button("close", danger=True), W - 42, 8, "vlc.quit()", "Quit VLC", anchor="tr")


def stage(L, art, x0, y0, x1, y1, outside):
    """The video area (Figma: the rounded rectangle inset under the top bar). Black whenever
    there is nothing to show, as in VLC. Audio without video shows its cover and title, as in
    Figma 'Player - Music' (whose blurred backdrop needs translucency skins2 lacks); without
    a cover, just the title. outside: palette key of the colour around each rounded corner,
    in tl, tr, br, bl order."""
    t = art.t
    w, h = x1 - x0, y1 - y0
    black = art.px("stage")
    L.image(black, x0, y0, w, h, anchor="fill", resize="scale", action2="dialogs.fileSimple()", hint="stage")
    # the media's cover; with none, its fallback is the black pixel, so nothing shows
    L.image(black, x0 + 60, y0 + 48, w - 120, h - 48 - 120, anchor="fill", resize="scale2", art=True,
            visible=ART_VIEW, hint="cover")
    f20 = L.skin.font(20)
    L.text("$N", x0 + 20, y1 - 62 - P.ascent(20), w - 40, f20, t["stage_text"], align="center",
           anchor="bottom", visible=ART_VIEW)

    L.video(x0, y0, w, h, visible="vlc.hasVout")

    # rounded corners: patches of the outside colour laid over the stage's corners
    r = 8
    spots = ((x0, y0, "tl"), (x1 - r, y0, "tr"), (x1 - r, y1 - r, "br"), (x0, y1 - r, "bl"))
    for (cx, cy, which), out in zip(spots, outside):
        img = lambda which=which, out=out: P.corner(r, t[out], which)
        L.image(art.get(f"corner.{which}.{r}.{out}", img, "stage"), cx, cy, anchor=which, hint="corner")


def repeat_controls(L, art, x, y, on):
    """Off -> repeat all -> repeat one -> off, the way VLC's own button cycles."""
    t = art.t
    off = art.icon_button("repeat", 28, 28, 2, 2, on=on)
    all_ = art.icon_button("repeat", 28, 28, 2, 2, active=True, on=on)

    def one_draw(bg, color):
        img = P.blank(28, 28)
        if bg:
            img.alpha_composite(P.rrect(28, 28, (0, 0, 28, 28), 6, t[bg]))
        img.alpha_composite(ICONS.tint("repeat", t[color]), (2, 2))
        return P.text(img, 14, 18, "1", 9, t[color], weight="semibold", align="center")
    one = art.states("repeat1", one_draw, ((None, "accent"), ("hover_bg", "accent_hover"), ("down_bg", "accent_down")), on)
    L.toggle("playlist.isLoop", off, all_, "playlist.setLoop(true)", "playlist.setLoop(false);playlist.setRepeat(true)",
               "Repeat all", "Repeat one", x=x, y=y, visible="not playlist.isRepeat")
    L.button(one, x, y, "playlist.setRepeat(false)", "Repeat off", visible="playlist.isRepeat")


# Playlist rows (Figma sidebar list): ROW px tall, text in the "Inter Rows" font
ROW, ROW_TEXT = 32, 14


def playtree_item(t):
    """Item icon for playlist rows. skins2 makes a row as tall as this image plus 1 and puts
    the text this image's width plus 2 to the right, so the 36 px width lines the text up
    with 'Add media' above it. The icon is centred in the row."""
    icon = ICONS.tint("media", t["icon"])
    bbox = icon.getbbox()
    img = P.blank(36, ROW - 1)
    # skins2 draws the image 1 px below the row top
    img.alpha_composite(icon, (4, round(ROW / 2 - 1 - (bbox[1] + bbox[3]) / 2)))
    return img


def sidebar(L, art):
    """Figma 'sidebar' (848:1996): a 48 px rail and a 379 px panel, here holding the playlist.
    VLC 3 has no media library views, so the rail offers VLC's ways to open media instead."""
    t, H = art.t, L.h
    top, bottom = 40, H - 54
    rail = (("playlist", f"main.setLayout({lid(t, 'full')})", "Hide playlist", True),
            ("file", "dialogs.file()", "Open files", False),
            ("folder", "dialogs.directory()", "Open a folder", False),
            ("disc", "dialogs.disc()", "Open a disc", False),
            ("streaming", "dialogs.net()", "Open a network stream", False),
            ("info", "dialogs.fileInfo()", "Media information", False))
    for i, (icon, action, tip, active) in enumerate(rail):
        L.button(art.icon_button(icon, 36, 36, 6, 6, active=active), 6, 47 + 46 * i, action, tip)
    L.button(art.icon_button("preferences", 36, 36, 6, 6), 6, bottom - 46, "dialogs.prefs()", "Preferences",
             anchor="bl")

    x0, x1 = 48, 427
    L.image(art.px("panel"), x0, top, x1 - x0, bottom - top, anchor="left", resize="scale", hint="sbpanel")
    L.text("Playlist", 70, 79 - P.ascent(16, "semibold"), 200, L.skin.font(16, "semibold"), t["text_hi"])
    L.toggle("playlist.isRandom", art.icon_button("shuffle", 28, 28, 2, 2, on="panel"),
               art.icon_button("shuffle", 28, 28, 2, 2, active=True, on="panel"), "playlist.setRandom(true)",
               "playlist.setRandom(false)", "Shuffle", "Shuffle off", x=301, y=58)
    repeat_controls(L, art, 339, 58, "panel")
    L.button(art.icon_button("open", 28, 28, 2, 2, on="panel"), 377, 58, "dialogs.playlist()",
             "Open VLC's playlist window")

    L.text("Queue", 70, 120 - P.ascent(13), 120, L.skin.font(13), t["text_dim"])
    for i, (icon, action, tip) in enumerate((("sort", "playlist.sort()", "Sort by title"),
                                             ("folder", "playlist.load()", "Load a playlist file"),
                                             ("save", "playlist.save()", "Save the playlist"),
                                             ("remove", "playlist.del()", "Remove selected items"))):
        L.button(art.icon_button(icon, 28, 28, 2, 2, on="panel"), 263 + 38 * i, 100, action, tip)
    L.image(art.px("divider"), 70, 142, 336, 1, resize="scale", hint="sbdivider")

    # 'Add media' and the playlist rows share their height and their icon and text columns
    L.button(art.labelled_button("sb.add", "add", "Add media", 342, ROW, 4, (ROW - 24) // 2, 38,
                                 ROW // 2 + 5, ROW_TEXT, "panel", colors=("text", "icon_hover", "icon_down")),
             64, 152, "playlist.add()", "Add files to the playlist")

    ty, th = 152 + ROW + 4, bottom - 10 - (152 + ROW + 4)
    thumb = art.get("sb.thumb", lambda: P.rrect(4, 40, (0, 0, 4, 40), 2, P.mix(t["panel"], t["text"], .35)), "panel")
    thumb_over = art.get("sb.thumb.over", lambda: P.rrect(4, 40, (0, 0, 4, 40), 2, P.mix(t["panel"], t["text"], .7)), "panel")
    L.playtree(64, ty, 342, th, L.skin.font(ROW_TEXT, "rows"),
               dict(fgcolor=t["row_text"], playcolor=t["accent"], selcolor=t["row_sel"],
                    bgcolor1=t["panel"], bgcolor2=t["panel"]),
               art.get("pt.item", lambda: playtree_item(t), "panel"), anchor="left",
               scrollbar=(410, ty, f"(2,{th - 20}),(2,20)", thumb, thumb_over))


def full_layout(skin, win, t, side):
    """The main player, 1280 x 720 by default and resizable. side=True adds the sidebar."""
    kind = "side" if side else "full"
    W, H = 1280, 720
    L = Layout(skin, win, lid(t, kind), W, H, min_size=(1040 if side else 720, 420))
    art = Art(skin, t)
    L.image(art.px("chrome"), 0, 0, W, H, anchor="fill", resize="scale", action="move", hint="bg")
    if side:
        sidebar(L, art)
        stage(L, art, 427, 40, W - 10, H - 54, ("panel", "chrome", "chrome", "panel"))
    else:
        stage(L, art, 10, 40, W - 10, H - 54, ("chrome",) * 4)
    top_bar(L, art, kind)

    def last(x, y, anchor):
        if side:
            L.button(art.icon_button("lists", 30, 32, 3, 4, active=True), x, y,
                     f"main.setLayout({lid(t, 'full')})", "Hide playlist", anchor=anchor)
        else:
            L.button(art.icon_button("lists", 30, 32, 3, 4), x, y,
                     f"main.setLayout({lid(t, 'side')})", "Show playlist", anchor=anchor)
    control_bar(L, art, H - 54, W, fixed=False, last=last,
                bg=lambda x0, y0, x1, y1: P.solid(x1 - x0, y1 - y0, t["chrome"]))

    # skins2 windows resize only from the right, the bottom and that corner
    chrome = art.px("chrome")
    L.image(chrome, W - 5, 0, 5, H - 12, anchor="right", resize="scale", action="resizeE", hint="gripE")
    L.image(chrome, 0, H - 4, W - 12, 4, anchor="bottom", resize="scale", action="resizeS", hint="gripS")
    L.image(chrome, W - 12, H - 12, 12, 12, anchor="br", resize="scale", action="resizeSE", hint="gripSE")


# --- mini player (Figma "Miniplayer", 970:3090) ---------------------------------------

def mini_layout(skin, win, t):
    W, H = 391, 339
    L = Layout(skin, win, lid(t, "mini"), W, H)
    art = Art(skin, t)
    vx, vy, vw, vh = 8, 8, 375, 211

    bg_img = P.solid(W, H, t["border"])
    bg_img.alpha_composite(P.rrect(W, H, (1, 1, W - 1, H - 1), 0, t["chrome"]))
    bg_img.alpha_composite(P.rrect(W, H, (vx, vy, vx + vw, vy + vh), 6, t["stage"]))
    L.image(art.get("mini.bg", bg_img), 0, 0, action="move", hint="bg")
    L.image(art.px("stage"), vx, vy + 8, vw, vh - 16, resize="scale2", art=True, visible=ART_VIEW, hint="cover")
    L.video(vx, vy, vw, vh, anchor="tl", visible="vlc.hasVout")

    progress(L, art, x0=vx, x1=vx + vw, y=227, h=12, inset=2, r_track=4, r_fill=3, handle=(4, 8, 2),
             anchor_l="tl", anchor_s="tl", bg=lambda x0, y0, x1, y1: bg_img.crop((x0, y0, x1, y1)),
             name="miniseek")

    f14 = L.skin.font(14)
    L.text("$N", 12, 266 - P.ascent(14), 367, f14, t["text_hi"], visible=ACTIVE)

    y = 284
    L.button(art.icon_button("previous"), 8, y, "playlist.previous()", "Previous")
    L.toggle("vlc.isPlaying", art.accent_button("play", 46, 28), art.accent_button("pause", 46, 28),
               "vlc.play()", "vlc.pause()", "Play", "Pause", x=40, y=y)
    L.button(art.icon_button("next"), 88, y, "playlist.next()", "Next")
    f12 = L.skin.font(12)
    L.text("$T / $D", 126, y + 19 - P.ascent(12), 126, f12, t["text"], visible=ACTIVE)
    L.toggle("vlc.isMute", art.icon_button("volume"), art.icon_button("mute"), "vlc.mute()", "vlc.mute()",
               "Mute", "Unmute", x=257, y=y)
    L.button(art.icon_button("lists"), 289, y, f"main.setLayout({lid(t, 'side')})", "Full player with playlist")
    L.button(art.icon_button("window"), 321, y, f"main.setLayout({lid(t, 'full')})", "Full player")
    L.button(art.icon_button("close"), 353, y, "vlc.quit()", "Quit VLC")
    return L


# --- equalizer (Figma "Audio - Equalizer", 6114:13610) -------------------------------

BANDS = ("60 Hz", "170 Hz", "310 Hz", "600 Hz", "1 kHz", "3 kHz", "6 kHz", "12 kHz", "14 kHz", "16 kHz")


def toggle_images(art, on):
    """The Figma 'Toggle' (536:1014): a dark pill with a square knob and ON / OFF."""
    t = art.t

    def draw(state):
        img = P.rrect(64, 28, (0, 0, 64, 28), 6, t["track"])
        kx = 38 if state else 2
        img.alpha_composite(P.rrect(64, 28, (kx, 2, kx + 24, 26), 4, t["accent" if state else "toggle_off_knob"]))
        return P.text(img, 20 if state else 45, 18, "ON" if state else "OFF", 11,
                      t["accent" if state else "text_dim"], weight="semibold", align="center")
    off = art.get("toggle.off", lambda: draw(False), on, opaque=True)
    on_ = art.get("toggle.on", lambda: draw(True), on, opaque=True)
    return (off, off, off), (on_, on_, on_)


def eq_layout(skin, win, t):
    W, row_h = 400, 34
    first = 92
    bands_top = first + row_h + 8
    H = bands_top + 10 * row_h + 22
    L = Layout(skin, win, lid(t, "eq"), W, H)
    art = Art(skin, t)
    tx0, tx1 = 100, 372                           # track
    rows = [("Preamp", "equalizer.preamp", first)] + [
        (b, f"equalizer.band({i})", bands_top + i * row_h) for i, b in enumerate(BANDS)]

    bg_img = P.solid(W, H, t["border"])
    bg_img.alpha_composite(P.rrect(W, H, (1, 1, W - 1, H - 1), 0, t["card_outer"]))
    P.text(bg_img, 20, 34, "Equalizer", 16, t["text_hi"], weight="semibold")
    bg_img.alpha_composite(P.rrect(W, H, (12, 56, W - 12, H - 12), 6, t["card"]))
    mid = (tx0 + tx1) // 2
    for label, x, align in (("−20 dB", tx0, "left"), ("0 dB", mid, "center"), ("+20 dB", tx1, "right")):
        P.text(bg_img, x, 80, label, 11, t["text_dim"], align=align)
    bg_img.alpha_composite(P.rrect(W, H, (mid, 84, mid + 1, H - 22), 0, P.mix(t["card"], t["text_dim"], .45)))
    for label, _, y in rows:
        P.text(bg_img, 28, y + 22, label, 14, t["text"])
        bg_img.alpha_composite(P.rrect(W, H, (tx0, y + 9, tx1, y + 25), 4, t["track"]))
    bg_img.alpha_composite(P.rrect(W, H, (28, bands_top - 5, W - 28, bands_top - 4), 0, t["divider"]))
    L.image(art.get("eq.bg", bg_img), 0, 0, action="move", hint="bg")

    for label, value, y in rows:
        progress(L, art, x0=tx0, x1=tx1, y=y + 9, h=16, inset=2, r_track=4, r_fill=3, handle=(8, 24, 4),
                 anchor_l="tl", anchor_s="tl", bg=lambda x0, y0, x1, y1: bg_img.crop((x0, y0, x1, y1)),
                 value=value, tip=label, visible=None, handle_on="card",
                 handle_keys=("eq_handle", "accent_hover", "accent_down"), draw_track=False,
                 name="eq" + value.split(".")[1].replace("(", "").replace(")", ""))
    off, on = toggle_images(art, "card_outer")
    L.toggle("equalizer.isEnabled", off, on, "equalizer.enable()", "equalizer.disable()",
               "Turn the equalizer on", "Turn the equalizer off", x=W - 20 - 36 - 10 - 64, y=14)
    L.button(art.window_button("close", on="card_outer"), W - 48, 16, "eqwin.hide()", "Close")
    return L


# --- fullscreen controller ----------------------------------------------------------

def fsc_layout(skin, win, t):
    """The bar again, floating over fullscreen video."""
    W, H = 1000, 56
    L = Layout(skin, win, lid(t, "fsc"), W, H)
    art = Art(skin, t)
    bg_img = P.solid(W, H, t["border"])
    bg_img.alpha_composite(P.rrect(W, H, (1, 1, W - 1, H - 1), 0, t["chrome"]))
    L.image(art.get("fsc.bg", bg_img), 0, 0, action="move", hint="bg")

    def last(x, y, anchor):
        L.button(art.icon_button("fullscreen_exit", 30, 32, 3, 4), x, y, "vlc.fullscreen()", "Leave fullscreen",
                 anchor=anchor)
    control_bar(L, art, 1, W, fixed=True, last=last, bg=lambda x0, y0, x1, y1: bg_img.crop((x0, y0, x1, y1)))
    return L


# --- menus ----------------------------------------------------------------------

def menus(skin):
    """The '...' menu (Figma 'menu', 6062:13354) per layout, and the playback menu
    (Figma 'right-click menu', 6065:13616). Shortcuts shown are VLC's own hotkeys."""
    for t in THEMES:
        o = other(t)
        for kind in ("full", "side", "mini"):
            view = [("Hide Playlist" if kind == "side" else "Show Playlist",
                     f"main.setLayout({lid(t, 'full' if kind == 'side' else 'side')})"),
                    ("Full Player" if kind == "mini" else "Mini Player",
                     f"main.setLayout({lid(t, 'full' if kind == 'mini' else 'mini')})"),
                    (f"{o['name'].title()} Theme", switch_theme(t, kind)),
                    ("Always on Top", "vlc.onTop()")]
            skin.menu(f"{lid(t, kind)}_menu", [
                ("Open File(s)...", "dialogs.file()"),
                ("Open Folder...", "dialogs.directory()"),
                ("Open Network Stream...", "dialogs.net()"),
                ("Open Disc...", "dialogs.disc()"),
                ("Convert / Stream...", "dialogs.streamingWizard()"),
                None,
                *view,
                None,
                ("Media Information", "dialogs.fileInfo()"),
                ("Messages", "dialogs.messages()"),
                ("Change Skin...", "dialogs.changeSkin()"),
                ("Settings...", "dialogs.prefs()"),
                None,
                ("Quit VLC\tCtrl+Q", "vlc.quit()"),
            ])
    skin.menu("playback_menu", [
        ("Play\tSpace", "vlc.play()"),
        ("Pause\tSpace", "vlc.pause()"),
        ("Stop\tS", "vlc.stop()"),
        ("Previous Item\tP", "playlist.previous()"),
        ("Next Item\tN", "playlist.next()"),
        None,
        ("Faster\t]", "vlc.faster()"),
        ("Slower\t[", "vlc.slower()"),
        ("Next Frame\tE", "vlc.nextFrame()"),
        None,
        ("Take Snapshot\tShift+S", "vlc.snapshot()"),
        ("Record\tShift+R", "vlc.toggleRecord()"),
        None,
        ("Video...", "dialogs.videoPopup()"),
        ("Audio...", "dialogs.audioPopup()"),
        ("Subtitle and More...", "dialogs.popup()"),
        ("More Settings...", "dialogs.prefs()"),
    ])


# --- build -------------------------------------------------------------------------

MAIN_KINDS = ("full", "side", "mini")


def build(start="dark_full", show_eq=False, preview_fsc=False):
    """start: the layout the main window opens with (VLC remembers the last one used
    after that). show_eq opens the equalizer too. preview_fsc renames the fullscreen
    controller so it opens as an ordinary window. The last two are for screenshots."""
    if OUT.exists():
        shutil.rmtree(OUT)
    rows = P.rows_font(Path(tempfile.mkdtemp()) / "InterRows-Regular.ttf", ROW_TEXT, ROW)
    skin = Skin("VLC Redesign", "Design by Juxtopposed, skinned by build.py", OUT,
                {**P.FONT_FILES, "rows": rows}, P.FONT_LICENSE)
    menus(skin)

    # skins2 starts each window on the layout added last
    start_t = DARK if start.startswith("dark") else LIGHT
    main = skin.window("main", position="Center", dragdrop="true", playondrop="true")
    order = [(t, k) for t in THEMES for k in MAIN_KINDS if lid(t, k) != start] + [(start_t, start.split("_")[1])]
    for t, kind in order:
        if kind == "mini":
            mini_layout(skin, main, t)
        else:
            full_layout(skin, main, t, kind == "side")
    eq = skin.window("eqwin", visible="true" if show_eq else "false", position="Center")
    fsc = (skin.window("fscpreview", position="Center") if preview_fsc else
           skin.window("fullscreenController", position="South", ymargin="3%"))
    for t in (other(start_t), start_t):
        eq_layout(skin, eq, t)
        fsc_layout(skin, fsc, t)

    skin.write()
    problems = check_theme.check(OUT / "theme.xml")
    if problems:
        raise SystemExit("theme.xml has problems:\n  " + "\n  ".join(problems))
    vlt = DIST / f"{NAME}.vlt"
    # dist/ is committed, so the archive is made byte-for-byte reproducible: no timestamps,
    # owners or ordering that change from build to build
    def plain(info):
        info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
        return info
    with open(vlt, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz, \
            tarfile.open(fileobj=gz, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        tar.add(OUT, arcname=NAME, recursive=False, filter=plain)
        for path in sorted(OUT.rglob("*")):
            tar.add(path, arcname=f"{NAME}/{path.relative_to(OUT).as_posix()}", recursive=False, filter=plain)
    images = len(list((OUT / "img").glob("*.png")))
    print(f"{OUT / 'theme.xml'}: {images} images")
    print(f"{vlt}: {vlt.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--start", default="dark_full", choices=[lid(t, k) for t in THEMES for k in MAIN_KINDS],
                    help="layout the main window opens with")
    ap.add_argument("--show-eq", action="store_true", help="open the equalizer window at start")
    ap.add_argument("--preview-fsc", action="store_true",
                    help="show the fullscreen controller as a normal window (for screenshots)")
    a = ap.parse_args()
    build(a.start, a.show_eq, a.preview_fsc)
