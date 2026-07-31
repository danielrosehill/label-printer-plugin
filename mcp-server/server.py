"""label-printer — MCP server for Brother P-touch label printers on Linux.

Renders label images with PIL (+ qrcode) and hands them to a print bridge over
HTTP; the bridge drives `ptouch-print` over USB and cuts the blank leader off
each label. Set PRINT_BRIDGE_URL to point at the bridge.

The bridge and the hardware notes live in:
  https://github.com/danielrosehill/ptouch-cube-print-bridge

Labels are landscape strips: the tape width is the label's *height*, and the
label runs arbitrarily long along the tape. Everything here is rendered at
12 px/mm (~305 dpi) and downscaled by the bridge to the 180 dpi print head.
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

import qrcode
from PIL import Image, ImageDraw, ImageFont
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Image as MCPImage
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,
    allowed_hosts=["*"],
    allowed_origins=["*"],
)
mcp = FastMCP("label-printer", transport_security=_security)

# No private address baked in: deployments set this. The gateway compose points
# it at the LAN host the printer is wired to.
BRIDGE_URL = os.environ.get("PRINT_BRIDGE_URL", "http://127.0.0.1:9180")

SCALE = 12                      # px per mm; the bridge downscales to the head
PAD_MM = 1.5
MAX_W_MM = 120                  # hard cap on label length, guards runaway tape
MAX_COPIES = 20                 # matches the bridge's own cap
MAX_BATCH = 50                  # distinct labels per batch call
MAX_IMAGE_BYTES = 8 * 1024 * 1024   # decoded size cap on submitted artwork
# MAX_W_MM guards the auto-layout against stretching tape to fit a long string.
# Submitted artwork is composed deliberately at a known length, so it gets a
# looser bound — still finite, to catch a wrong-aspect image before it prints.
MAX_IMAGE_W_MM = 300

# QR labels aim for a uniform length; long names wrap rather than stretch the
# tape. The label only grows past this if the heading itself won't fit legibly.
PREF_W_MM = int(os.environ.get("LABEL_WIDTH_MM", "62"))
SUBTEXT_MAX_LINES = 2
MIN_SUBTEXT_MM = 2.0            # legibility floor for the wrapped name

FONT_BOLD = os.environ.get("FONT_BOLD", "/app/fonts/Inter-ExtraBold.ttf")
FONT_REGULAR = os.environ.get("FONT_REGULAR", "/app/fonts/Inter-Regular.ttf")

# Inter carries no Hebrew glyphs, so Hebrew text falls back to Noto Sans Hebrew.
FONT_HEBREW_BOLD = os.environ.get("FONT_HEBREW_BOLD", "/app/fonts/NotoSansHebrew-Bold.ttf")
FONT_HEBREW_REGULAR = os.environ.get("FONT_HEBREW_REGULAR", "/app/fonts/NotoSansHebrew-Regular.ttf")

# Template prefixes — applied only when the id doesn't already carry one.
ASSET_PREFIX = os.environ.get("ASSET_PREFIX", "A-")
STORAGE_PREFIX = os.environ.get("STORAGE_PREFIX", "S-")

# Fallback when the printer is off and can't report its tape.
DEFAULT_TAPE_MM = int(os.environ.get("LABEL_TAPE_MM", "24"))
# Below this, there is no room for a second line under the heading.
SUBTEXT_MIN_TAPE_MM = 18

_TAPE_CACHE: dict[str, Any] = {"mm": None, "at": 0.0}
_TAPE_TTL = 60.0


# --------------------------------------------------------------------------
# bridge transport
# --------------------------------------------------------------------------

def _bridge(path: str, payload: dict | None = None, timeout: int = 90) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{BRIDGE_URL}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": f"bridge HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"bridge unreachable at {BRIDGE_URL}: {e}"}


def _tape_mm() -> int:
    """Loaded tape width, cached briefly. Falls back if the printer is off."""
    now = time.time()
    if _TAPE_CACHE["mm"] and now - _TAPE_CACHE["at"] < _TAPE_TTL:
        return _TAPE_CACHE["mm"]
    info = _bridge("/health", timeout=15)
    mm = info.get("tapeMm") if info.get("ok") else None
    mm = int(mm) if mm else DEFAULT_TAPE_MM
    _TAPE_CACHE.update({"mm": mm, "at": now})
    return mm


def _to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _print_image(img: Image.Image, copies: int) -> dict[str, Any]:
    data_url = "data:image/png;base64," + base64.b64encode(_to_png_bytes(img)).decode()
    result = _bridge("/print", {"imageDataUrl": data_url, "copies": copies})
    result.setdefault("labelPx", [img.width, img.height])
    return result


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _is_rtl(text: str) -> bool:
    """True if the string contains Hebrew or Arabic letters."""
    return any(0x0590 <= ord(c) <= 0x08FF or 0xFB1D <= ord(c) <= 0xFDFF for c in text)


def _shape(text: str) -> str:
    """Logical order -> visual order for RTL text.

    Pillow is built without raqm here, so it lays glyphs out left-to-right and
    will not apply the bidi algorithm itself. We apply it, and pin the layout
    engine to BASIC below so a raqm-enabled Pillow can't reorder a second time
    and undo this.
    """
    if not _is_rtl(text):
        return text
    try:
        from bidi import get_display  # python-bidi >= 0.5
    except ImportError:
        try:
            from bidi.algorithm import get_display  # python-bidi < 0.5
        except ImportError:
            return text
    return get_display(text)


def _font_paths(*texts: str) -> tuple[str, str]:
    """(bold, regular) font paths, switched to the Hebrew faces when needed."""
    if any(_is_rtl(t) for t in texts):
        return FONT_HEBREW_BOLD, FONT_HEBREW_REGULAR
    return FONT_BOLD, FONT_REGULAR


def _truetype(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)  # noqa: E501


def _fit_font(draw: ImageDraw.ImageDraw, text: str, path: str, max_w: int, max_h: int) -> ImageFont.FreeTypeFont:
    """Largest font size at which `text` fits on one line inside the box."""
    size = max(8, int(max_h))
    while size > 8:
        font = _truetype(path, size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_w and box[3] - box[1] <= max_h:
            return font
        size -= 2
    return _truetype(path, 8)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str] | None:
    """Greedy word wrap. None if any single word is too wide at this size."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        if draw.textlength(word, font=font) > max_w:
            return None
        trial = f"{cur} {word}".strip()
        if cur and draw.textlength(trial, font=font) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or None


def _fit_wrapped(
    draw: ImageDraw.ImageDraw, text: str, path: str, max_w: int, max_h: int, max_lines: int
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Largest font whose fully wrapped lines fit the box; ellipsize as a last resort."""
    floor = max(8, round(MIN_SUBTEXT_MM * SCALE))
    for size in range(max(floor, int(max_h)), floor - 1, -2):
        font = _truetype(path, size)
        lines = _wrap(draw, text, font, max_w)
        if lines and len(lines) <= max_lines and len(lines) * size * 1.2 <= max_h:
            return font, lines

    font = _truetype(path, floor)
    lines = _wrap(draw, text, font, max_w) or [text]
    lines = lines[:max_lines]
    if len(lines) < len(_wrap(draw, text, font, max_w) or lines):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last + "…"
    return font, lines


def _render(heading: str, subtext: str = "", qr_url: str = "", tape_mm: int | None = None) -> Image.Image:
    """Render one label.

    With `qr_url`: QR square on the left, heading (and optional subtext) right.
    Without it: heading centred, `\\n` splitting it into up to 3 stacked lines.
    """
    tape_mm = tape_mm or _tape_mm()
    h = tape_mm * SCALE
    pad = round(PAD_MM * SCALE)
    max_w = MAX_W_MM * SCALE
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    bold_path, regular_path = _font_paths(heading, subtext)

    # Narrow tape has no room for a second line.
    if tape_mm < SUBTEXT_MIN_TAPE_MM:
        subtext = ""

    if not qr_url:
        lines = [ln.strip() for ln in heading.split("\n") if ln.strip()][:3]
        if subtext:
            lines = (lines + [subtext])[:3]
        line_h = (h - 2 * pad) // len(lines)
        fonts = [_fit_font(probe, ln, bold_path, max_w - 2 * pad, round(line_h * 0.8)) for ln in lines]
        widths = [probe.textbbox((0, 0), ln, font=f)[2] for ln, f in zip(lines, fonts)]
        w = min(max_w, max(widths) + 2 * pad + SCALE)
        img = Image.new("L", (w, h), 255)
        draw = ImageDraw.Draw(img)
        for i, (ln, font) in enumerate(zip(lines, fonts)):
            draw.text((w // 2, pad + line_h * i + line_h // 2), _shape(ln), font=font, fill=0, anchor="mm")
        return img

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_side = h - 2 * pad
    qr_img = qr.make_image(fill_color="black", back_color="white").resize(
        (qr_side, qr_side), Image.NEAREST
    )

    # Fixed-width text column keeps labels uniform; long names wrap instead of
    # stretching the tape. Only a heading that can't fit legibly widens it.
    heading = heading.replace("\n", " ").strip()
    tx_start = pad + qr_side + 2 * SCALE
    avail_h = h - 2 * pad
    head_h = round(avail_h * 0.55) if subtext else avail_h
    gap = round(0.8 * SCALE)

    tw = max(PREF_W_MM * SCALE - pad - tx_start, 10 * SCALE)
    head_font = _fit_font(probe, heading, bold_path, tw, head_h)
    # If shrinking to fit made the heading illegible, widen the label instead.
    if head_font.size < head_h * 0.55:
        want = _fit_font(probe, heading, bold_path, max_w, head_h)
        needed = round(probe.textlength(heading, font=want))
        tw = min(needed, max_w - pad - tx_start)
        head_font = _fit_font(probe, heading, bold_path, tw, head_h)

    w = min(max_w, tx_start + tw + pad)
    img = Image.new("L", (w, h), 255)
    img.paste(qr_img, (pad, pad))
    draw = ImageDraw.Draw(img)

    if subtext:
        sub_h = avail_h - head_h - gap
        sub_font, lines = _fit_wrapped(draw, subtext, regular_path, tw, sub_h, SUBTEXT_MAX_LINES)
        draw.text((tx_start + tw // 2, pad + head_h // 2), _shape(heading), font=head_font, fill=0, anchor="mm")
        line_h = sub_h / len(lines)
        for i, line in enumerate(lines):
            cy = pad + head_h + gap + round(line_h * (i + 0.5))
            draw.text((tx_start + tw // 2, cy), _shape(line), font=sub_font, fill=0, anchor="mm")
    else:
        draw.text((tx_start + tw // 2, h // 2), _shape(heading), font=head_font, fill=0, anchor="mm")
    return img


# --------------------------------------------------------------------------
# submitted artwork
#
# The text renderer above picks one font per label, so a label mixing scripts
# (Latin + Hebrew, say) gets whichever face matches the RTL test and shows tofu
# for everything that face doesn't cover. Rather than grow a per-run font
# fallback, callers that need full control render their own image and submit it.
# --------------------------------------------------------------------------

FIT_MODES = ("scale", "pad", "exact")


def _decode_image(data: str) -> Image.Image:
    """Decode submitted artwork from a data: URL or a bare base64 string."""
    if not data or not data.strip():
        raise ValueError("image is empty")
    payload = data.strip()
    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")
        if not payload:
            raise ValueError("malformed data URL: nothing after the comma")
    payload = "".join(payload.split())    # tolerate wrapped/newline-padded base64
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"image is not valid base64: {e}") from e
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"image is {len(raw) // 1024} KiB, over the {MAX_IMAGE_BYTES // 1024} KiB cap"
        )
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"not a readable image: {e}") from e
    return img


def _flatten(img: Image.Image) -> Image.Image:
    """Composite transparency onto white, then reduce to greyscale.

    Without this an RGBA design prints as a solid black slab: a transparent
    background converts straight to black rather than to bare tape.
    """
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        img = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba)
    return img.convert("L")


def _fit_to_tape(img: Image.Image, tape_mm: int, fit: str) -> Image.Image:
    """Bring submitted artwork to the tape height, and refuse runaway lengths."""
    if fit not in FIT_MODES:
        raise ValueError(f"fit must be one of: {', '.join(FIT_MODES)}")
    h = tape_mm * SCALE

    if fit == "exact":
        if img.height != h:
            raise ValueError(
                f"image is {img.width}x{img.height}px, but the loaded {tape_mm}mm tape "
                f"needs a height of exactly {h}px — call label_canvas(), or use fit='scale'"
            )
    elif fit == "scale":
        if img.height != h:
            img = img.resize((max(1, round(img.width * h / img.height)), h), Image.LANCZOS)
    else:  # pad — keep the design's own scale, centre it across the tape
        if img.height > h:
            img = img.resize((max(1, round(img.width * h / img.height)), h), Image.LANCZOS)
        elif img.height < h:
            canvas = Image.new("L", (img.width, h), 255)
            canvas.paste(img, (0, (h - img.height) // 2))
            img = canvas

    if img.width > MAX_IMAGE_W_MM * SCALE:
        raise ValueError(
            f"label would run {img.width / SCALE:.0f}mm, over the {MAX_IMAGE_W_MM}mm cap; "
            "shorten the design or make it less wide relative to its height"
        )
    return img


def _prepare_image(image: str, fit: str) -> Image.Image:
    return _fit_to_tape(_flatten(_decode_image(image)), _tape_mm(), fit)


def _clamp_copies(copies: int) -> int:
    return min(MAX_COPIES, max(1, int(copies)))


def _prefixed(value: str, prefix: str) -> str:
    """Apply a template prefix unless the id already carries one."""
    value = value.strip()
    if not prefix or value.upper().startswith(prefix.upper()):
        return value
    return f"{prefix}{value}"


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------

@mcp.tool()
def printer_status() -> dict[str, Any]:
    """Check the label printer: bridge reachability, loaded tape width, errors.

    P-touch printers auto-power-off when idle and cannot be woken over USB, so
    an unavailable result usually means someone must press the power button.
    """
    return _bridge("/health", timeout=15)


@mcp.tool()
def printer_capabilities() -> dict[str, Any]:
    """What this printer setup can and cannot do — check before promising a setting.

    `ptouch-print` is a print-only driver. It exposes no device settings at all:
    auto-power-off, Bluetooth and NVRAM options are unreachable from Linux and
    can only be changed with Brother's Windows/macOS Printer Setting Tool.
    """
    live = _bridge("/health", timeout=15)
    return {
        "bridgeUrl": BRIDGE_URL,
        "live": live,
        "renderer": {
            "scalePxPerMm": SCALE,
            "maxLabelLengthMm": MAX_W_MM,
            "maxCopiesPerJob": MAX_COPIES,
            "maxBatchLabels": MAX_BATCH,
            "subtextRequiresTapeMm": SUBTEXT_MIN_TAPE_MM,
            "colour": "1-bit black on tape; no greyscale, no colour",
        },
        "imageSubmission": {
            "tool": "print_image_label",
            "canvasTool": "label_canvas",
            "accepts": "PNG or JPEG, as a data: URL or a bare base64 string",
            "maxDecodedBytes": MAX_IMAGE_BYTES,
            "maxLengthMm": MAX_IMAGE_W_MM,
            "fitModes": list(FIT_MODES),
            "whenToUse": (
                "Anything the text renderer cannot express. It selects a single "
                "font per label, so a label mixing scripts shows tofu for the "
                "glyphs that face lacks — render it yourself and submit it."
            ),
        },
        "driverExposes": [
            "copies", "font", "font-size", "font-margin", "align", "image",
            "text", "newline", "pad", "cutmark", "precut", "chain",
            "info", "list-supported", "write-png", "force-tape-width", "timeout",
        ],
        "driverDoesNotExpose": {
            "autoPowerOff": (
                "Not settable from Linux. ptouch-print has no device-settings "
                "support, Bluetooth cannot carry device settings, and the mobile "
                "apps do not expose it. Use Brother's Printer Setting Tool "
                "(Device Settings > Basic > Auto Power Off = None) on Windows or "
                "macOS over USB; the value is stored in printer NVRAM and "
                "survives reboots. Wine does not work — the tool reaches the "
                "printer through a Windows kernel-mode driver."
            ),
            "otherDeviceSettings": (
                "Bluetooth pairing, auto-cut defaults and tape-feed settings are "
                "likewise Setting-Tool-only."
            ),
            "tapeRemaining": "The printer does not report remaining tape length.",
        },
    }


@mcp.tool()
def preview_label(heading: str, subtext: str = "", qr_url: str = "") -> MCPImage:
    """Render a label and return the image WITHOUT printing it. Use to check
    layout, wrapping and QR size before spending tape.

    Args:
        heading: Big bold text. Without a QR, \\n splits it into up to 3 lines.
        subtext: Optional smaller line under the heading (needs 18mm+ tape).
        qr_url: If set, encoded as a QR code on the left of the label.
    """
    if not heading.strip() and not qr_url:
        raise ValueError("heading is required (or provide qr_url)")
    return MCPImage(data=_to_png_bytes(_render(heading, subtext, qr_url)), format="png")


@mcp.tool()
def print_label(heading: str, subtext: str = "", qr_url: str = "", copies: int = 1) -> dict[str, Any]:
    """Print a single label, optionally with a QR code and in several copies.

    This is the general-purpose tool. For inventory work prefer
    `print_asset_label` or `print_storage_label`, which apply the id conventions.

    Args:
        heading: Big bold text. Without a QR, \\n splits it into up to 3 lines.
        subtext: Optional smaller line under the heading (needs 18mm+ tape).
        qr_url: If set, encoded as a QR code on the left of the label.
        copies: Number of identical labels (1-20), each cut separately.
    """
    if not heading.strip() and not qr_url:
        return {"ok": False, "error": "heading is required (or provide qr_url)"}
    return _print_image(_render(heading, subtext, qr_url), _clamp_copies(copies))


@mcp.tool()
def print_text_label(text: str, copies: int = 1) -> dict[str, Any]:
    """Print a text-only label, no QR. Use \\n for up to 3 stacked lines.

    Args:
        text: Label text; newlines split it into stacked, auto-sized lines.
        copies: Number of identical labels (1-20), each cut separately.
    """
    if not text.strip():
        return {"ok": False, "error": "text is empty"}
    return _print_image(_render(text), _clamp_copies(copies))


@mcp.tool()
def label_canvas() -> dict[str, Any]:
    """The exact pixel canvas to render your own label artwork onto.

    Call this before generating a design for `print_image_label`. The tape width
    is the label's HEIGHT; the label runs as long as you like along the tape, up
    to the length cap.
    """
    tape_mm = _tape_mm()
    return {
        "tapeMm": tape_mm,
        "heightPx": tape_mm * SCALE,
        "maxWidthPx": MAX_IMAGE_W_MM * SCALE,
        "maxLengthMm": MAX_IMAGE_W_MM,
        "scalePxPerMm": SCALE,
        "colour": "1-bit black on tape — render black on white; greyscale is thresholded",
        "notes": (
            "Match heightPx exactly, or let fit='scale' resize for you. Flatten "
            "transparency onto white. The bridge downscales to the 180 dpi head "
            "and trims the blank leader, so no margins are needed at the ends."
        ),
    }


@mcp.tool()
def preview_image_label(image: str, fit: str = "scale") -> MCPImage:
    """Return submitted artwork exactly as it would reach the printer, without printing.

    Use this to check scaling and cropping before spending tape.

    Args:
        image: PNG or JPEG artwork, as a data: URL or a bare base64 string.
        fit: How to reconcile the artwork height with the tape — see `print_image_label`.
    """
    return MCPImage(data=_to_png_bytes(_prepare_image(image, fit)), format="png")


@mcp.tool()
def print_image_label(image: str, copies: int = 1, fit: str = "scale") -> dict[str, Any]:
    """Print arbitrary artwork as a label — a PNG or JPEG you rendered yourself.

    Use this when the built-in text and QR layouts can't express the design:
    mixed scripts on one line, logos, custom typography, multi-column layouts.
    Call `label_canvas()` first for the pixel canvas to draw onto.

    Args:
        image: PNG or JPEG artwork, as a data: URL or a bare base64 string.
        copies: Number of identical labels (1-20), each cut separately.
        fit: "scale" resizes proportionally to the tape height (default);
            "pad" keeps the artwork's own scale and centres it across the tape;
            "exact" refuses artwork whose height isn't already the tape height.
    """
    try:
        img = _prepare_image(image, fit)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return _print_image(img, _clamp_copies(copies))


@mcp.tool()
def print_asset_label(asset_id: str, name: str = "", url: str = "", copies: int = 1) -> dict[str, Any]:
    """Print an inventory ASSET label: QR left, asset id big, item name under it.

    The asset id is prefixed (default "A-") unless it already carries the prefix,
    so `100` prints as `A-100`.

    Args:
        asset_id: Asset number, e.g. "100" or "A-100".
        name: Item name shown under the id, e.g. "Instant Pot".
        url: Link encoded in the QR code — the item's page in your inventory system.
        copies: Number of identical labels (1-20), each cut separately.
    """
    if not asset_id.strip():
        return {"ok": False, "error": "asset_id is required"}
    return _print_image(
        _render(_prefixed(asset_id, ASSET_PREFIX), name.strip(), url.strip()),
        _clamp_copies(copies),
    )


@mcp.tool()
def print_storage_label(unit_id: str, contents: str = "", url: str = "", copies: int = 1) -> dict[str, Any]:
    """Print a STORAGE UNIT label: QR left, box/shelf id big, contents under it.

    The unit id is prefixed (default "S-") unless it already carries the prefix,
    so `3` prints as `S-3`.

    Args:
        unit_id: Storage unit id, e.g. "3" or "S-003".
        contents: Short description of what's inside, e.g. "Cables & adapters".
        url: Link encoded in the QR code — the unit's page in your inventory system.
        copies: Number of identical labels (1-20), each cut separately.
    """
    if not unit_id.strip():
        return {"ok": False, "error": "unit_id is required"}
    return _print_image(
        _render(_prefixed(unit_id, STORAGE_PREFIX), contents.strip(), url.strip()),
        _clamp_copies(copies),
    )


class BatchLabel(BaseModel):
    """One label in a batch run."""

    heading: str = Field(description="Big bold text, e.g. an asset id")
    subtext: str = Field(default="", description="Optional smaller line underneath")
    qr_url: str = Field(default="", description="If set, encoded as a QR code on the left")
    copies: int = Field(default=1, description="Copies of this label (1-20)")


@mcp.tool()
def print_batch(labels: list[BatchLabel]) -> dict[str, Any]:
    """Print a batch of DIFFERENT labels in one run, each cut separately.

    Use this for labelling a whole shelf or a box of items at once, rather than
    calling the single-label tools repeatedly. Stops at the first failure and
    reports how many labels were printed before it.

    Args:
        labels: Up to 50 label specs, printed in order.
    """
    if not labels:
        return {"ok": False, "error": "no labels given"}
    if len(labels) > MAX_BATCH:
        return {"ok": False, "error": f"batch too large: {len(labels)} > {MAX_BATCH}"}

    results: list[dict[str, Any]] = []
    for i, spec in enumerate(labels):
        if not spec.heading.strip() and not spec.qr_url.strip():
            return {
                "ok": False,
                "error": f"label {i}: heading is required (or provide qr_url)",
                "printed": results,
            }
        r = _print_image(
            _render(spec.heading, spec.subtext.strip(), spec.qr_url.strip()),
            _clamp_copies(spec.copies),
        )
        results.append({"heading": spec.heading, "copies": r.get("copies"), "ok": r.get("ok", False)})
        if not r.get("ok"):
            return {
                "ok": False,
                "error": f"label {i} ({spec.heading!r}) failed: {r.get('error')}",
                "printedBefore": len(results) - 1,
                "results": results,
            }
    total = sum(_clamp_copies(s.copies) for s in labels)
    return {"ok": True, "labels": len(labels), "totalPrinted": total, "results": results}


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "streamable_http")
    if transport == "streamable_http":
        mcp.settings.host = os.environ.get("MCP_HTTP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("MCP_HTTP_PORT", "3000"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
