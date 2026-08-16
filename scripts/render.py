#!/usr/bin/env python3
"""Render a label to PNG, and — only when explicitly asked — send it to a printer.

Unlike labelctl.py this needs Pillow, and qrcode (or the `qrencode` binary) for
QR labels. The `install-drivers` skill installs them.

    render.py preview --text "Spare fuses" --qr https://x/1 --printer ql-810w -o /tmp/l.png
    render.py print   --text "Spare fuses" --qr https://x/1 --printer ql-810w --copies 2

`preview` never opens a socket to the printer. That separation is deliberate:
`brother_ql print` converts *and* transmits in a single step with no dry-run
flag, so the only safe way to see a label first is to render it here and stop.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from labelctl import load_catalogue, load_registry, resolve_paths, template_show  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = PLUGIN_ROOT / "mcp-server" / "fonts"
FONT_BOLD = FONT_DIR / "Inter-ExtraBold.ttf"
FONT_REG = FONT_DIR / "Inter-Regular.ttf"
FONT_HE_BOLD = FONT_DIR / "NotoSansHebrew-Bold.ttf"
FONT_HE_REG = FONT_DIR / "NotoSansHebrew-Regular.ttf"

PAD = 8          # px margin inside the label
GAP = 12         # px between QR and text
MIN_LEN_MM = 20
# Continuous roll has no natural end, so without a cap the label grows to fit
# whatever type size the height allows — an 11-character heading on 29 mm tape
# came out 116 mm long before this existed. Text shrinks to fit this instead.
MAX_LEN_MM = 90


def need_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
        return Image, ImageDraw, ImageFont
    except ImportError:
        sys.exit(
            "Pillow is not installed. Run:  pip install --user Pillow qrcode\n"
            "or use the label-printer:install-drivers skill."
        )


def is_rtl(s: str) -> bool:
    return any("֐" <= c <= "ࣿ" for c in s or "")


def pick_font(text: str, bold: bool):
    if is_rtl(text):
        return FONT_HE_BOLD if bold else FONT_HE_REG
    return FONT_BOLD if bold else FONT_REG


def shape(text: str) -> str:
    """Reorder RTL runs for a renderer that does no bidi of its own."""
    if not is_rtl(text):
        return text
    try:
        from bidi.algorithm import get_display
        return get_display(text)
    except ImportError:
        return text[::-1]  # crude, but better than logical order on tape


def make_qr(data: str, px: int):
    Image, _, _ = need_pillow()
    try:
        import qrcode
        q = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
        q.add_data(data)
        q.make(fit=True)
        img = q.make_image(fill_color="black", back_color="white").convert("L")
    except ImportError:
        if not shutil.which("qrencode"):
            sys.exit("Need either the python `qrcode` package or the `qrencode` binary for QR labels.")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp = tf.name
        subprocess.run(["qrencode", "-o", tmp, "-m", "0", "-s", "8", data], check=True)
        img = Image.open(tmp).convert("L")
    return img.resize((px, px), Image.NEAREST)


def geometry_for(printer: dict, media: str | None) -> dict:
    """Resolve the pixel canvas for this printer's loaded media."""
    cat = load_catalogue()
    code = media or printer.get("installed_media")
    if not code:
        sys.exit(
            f"printer '{printer['id']}' has no installed_media recorded and none was "
            f"passed with --media. Set it: labelctl.py registry set-media --id {printer['id']} --media DK-22210"
        )
    prod = cat["products"].get(code)
    if not prod:
        sys.exit(f"unknown media '{code}' — see `labelctl.py media list`")
    # The same guard registry set-media applies. Without it here, --media can
    # override the registry with media the printer physically cannot take, and
    # the result is a plausible-looking canvas of entirely the wrong size.
    fam = printer.get("media_family")
    if fam and prod["family"] != fam:
        sys.exit(
            f"{code} is {prod['family']} media; printer '{printer['id']}' "
            f"({printer.get('model')}) takes {fam}. Loading it is physically impossible."
        )
    geo = dict(cat["geometry"][prod["family"]][prod["geometry"]])
    geo["product"] = code
    geo["family"] = prod["family"]
    geo["geometry_name"] = prod["geometry"]
    geo["two_color"] = bool(geo.get("two_color"))
    return geo


def render(text: str, subtext: str, qr: str, geo: dict):
    Image, ImageDraw, ImageFont = need_pillow()
    head_px = geo["printable_px"]           # across the print head
    die_cut = "length_px" in geo

    qr_px = max(0, head_px - 2 * PAD) if qr else 0
    # On a die-cut label the length is fixed, so a QR sized to the full head
    # width can swallow most of it and squeeze the text into a sliver. Cap it
    # at 45% of the label length; on continuous roll the label just grows, so
    # there is nothing to protect against.
    if qr and die_cut:
        qr_px = min(qr_px, int(geo["length_px"] * 0.45))
    qr_img = make_qr(qr, qr_px) if qr else None

    text_left = PAD + (qr_px + GAP if qr else 0)

    def fitted(s: str, bold: bool, box_h: int, box_w: int):
        """Largest size fitting box_h and box_w. Returns (font, w, h, top_offset).

        top_offset matters: PIL's draw.text() places the *ascender origin*, not
        the ink top, so drawing at y puts the glyph bbox at y+top. Ignoring it
        pushes descenders off the bottom of the label.
        """
        font_path = str(pick_font(s, bold))
        size = max(8, box_h)
        while size > 6:
            f = ImageFont.truetype(font_path, size)
            l, t, r, b = f.getbbox(s)
            if (b - t) <= box_h and (r - l) <= box_w:
                return f, r - l, b - t, t
            size -= 1
        f = ImageFont.truetype(font_path, 6)
        l, t, r, b = f.getbbox(s)
        return f, r - l, b - t, t

    body = shape(text)
    sub = shape(subtext) if subtext else ""
    avail_h = head_px - 2 * PAD
    # Two stacked lines only if the media is tall enough to read them. Below
    # roughly 18 mm the second line is not legible, so it is dropped.
    two_line = bool(sub) and head_px >= 120
    head_h = int(avail_h * 0.58) if two_line else avail_h
    sub_h = avail_h - head_h - 4 if two_line else 0

    dpi = load_catalogue()["families"][geo["family"]]["dpi"]
    if die_cut:
        total_w = geo["length_px"]
        box_w = total_w - text_left - PAD
    else:
        box_w = int(MAX_LEN_MM * dpi / 25.4) - text_left - PAD

    f1, w1, h1, t1 = fitted(body, True, head_h, box_w)
    f2 = w2 = h2 = t2 = None
    if two_line:
        f2, w2, h2, t2 = fitted(sub, False, sub_h, box_w)

    if not die_cut:
        total_w = text_left + max(w1, w2 or 0) + PAD
        total_w = max(int(MIN_LEN_MM * dpi / 25.4), total_w)

    canvas = Image.new("L", (total_w, head_px), 255)
    d = ImageDraw.Draw(canvas)
    if qr_img:
        canvas.paste(qr_img, (PAD, (head_px - qr_px) // 2))
    if two_line:
        d.text((text_left, PAD - t1), body, font=f1, fill=0)
        d.text((text_left, PAD + head_h + 4 - t2), sub, font=f2, fill=0)
    else:
        d.text((text_left, (head_px - h1) // 2 - t1), body, font=f1, fill=0)
    return canvas


def resolve_printer(pid: str | None) -> dict:
    reg = load_registry()
    printers = reg.get("printers", [])
    if not printers:
        sys.exit(
            "No printers registered. Run the label-printer:profile-printers skill, "
            "or: labelctl.py discover"
        )
    if pid:
        for p in printers:
            if p["id"] == pid:
                return p
        sys.exit(f"no printer with id '{pid}'. Registered: {', '.join(p['id'] for p in printers)}")
    if len(printers) == 1:
        return printers[0]
    sys.exit(
        "Several printers are registered — name one with --printer: "
        + ", ".join(f"{p['id']} ({p.get('description') or p.get('name')})" for p in printers)
    )


def send(img, printer: dict, geo: dict, copies: int, cut: bool) -> dict:
    Image, _, _ = need_pillow()
    backend = printer.get("backend")
    if backend in ("zebra_wip", "dymo_wip"):
        sys.exit(
            f"Backend '{backend}' is not implemented yet — this plugin can discover and "
            f"register {printer.get('model')} but cannot print to it. See docs/backends.md."
        )

    if backend in ("brother_ql_network", "brother_ql_usb"):
        # brother_ql wants the image at exactly the head width, and rasters it
        # down the tape. We render landscape, so rotate a quarter turn first.
        #
        # This is not cosmetic. brother_ql 0.9.4's conversion.py resizes with
        # Image.ANTIALIAS, which Pillow removed in 10.0 — so on any modern
        # Pillow a job that needs resizing dies with
        #   AttributeError: module 'PIL.Image' has no attribute 'ANTIALIAS'
        # Handing it an image already at dots_printable skips that branch
        # entirely, so this works regardless of the installed Pillow.
        img = img.rotate(-90, expand=True)
        want = geo["printable_px"]
        if img.size[0] != want:
            h = max(1, round(img.size[1] * want / img.size[0]))
            img = img.resize((want, h), Image.LANCZOS)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        png = tf.name
    img.save(png)

    if backend in ("brother_ql_network", "brother_ql_usb"):
        if not shutil.which("brother_ql"):
            sys.exit("brother_ql is not installed — see the install-drivers skill.")
        if backend == "brother_ql_network":
            ident = f"tcp://{printer['host']}:{printer.get('port', 9100)}"
            be = "network"
        else:
            ident = printer.get("usb_id_path") or f"usb://0x{printer['usb_id'].replace(':', '/0x')}"
            be = "pyusb"
        cmd = ["brother_ql", "-b", be, "-p", ident, "-m", printer["model"],
               "print", "-l", geo["geometry_name"]]
        if geo.get("two_color"):
            cmd.append("--red")
        if not cut:
            cmd.append("--no-cut")
        cmd.append(png)
        results = []
        for _ in range(copies):
            r = subprocess.run(cmd, capture_output=True, text=True)
            results.append({"rc": r.returncode, "stderr": r.stderr.strip()[-400:]})
            if r.returncode != 0:
                break
        return {"backend": backend, "identifier": ident, "copies": copies, "runs": results}

    if backend == "ptouch_usb":
        if not shutil.which("ptouch-print"):
            sys.exit("ptouch-print is not installed — see the install-drivers skill.")
        cmd = ["ptouch-print", "--copies", str(copies), "--image", png]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return {"backend": backend, "rc": r.returncode, "stderr": r.stderr.strip()[-400:]}

    if backend == "cups":
        q = printer.get("cups_queue")
        if not q:
            sys.exit(f"printer '{printer['id']}' has backend 'cups' but no cups_queue recorded.")
        r = subprocess.run(["lp", "-d", q, "-n", str(copies), png], capture_output=True, text=True)
        return {"backend": "cups", "queue": q, "rc": r.returncode,
                "stdout": r.stdout.strip(), "stderr": r.stderr.strip()[-400:]}

    sys.exit(f"unknown backend '{backend}'")


def main() -> None:
    ap = argparse.ArgumentParser(prog="render.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("preview", "print"):
        s = sub.add_parser(name)
        s.add_argument("--template", help="saved template name; --text etc. override its fields")
        s.add_argument("--text")
        s.add_argument("--subtext", default="")
        s.add_argument("--qr", default="")
        s.add_argument("--printer")
        s.add_argument("--media")
        if name == "preview":
            s.add_argument("-o", "--out", default="/tmp/label-preview.png")
        else:
            s.add_argument("--copies", type=int, default=1)
            s.add_argument("--no-cut", action="store_true")

    args = ap.parse_args()

    if args.template:
        tpl = template_show(args.template)
        for field in ("text", "subtext", "qr", "media", "printer"):
            if not getattr(args, field, None) and tpl.get(field):
                setattr(args, field, tpl[field])
    if not args.text:
        ap.error("--text is required (or supply a --template that carries one)")

    printer = resolve_printer(args.printer)
    geo = geometry_for(printer, args.media)
    img = render(args.text, args.subtext, args.qr, geo)

    if args.cmd == "preview":
        img.save(args.out)
        print(json.dumps({
            "preview": args.out, "printer": printer["id"], "model": printer.get("model"),
            "media": geo["product"], "canvas_px": list(img.size),
            "printed": False,
        }, indent=2))
        return

    if args.copies > 20:
        sys.exit("Refusing more than 20 copies in one call — tape and rolls are consumable.")
    out = send(img, printer, geo, args.copies, cut=not args.no_cut)
    # Report what happened, not what was attempted. `runs` is per-copy for the
    # brother_ql backends; the others report a single rc.
    rcs = [r["rc"] for r in out.get("runs", [])] or [out.get("rc", 0)]
    ok = all(rc == 0 for rc in rcs)
    print(json.dumps({"printer": printer["id"], "media": geo["product"],
                      "canvas_px": list(img.size), "printed": ok,
                      "copies_sent": sum(1 for rc in rcs if rc == 0),
                      "result": out}, indent=2))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
