"""Label design: fonts, icons, media geometry and layouts -> a 1-bit PIL image.

Nothing in here talks to a printer. render.py composes this with backends.py.

Canvas convention: the image is always in *reading* orientation.
  continuous tape/roll  height = printable px across the head, width grows with content
  die-cut label         fixed width x height as the label is read
Backends rotate or pad as their transport needs (brother_ql wants it rotated).

Fonts are resolved by name ("IBM Plex Sans Bold", "Inter SemiBold", or a file path):
installed fonts (fontconfig) -> this plugin's font cache -> download (IBM Plex from
IBM's repo, anything else from Google Fonts) -> the bundled Inter ExtraBold.
Icons are Iconify ids (prefix:name), fetched once and cached.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BUNDLED = PLUGIN_ROOT / "mcp-server" / "fonts"
FALLBACK_FONT = BUNDLED / "Inter-ExtraBold.ttf"
HEBREW_FONT = BUNDLED / "NotoSansHebrew-Bold.ttf"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "label-printer"
UA = {"User-Agent": "label-printer/2 (label renderer)"}

# Defaults every style starts from. A user's styles.json overrides these.
BUILTIN_STYLE = {
    "font": "IBM Plex Sans Bold",
    "icon_prefix": "mdi",        # bare icon names resolve here; mdi icons are filled
    "layout": "auto",            # auto | one-line | two-line | text | icon-top | icon | qr
    "wrap_mm": 85,               # continuous media: wrap one line to two past this length
    "max_len_mm": 160,           # continuous media: shrink text rather than exceed this
    "min_len_mm": 20,
    "margin_mm": 1.5,            # die-cut media: inner margin
    "line_gap": 0.12,
    "invert": False,
    "border": False,
}

WEIGHTS = {"thin": 100, "extralight": 200, "light": 300, "regular": 400, "text": 450,
           "medium": 500, "semibold": 600, "bold": 700, "extrabold": 800, "black": 900}
PLEX_NAMES = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 450: "Text",
              500: "Medium", 600: "SemiBold", 700: "Bold", 800: "Bold", 900: "Bold"}


class DesignError(ValueError):
    pass


def _fetch(url: str, timeout: int = 20, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- fonts
def parse_font_name(name: str) -> tuple[str, int]:
    """'IBM Plex Sans Bold' -> ('IBM Plex Sans', 700). No weight word means Bold."""
    words = name.strip().split()
    if words and words[-1].lower().replace("-", "") in WEIGHTS:
        return " ".join(words[:-1]), WEIGHTS[words[-1].lower().replace("-", "")]
    return name.strip(), 700


def _fc_lookup(family: str, weight: int) -> str | None:
    if not shutil.which("fc-match"):
        return None
    # fontconfig weights: 80 regular, 100 medium, 180 semibold, 200 bold, 205 extrabold, 210 black
    fcw = {100: 0, 200: 40, 300: 50, 400: 80, 450: 80, 500: 100, 600: 180, 700: 200, 800: 205, 900: 210}[weight]
    try:
        out = subprocess.run(["fc-match", "-f", "%{family}|%{weight}|%{file}", f"{family}:weight={fcw}"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    fams, w, path = (out.split("|") + ["", "", ""])[:3]
    # fc-match always answers with *something*; only accept the family asked for at that weight.
    if family.lower() not in [f.strip().lower() for f in fams.split(",")]:
        return None
    try:
        if abs(int(float(w)) - fcw) > 10:
            return None
    except ValueError:
        return None
    return path if Path(path).exists() else None


def _download_font(family: str, weight: int) -> Path:
    d = CACHE / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{re.sub(r'[^A-Za-z0-9]+', '', family)}-{weight}.ttf"
    if target.exists():
        return target
    if family.lower().startswith("ibm plex"):
        # IBM Plex ships per-family folders: plex-sans, plex-mono, plex-sans-condensed, plex-serif ...
        slug = family.lower().replace("ibm ", "").replace(" ", "-")
        fname = family.replace("IBM ", "IBM").replace(" ", "") + f"-{PLEX_NAMES[weight]}.ttf"
        url = f"https://github.com/IBM/plex/raw/master/packages/{slug}/fonts/complete/ttf/{fname}"
        target.write_bytes(_fetch(url, timeout=60))
        return target
    # Google Fonts: an old-browser User-Agent makes css2 answer with plain TTF URLs.
    q = urllib.parse.quote_plus(family)
    css = _fetch(f"https://fonts.googleapis.com/css2?family={q}:wght@{weight}",
                 headers={"User-Agent": "Wget/1.21"}).decode()
    m = re.search(r"url\((https://[^)]+\.ttf)\)", css)
    if not m:
        raise DesignError(f"font '{family}' not found on Google Fonts")
    target.write_bytes(_fetch(m.group(1), timeout=60))
    return target


def resolve_font(name: str | None, *, allow_download: bool = True) -> dict:
    """Return {'path', 'source'} for a font name or file path."""
    name = name or BUILTIN_STYLE["font"]
    p = Path(os.path.expanduser(name))
    if p.suffix.lower() in (".ttf", ".otf") and p.exists():
        return {"path": str(p), "source": "file"}
    family, weight = parse_font_name(name)
    hit = _fc_lookup(family, weight)
    if hit:
        return {"path": hit, "source": "installed"}
    cached = CACHE / "fonts" / f"{re.sub(r'[^A-Za-z0-9]+', '', family)}-{weight}.ttf"
    if cached.exists():
        return {"path": str(cached), "source": "cache"}
    if allow_download:
        try:
            return {"path": str(_download_font(family, weight)), "source": "downloaded"}
        except Exception as e:  # noqa: BLE001 - any failure falls back to the bundled font
            return {"path": str(FALLBACK_FONT), "source": f"fallback ({family}: {e})"}
    return {"path": str(FALLBACK_FONT), "source": "fallback"}


def is_rtl(s: str) -> bool:
    return any("֐" <= c <= "ࣿ" for c in s or "")


def shape(s: str) -> str:
    if not is_rtl(s):
        return s
    try:
        from bidi.algorithm import get_display
        return get_display(s)
    except ImportError:
        return s[::-1]


# ---------------------------------------------------------------- icons
def icon_id(raw: str, prefix: str = "mdi") -> str:
    return raw if ":" in raw else f"{prefix}:{raw}"


def icon_svg(iid: str) -> str:
    prefix, name = iid.split(":", 1)
    d = CACHE / "icons"
    d.mkdir(parents=True, exist_ok=True)
    cached = d / f"{prefix}__{name}.svg"
    if cached.exists():
        return cached.read_text()
    try:
        svg = _fetch(f"https://api.iconify.design/{prefix}/{name}.svg?color=%23000000").decode()
    except Exception as e:  # noqa: BLE001
        raise DesignError(f"icon {iid}: {e}") from e
    if not svg.lstrip().startswith("<svg"):
        raise DesignError(f"icon not found: {iid}")
    cached.write_text(svg)
    return svg


def icon_image(iid: str, size: int) -> Image.Image:
    try:
        import resvg_py
    except ImportError as e:
        raise DesignError("icons need the resvg-py package (run render.py through `uv run --script`)") from e
    png = bytes(resvg_py.svg_to_bytes(svg_string=icon_svg(iid), width=size, height=size))
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    return Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("L")


OUTLINE = re.compile(r"(-outline|-outlined|-line|-thin|-light|-duotone)(-|$)")


def icon_search(query: str, prefixes: str = "mdi,material-symbols,ph,tabler,fluent", limit: int = 12) -> list[dict]:
    """Iconify search, filled icons first (they print solid; outlines print faint)."""
    q = urllib.parse.urlencode({"query": query, "limit": 64, "prefixes": prefixes})
    icons = json.loads(_fetch(f"https://api.iconify.design/search?{q}")).get("icons", [])
    order = {p: i for i, p in enumerate(prefixes.split(","))}

    def rank(i: str):
        p, n = i.split(":", 1)
        return (bool(OUTLINE.search(n)), order.get(p, 99), len(n))

    return [{"id": i, "filled": not OUTLINE.search(i.split(":", 1)[1]),
             "preview": f"https://api.iconify.design/{i}.svg"} for i in sorted(icons, key=rank)[:limit]]


# ---------------------------------------------------------------- QR
def qr_image(data: str, px: int) -> Image.Image:
    try:
        import qrcode
        q = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
        q.add_data(data)
        q.make(fit=True)
        img = q.make_image(fill_color="black", back_color="white").convert("L")
    except ImportError:
        if not shutil.which("qrencode"):
            raise DesignError("QR labels need the python `qrcode` package or the `qrencode` binary")
        out = subprocess.run(["qrencode", "-o", "-", "-m", "0", "-s", "8", data], capture_output=True, check=True)
        img = Image.open(io.BytesIO(out.stdout)).convert("L")
    return img.resize((px, px), Image.NEAREST)


# ---------------------------------------------------------------- text fitting
def split_lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").replace("\\n", "\n").split("\n") if ln.strip()]


def _font_for(line: str, fp: str, size: int):
    return ImageFont.truetype(str(HEBREW_FONT) if is_rtl(line) else fp, size)


def _measure(lines, fp, size, gap_ratio):
    boxes = [_font_for(ln, fp, size).getbbox(shape(ln)) for ln in lines]
    w = max(b[2] - b[0] for b in boxes)
    h = sum(b[3] - b[1] for b in boxes) + int(size * gap_ratio) * (len(lines) - 1)
    return w, h, boxes


def fit(lines, fp, max_w, max_h, gap_ratio=0.12) -> tuple[int, int, int]:
    """Largest font size whose block fits max_w x max_h. Returns (size, w, h)."""
    lo, hi, best = 6, 600, (6, *_measure(lines, fp, 6, gap_ratio)[:2])
    while lo <= hi:
        mid = (lo + hi) // 2
        w, h, _ = _measure(lines, fp, mid, gap_ratio)
        if w <= max_w and h <= max_h:
            best, lo = (mid, w, h), mid + 1
        else:
            hi = mid - 1
    return best


def draw_block(d, lines, fp, size, box, gap_ratio=0.12, align="center"):
    x0, y0, bw, bh = box
    gap = int(size * gap_ratio)
    _, tot, boxes = _measure(lines, fp, size, gap_ratio)
    y = y0 + (bh - tot) // 2
    for ln, b in zip(lines, boxes):
        f = _font_for(ln, fp, size)
        lw = b[2] - b[0]
        x = x0 + ((bw - lw) // 2 if align == "center" else 0)
        d.text((x - b[0], y - b[1]), shape(ln), font=f, fill=0)
        y += (b[3] - b[1]) + gap


def two_line_splits(line: str) -> list[list[str]]:
    words = line.split()
    return [[" ".join(words[:i]), " ".join(words[i:])] for i in range(1, len(words))]


# ---------------------------------------------------------------- layouts
def finish(img: Image.Image, invert: bool, border: bool) -> Image.Image:
    if border:
        d = ImageDraw.Draw(img)
        r = max(4, img.height // 12)
        d.rounded_rectangle((1, 1, img.width - 2, img.height - 2), radius=r, outline=0, width=max(2, img.height // 60))
    img = img.point(lambda p: 0 if p < 128 else 255).convert("1")
    if invert:
        img = ImageOps.invert(img.convert("L")).convert("1")
    return img


def render_continuous(lines, sub, icon, qr, geo, st, fp) -> tuple[Image.Image, dict]:
    """Tape / continuous roll: fixed height, length grows with the content."""
    h = geo["canvas_h"]
    dpmm = geo["dpi"] / 25.4
    pad = max(2, h // 16)
    inner = h - 2 * pad
    gap_ratio = st["line_gap"]
    layout = st["layout"]
    slots = []  # (kind, value) squares on the left
    if qr:
        slots.append(("qr", qr))
    if icon and layout not in ("text",):
        slots.append(("icon", icon))
    if layout == "icon" and icon:
        lines, sub = [], ""
    sq = inner
    lead = pad + len(slots) * (sq + pad * 2)
    max_text_w = int(st["max_len_mm"] * dpmm) - lead - pad
    wrap_px = int(st["wrap_mm"] * dpmm)

    note = {}
    if sub and h < 100:
        note["subtext_dropped"] = f"{h}px media is too short for a second, smaller line; put it in --text"
        sub = ""
    main_h = int(inner * 0.6) if sub else inner
    sub_h = inner - main_h - pad if sub else 0

    choice = lines
    if lines:
        cands = [lines]
        if len(lines) == 1 and " " in lines[0] and layout in ("auto", "two-line"):
            cands += two_line_splits(lines[0])
        if layout == "two-line" and len(cands) > 1:
            cands = cands[1:]
        if layout == "one-line":
            cands = [[" ".join(lines)]]
        scored = []
        for c in cands:
            size, w, _ = fit(c, fp, 10**6, main_h, gap_ratio)
            scored.append((c, size, w))
        one = scored[0]
        if layout == "auto" and len(lines) == 1 and lead + one[2] + pad > wrap_px and len(scored) > 1:
            # Wrap: of the two-line splits, the one giving the shortest label.
            choice = min(scored[1:], key=lambda s: s[2])[0]
            note["wrapped"] = f"one line would be {round((lead + one[2] + pad) / dpmm)} mm > wrap_mm {st['wrap_mm']}"
        elif layout == "two-line" and scored:
            choice = min(scored, key=lambda s: s[2])[0]
        else:
            choice = one[0]
    size, tw, _ = fit(choice, fp, max_text_w, main_h, gap_ratio) if choice else (0, 0, 0)
    sw = ssize = 0
    if sub:
        ssize, sw, _ = fit([sub], fp, max_text_w, sub_h, gap_ratio)
    text_w = max(tw, sw)
    w = lead + text_w + pad if choice or sub else pad + len(slots) * (sq + pad * 2) - pad
    w = max(w, int(st["min_len_mm"] * dpmm))
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    x = pad
    for kind, val in slots:
        img.paste(qr_image(val, sq) if kind == "qr" else icon_image(val, sq), (x, pad))
        x += sq + pad * 2
    # Text sits centred in what is left, so a min-length label does not look lopsided.
    tx = lead
    tbox_w = w - lead - pad
    if choice:
        draw_block(d, choice, fp, size, (tx, pad, tbox_w, main_h), gap_ratio)
    if sub:
        draw_block(d, [sub], fp, ssize, (tx, pad + main_h + pad, tbox_w, sub_h), gap_ratio)
    note["lines"] = choice
    return img, note


def render_diecut(lines, sub, icon, qr, geo, st, fp) -> tuple[Image.Image, dict]:
    """Fixed-size label (NIIMBOT rolls, DK die-cut). Port of the niimbot-labels layouts."""
    w, h = geo["canvas_w"], geo["canvas_h"]
    dpmm = geo["dpi"] / 25.4
    m = round(st["margin_mm"] * dpmm)
    iw, ih = w - 2 * m, h - 2 * m
    gap_ratio = st["line_gap"]
    lines = lines + ([sub] if sub else [])
    layout = st["layout"]
    if layout in ("one-line", "two-line"):
        layout = "auto"
    if layout == "auto":
        if qr:
            layout = "qr"
        elif icon and lines:
            layout = "left" if w >= 1.6 * h else "icon-top"
        elif icon:
            layout = "icon"
        else:
            layout = "text"
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)

    def text_in(box):
        if not lines:
            return None
        cands = [lines]
        if len(lines) == 1 and " " in lines[0]:
            cands += two_line_splits(lines[0])
        size, use = max(((fit(c, fp, box[2], box[3], gap_ratio)[0], c) for c in cands), key=lambda t: t[0])
        draw_block(d, use, fp, size, box, gap_ratio)
        return use

    used = None
    if layout == "icon" and icon:
        s = min(iw, ih)
        img.paste(icon_image(icon, s), (m + (iw - s) // 2, m + (ih - s) // 2))
    elif layout in ("left", "qr") and (icon or qr):
        s = min(ih, int(iw * 0.5))
        sq = qr_image(qr, s) if (layout == "qr" and qr) else icon_image(icon, s)
        img.paste(sq, (m, m + (ih - s) // 2))
        g = round(1.5 * dpmm)
        used = text_in((m + s + g, m, iw - s - g, ih))
    elif layout == "icon-top" and icon:
        s = min(int(ih * 0.45), iw)
        img.paste(icon_image(icon, s), (m + (iw - s) // 2, m))
        g = round(1 * dpmm)
        used = text_in((m, m + s + g, iw, ih - s - g))
    else:
        used = text_in((m, m, iw, ih))
    dx = round(float(geo.get("offset_mm") or 0) * dpmm)  # print-position calibration, negative = left
    if dx:
        shifted = Image.new("L", (w, h), 255)
        shifted.paste(img, (dx, 0))
        img = shifted
    return img, {"layout": layout, "lines": used}


def render_label(*, text: str = "", subtext: str = "", icon: str | None = None, qr: str = "",
                 geo: dict, style: dict) -> tuple[Image.Image, dict]:
    st = {**BUILTIN_STYLE, **{k: v for k, v in style.items() if v is not None}}
    lines = split_lines(text)
    iid = icon_id(icon, st["icon_prefix"]) if icon else None
    if not lines and not iid and not qr:
        raise DesignError("nothing to print: give text, an icon or a QR payload")
    font = resolve_font(st["font"])
    fn = render_continuous if geo.get("canvas_w") is None else render_diecut
    img, note = fn(lines, subtext or "", iid, qr, geo, st, font["path"])
    img = finish(img, st["invert"], st["border"])
    dpmm = geo["dpi"] / 25.4
    info = {"canvas_px": list(img.size), "size_mm": [round(img.width / dpmm, 1), round(img.height / dpmm, 1)],
            "font": font, "icon": iid, **note}
    return img, info
