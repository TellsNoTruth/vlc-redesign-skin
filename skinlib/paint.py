"""Raster helpers. Every image in the skin is drawn here or cut from the Figma icon sheet.

Shapes are drawn SS times larger and box-filtered down in premultiplied space,
which gives clean antialiased edges on transparent canvases.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SS = 4
ROOT = Path(__file__).resolve().parent.parent
FIGMA = ROOT / "reference" / "figma"


def rgba(c):
    if isinstance(c, tuple):
        return c if len(c) == 4 else (*c, 255)
    c = c.lstrip("#")
    a = int(c[6:8], 16) if len(c) == 8 else 255
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)


def mix(a, b, t):
    """Linear blend of two colours, t=0 gives a, t=1 gives b."""
    a, b = rgba(a), rgba(b)
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(4))


def blank(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def solid(w, h, color):
    return Image.new("RGBA", (w, h), rgba(color))


def _down(big, w, h):
    return big.convert("RGBa").resize((w, h), Image.Resampling.BOX).convert("RGBA")


def rrect(w, h, box, r, color):
    """Antialiased rounded rectangle on a transparent w x h canvas.
    box = (x0, y0, x1, y1) with exclusive x1/y1; fractional values are fine."""
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    ImageDraw.Draw(big).rounded_rectangle(
        (round(x0 * SS), round(y0 * SS), round(x1 * SS) - 1, round(y1 * SS) - 1),
        radius=round(r * SS), fill=rgba(color))
    return _down(big, w, h)


def poly(w, h, pts, color):
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    ImageDraw.Draw(big).polygon([(x * SS, y * SS) for x, y in pts], fill=rgba(color))
    return _down(big, w, h)


def ellipse(w, h, box, color):
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    ImageDraw.Draw(big).ellipse((x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - 1), fill=rgba(color))
    return _down(big, w, h)


def over(base, *layers):
    """Composite same-sized layers over base (returns a new image)."""
    out = base.copy()
    for layer in layers:
        out.alpha_composite(layer)
    return out


def paste(base, img, x, y):
    """Composite img onto base at (x, y), in place."""
    base.alpha_composite(img, (x, y))
    return base


def flatten(img, color):
    """Put img on an opaque background (for masks that must hide what is beneath)."""
    return over(solid(img.width, img.height, color), img)


def solidify(img, color):
    """Make every pixel either opaque or fully transparent.

    skins2 on Windows draws an image control into its own buffer as if over black and then
    copies it to the window, so a pixel with alpha a and colour c shows as c * (a/255)^2
    and nothing of what lies beneath (measured: white at a=64 renders 16, at 128 renders 64).
    So partly transparent pixels are composited here onto `color`, the surface the image
    will sit on; fully transparent ones stay transparent and still cut out shapes."""
    base = solid(img.width, img.height, color)
    base.alpha_composite(img)
    base.putalpha(img.getchannel("A").point(lambda v: 0 if v == 0 else 255))
    return base


def is_binary_alpha(img):
    lo_hi = {0, 255}
    return all(v in lo_hi for v, n in enumerate(img.getchannel("A").histogram()) if n)


def corner(r, color, which):
    """An r x r patch of `color` with a quarter-circle hole: laid over a rectangle's corner
    it rounds that corner. which: tl, tr, br or bl."""
    hole = rrect(4 * r, 4 * r, (0, 0, 4 * r, 4 * r), r, "#FFFFFF").getchannel("A")
    img = solid(4 * r, 4 * r, color)
    img.putalpha(hole.point(lambda v: 255 - v))
    box = {"tl": (0, 0, r, r), "tr": (3 * r, 0, 4 * r, r),
           "br": (3 * r, 3 * r, 4 * r, 4 * r), "bl": (0, 3 * r, r, 4 * r)}[which]
    return img.crop(box)


# --- text --------------------------------------------------------------------

# Inter, the design's typeface (SIL Open Font License, fonts/Inter-LICENSE.txt), from the
# official 4.1 release. skins2 loads only fonts shipped inside the skin, so these are bundled.
FONTS = ROOT / "fonts"
FONT_FILES = {"regular": FONTS / "Inter-Regular.ttf", "semibold": FONTS / "Inter-SemiBold.ttf"}
FONT_LICENSE = FONTS / "Inter-LICENSE.txt"


def rows_font(dst, size, row):
    """Write a copy of Inter Regular for playlist rows and return its path.

    skins2 draws each playlist row's text at the bottom of the row, so where the text sits
    depends only on the font's descender. This copy has a deeper descender, chosen so the
    capitals of `size`-pixel text sit in the middle of a `row`-pixel row. The glyphs are
    untouched; the family is renamed "Inter Rows", as a modified font should be (OFL)."""
    from fontTools.ttLib import TTFont
    f = TTFont(FONT_FILES["regular"], recalcTimestamp=False)   # same bytes every build
    upm, asc = f["head"].unitsPerEm, f["hhea"].ascent
    target = round((row - f["OS/2"].sCapHeight * size / upm) / 2)
    asc_px = asc * size / upm
    # FreeType rounds these metrics up, down or to nearest depending on the font's flags,
    # so pick a descender every rounding agrees on, with ascender + descender as well
    for units in range(round((target - .5) * upm / size), round(target * upm / size) + 1):
        d = units * size / upm
        if -((-d) // 1) == round(d) == target and round(asc_px + d + 1e-9) == -((-asc_px) // 1) + target:
            break
    else:
        raise ValueError(f"no clean descender for {size}px text in {row}px rows")
    f["hhea"].descent = -units
    f["OS/2"].sTypoDescender = -units
    f["OS/2"].usWinDescent = units
    for rec in f["name"].names:
        if rec.nameID in (1, 3, 4, 16, 6):
            old = rec.toUnicode()
            rec.string = old.replace("Inter-", "InterRows-") if rec.nameID == 6 else old.replace("Inter", "Inter Rows", 1)
    f.save(dst)
    return Path(dst)


def font(size, weight="regular"):
    return ImageFont.truetype(str(FONT_FILES[weight]), size)


def ascent(size, weight="regular"):
    """Pixels from the top of a skins2 Text control to its baseline (FreeType ascender)."""
    return font(size, weight).getmetrics()[0]


def text(img, x, baseline, s, size, color, weight="regular", align="left"):
    """Draw s with its baseline at y=baseline. align: left (x is the left edge),
    center (x is the centre) or right (x is the right edge). Modifies img."""
    f = font(size, weight)
    mask = Image.new("L", img.size, 0)
    anchor = {"left": "ls", "center": "ms", "right": "rs"}[align]
    ImageDraw.Draw(mask).text((x, baseline), s, font=f, fill=255, anchor=anchor)
    layer = Image.new("RGBA", img.size, rgba(color))
    alpha = Image.new("L", img.size, 0)
    alpha.paste(mask)
    if rgba(color)[3] != 255:
        alpha = alpha.point(lambda v: v * rgba(color)[3] // 255)
    layer.putalpha(alpha)
    img.alpha_composite(layer)
    return img


def text_width(s, size, weight="regular"):
    return round(font(size, weight).getlength(s))


# --- icons -------------------------------------------------------------------

# Top-left corner of each 24 x 24 symbol inside the Figma "Icon" component set
# (node 42:356, saved as reference/figma/icons-42_356.png at 1x).
ICONS = {
    "settings": (20, 20), "playback_settings": (108, 20), "preferences": (240, 20),
    "playlist": (328, 20), "playlist_active": (416, 20), "lists": (460, 20),
    "lists_active": (504, 20), "hotkeys": (20, 64), "subtitles": (152, 64),
    "subtitles_active": (240, 64), "audio": (284, 64), "audio_active": (372, 64),
    "play": (416, 64), "media": (460, 64), "pause": (108, 108), "next": (152, 108),
    "stop": (240, 108), "previous": (328, 108), "fwd10": (416, 108), "back10": (504, 108),
    "volume": (284, 152), "volume_medium": (328, 152), "volume_low": (372, 152),
    "mute": (416, 152), "close": (504, 152), "minimize": (20, 196), "maximize": (64, 196),
    "fullscreen": (108, 196), "fullscreen_exit": (152, 196), "home": (196, 196),
    "folder": (240, 196), "folder_active": (416, 196), "sidebar": (504, 196),
    "album": (64, 240), "music": (284, 240), "video": (328, 240), "streaming": (196, 284),
    "divider": (64, 328), "chevron_down": (108, 328), "arrow_right": (372, 328),
    "arrow_left": (460, 328), "open": (20, 372), "repeat": (64, 372),
    "repeat_active": (108, 372), "shuffle": (152, 372), "shuffle_active": (196, 372),
    "chevron_up": (240, 372), "chevron_right": (284, 372), "chevron_left": (328, 372),
    "more": (372, 372), "vlc": (416, 372), "add": (460, 372), "remove": (504, 372),
    "check": (372, 416), "sort": (416, 416), "search": (504, 416), "info": (284, 460),
    "file": (20, 504), "window": (196, 504), "grid": (460, 504), "list": (504, 504),
    "speed": (64, 548), "record": (152, 548), "snapshot": (284, 548), "queue": (328, 548),
    "eq": (372, 592), "save": (460, 680), "disc": (64, 724), "capture": (108, 724),
    "quit": (460, 724),
}


class Icons:
    def __init__(self, sheet=FIGMA / "icons-42_356.png"):
        self.sheet = Image.open(sheet).convert("RGBA")

    def raw(self, name):
        """The icon exactly as drawn in Figma (keeps two-tone and orange variants)."""
        x, y = ICONS[name]
        return self.sheet.crop((x, y, x + 24, y + 24))

    def tint(self, name, color):
        """The icon's shape in a single colour."""
        icon = self.raw(name)
        out = Image.new("RGBA", icon.size, rgba(color))
        a = icon.getchannel("A")
        if rgba(color)[3] != 255:
            a = a.point(lambda v: v * rgba(color)[3] // 255)
        out.putalpha(a)
        return out


# --- slider artwork ----------------------------------------------------------

def fill_strip(reach, height, color, tail=0):
    """Cursor image for the 'long cursor' fill trick: a strip `reach` pixels long that ends
    `tail` pixels right of the cursor centre, then transparency of equal length so the
    centre column (index reach) is where skins2 places the slider value."""
    w = 2 * reach + 1
    img = blank(w, height)
    img.paste(solid(reach + tail, height, color), (0, 0))
    return img


def volume_frames(theme, cols=9, rows=10):
    """SliderBackground frames for the wedge-shaped volume control (Figma 'volume', 244:184).

    Frame k shows the wedge filled to k/(n-1) of its width. The dark theme uses the
    Figma pixels directly: state '0' is the empty wedge and state '200%' the full gradient."""
    src = Image.open(FIGMA / "volume-244_184.png").convert("RGBA")
    empty = src.crop((21, 21, 109, 49))
    full = src.crop((21, 21 + 48 * 12, 109, 49 + 48 * 12))
    if theme["vol_track"]:
        a = empty.getchannel("A")
        empty_l = solid(88, 28, theme["vol_track"])
        empty_l.putalpha(a)
        lifted = full.copy()
        px, epx = lifted.load(), empty.load()
        for y in range(28):
            for x in range(88):
                r, g, b, al = px[x, y]
                er, eg, eb, _ = epx[x, y]
                diff = abs(r - er) + abs(g - eg) + abs(b - eb)
                if diff > 30:
                    c = mix((r, g, b, al), (255, 255, 255, al), theme["vol_fill_lift"])
                    px[x, y] = c
                else:
                    px[x, y] = (*rgba(theme["vol_track"])[:3], al)
        empty, full = empty_l, lifted
    w, h = empty.size
    n = cols * rows
    sheet = blank(w * cols, h * rows)    # row-major, the order skins2 reads frames in
    for k in range(n):
        frame = empty.copy()
        end = round(k * (w - 1) / (n - 1))
        if k:
            frame.paste(full.crop((0, 0, end + 1, h)), (0, 0))
        sheet.paste(frame, ((k % cols) * w, (k // cols) * h))
    return sheet
