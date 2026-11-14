#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10.1", "resvg-py>=0.1.5", "qrcode>=7.4", "python-bidi>=0.4"]
# ///
"""Design a label, preview it, and (only when asked) print it.

    render.py preview --text "Flat Ethernet Cable" --icon mdi:ethernet --printer ptouch -o /tmp/l.png
    render.py print   --text "Flat Ethernet Cable" --icon mdi:ethernet --printer ptouch --copies 2
    render.py preview --text "Hall" --icon lightbulb --media NIIMBOT-40x30 -o /tmp/n.png   # no printer needed
    render.py icons search "wine"            filled icons first
    render.py font "IBM Plex Sans Bold"      where that font resolves (downloads if missing)
    render.py style list | show NAME | save NAME [--font ...] | default NAME

`preview` never sends anything to a printer. For bridge and hub printers it does
ask what tape is loaded (a status read) unless --no-live is given.

Run with `uv run --script render.py ...` (installs Pillow, resvg-py, qrcode on the fly),
or plain python3 if those are already installed. Every command prints JSON.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backends  # noqa: E402
import design  # noqa: E402
from labelctl import load_catalogue, load_registry, repo_commit, resolve_paths, template_show  # noqa: E402

MAX_COPIES = 20


def out(obj, code=0):
    print(json.dumps(obj, indent=2, ensure_ascii=False))
    sys.exit(code)


# ---------------------------------------------------------------- styles
def styles_file() -> Path:
    return Path(resolve_paths()["styles"])


def load_styles() -> dict:
    p = styles_file()
    if p.exists():
        return json.loads(p.read_text())
    return {"default": "builtin", "styles": {}}


def save_styles(s: dict) -> str:
    p = styles_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n")
    repo_commit("styles: update", ["styles.json"])
    return str(p)


def style_for(name: str | None) -> dict:
    s = load_styles()
    name = name or s.get("default") or "builtin"
    if name == "builtin":
        return dict(design.BUILTIN_STYLE)
    if name not in s.get("styles", {}):
        sys.exit(f"no style '{name}'. Saved: {', '.join(s.get('styles', {})) or 'none'} (and 'builtin')")
    return {**design.BUILTIN_STYLE, **s["styles"][name]}


# ---------------------------------------------------------------- printers and geometry
def resolve_printer(pid: str | None) -> dict | None:
    printers = load_registry().get("printers", [])
    if pid:
        for p in printers:
            if p["id"] == pid or pid in p.get("aliases", []):
                return p
        sys.exit(f"no printer '{pid}'. Registered: {', '.join(p['id'] for p in printers) or 'none'}")
    live = [p for p in printers if not p.get("retired")]
    if len(live) == 1:
        return live[0]
    default = [p for p in live if p.get("default")]
    if len(default) == 1:
        return default[0]
    return None


def media_code(raw: str, family: str | None) -> str:
    cat = load_catalogue()
    if raw in cat["products"]:
        return raw
    if re.fullmatch(r"\d+x\d+", raw) and f"NIIMBOT-{raw}" in cat["products"]:
        return f"NIIMBOT-{raw}"
    m = re.fullmatch(r"(?:TZe-?)?(\d+(?:\.\d+)?)\s*mm", raw, re.I)
    if m:
        for code, prod in cat["products"].items():
            if prod["family"] == (family or "TZe") and prod["geometry"] == m.group(1):
                return code
    sys.exit(f"unknown media '{raw}': use a product code from `labelctl.py media list`, "
             f"'24mm' for tape, or '40x30' for NIIMBOT")


def geometry(printer: dict | None, media: str | None, live: bool, soft_media: str | None = None) -> tuple[dict, dict]:
    """media: forced (--media). soft_media: a template's media, used unless the printer reports otherwise."""
    cat = load_catalogue()
    fam = (printer or {}).get("media_family")
    note: dict = {}
    code = media_code(media, fam) if media else None
    max_px = None
    if not code and printer and live:
        lm = backends.live_media(printer)
        if lm is not None:
            note["live_media"] = lm
            if lm.get("tape_mm"):
                code = media_code(f"{lm['tape_mm']}mm", fam or "TZe")
                max_px = lm.get("max_px")
            elif lm.get("media"):
                code = media_code(str(lm["media"]), fam)
    if soft_media:
        want = media_code(soft_media, fam)
        if code and code != want:
            note["media_mismatch"] = f"template is for {want} but the printer reports {code}; rendered for {code}"
        elif not code:
            code = want
    if not code and printer and printer.get("installed_media"):
        code = media_code(printer["installed_media"], fam)
    if not code:
        sys.exit("no media: pass --media (e.g. TZe-251, 24mm, NIIMBOT-40x30, DK-22210) or set the printer's "
                 "installed_media with `labelctl.py registry set-media`")
    prod = cat["products"][code]
    if fam and prod["family"] != fam:
        sys.exit(f"{code} is {prod['family']} media; printer '{printer['id']}' takes {fam}.")
    g = cat["geometry"][prod["family"]][prod["geometry"]]
    dpi = cat["families"][prod["family"]]["dpi"]
    geo = {"product": code, "family": prod["family"], "geometry_name": prod["geometry"], "dpi": dpi,
           "two_color": bool(g.get("two_color")), "offset_mm": (printer or {}).get("offset_mm", 0)}
    if prod["family"] == "NIIMBOT":
        geo["canvas_w"], geo["canvas_h"] = g["canvas_px"]
        geo["printable_px"] = g["canvas_px"][0]
    elif "length_px" in g:      # DK die-cut: read along the label, head width is the height
        geo.update(canvas_w=g["length_px"], canvas_h=g["printable_px"], printable_px=g["printable_px"])
    else:                       # continuous
        px = max_px or g["printable_px"]
        geo.update(canvas_w=None, canvas_h=px, printable_px=px)
    return geo, note


# ---------------------------------------------------------------- label build
def build(args):
    soft_media = None
    if getattr(args, "template", None):
        tpl = template_show(args.template)
        if not args.media and tpl.get("media"):
            soft_media = tpl["media"]
        for f in ("text", "subtext", "qr", "icon", "layout", "style", "printer"):
            if not getattr(args, f, None) and tpl.get(f):
                setattr(args, f, tpl[f])
        if getattr(args, "copies", None) is None and tpl.get("copies"):
            args.copies = tpl["copies"]
    # --media without --printer is a design-only preview: don't let a lone registered printer
    # (with a different media family) hijack it.
    printer = resolve_printer(args.printer) if (args.printer or not (args.media or soft_media)) else None
    if printer and printer.get("retired"):
        sys.exit(f"printer '{printer['id']}' is retired: {printer.get('description', '')}")
    if not printer and not (args.media or soft_media):
        printers = load_registry().get("printers", [])
        sys.exit("name a printer with --printer (" + ", ".join(p["id"] for p in printers) + ") or pass --media "
                 "to design without one" if printers else "no printers registered: pass --media, or run the setup skill")
    st = style_for(args.style or (printer or {}).get("style"))
    for k, a in (("font", "font"), ("layout", "layout"), ("wrap_mm", "wrap_mm"), ("max_len_mm", "max_len_mm"),
                 ("margin_mm", "margin_mm")):
        v = getattr(args, a, None)
        if v is not None:
            st[k] = v
    if printer and printer.get("margin_mm") is not None and args.margin_mm is None:
        st["margin_mm"] = printer["margin_mm"]
    if args.invert:
        st["invert"] = True
    if args.border:
        st["border"] = True
    geo, note = geometry(printer, args.media, not args.no_live, soft_media)
    try:
        img, info = design.render_label(text=args.text or "", subtext=args.subtext or "", icon=args.icon,
                                        qr=args.qr or "", geo=geo, style=st)
    except design.DesignError as e:
        out({"ok": False, "error": str(e)}, 1)
    return printer, geo, img, {**note, **info}


def add_design_args(s):
    s.add_argument("--template", help="saved template; flags override its fields")
    s.add_argument("--text", "-t", help="label text; '\\n' forces a line break")
    s.add_argument("--subtext", help="smaller second line (continuous media >= ~14 mm)")
    s.add_argument("--icon", "-i", help="Iconify id, e.g. mdi:ethernet; a bare name uses the style's icon_prefix")
    s.add_argument("--qr", help="QR payload, drawn at the left")
    s.add_argument("--layout", choices=["auto", "one-line", "two-line", "text", "icon-top", "icon", "qr", "left"])
    s.add_argument("--style", help="saved style name (default: the user's default style)")
    s.add_argument("--font", help="font name ('IBM Plex Sans Bold', 'Inter SemiBold') or a .ttf path")
    s.add_argument("--wrap-mm", dest="wrap_mm", type=float)
    s.add_argument("--max-len-mm", dest="max_len_mm", type=float)
    s.add_argument("--margin-mm", dest="margin_mm", type=float)
    s.add_argument("--invert", action="store_true")
    s.add_argument("--border", action="store_true")
    s.add_argument("--printer", "-p")
    s.add_argument("--media", "-m")
    s.add_argument("--no-live", action="store_true", help="don't ask a bridge/hub printer what tape is loaded")


def main():
    ap = argparse.ArgumentParser(prog="render.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("preview")
    add_design_args(pv)
    pv.add_argument("-o", "--out", default="/tmp/label-preview.png")
    pr = sub.add_parser("print")
    add_design_args(pr)
    pr.add_argument("--copies", "-n", type=int, default=None)
    pr.add_argument("--no-cut", action="store_true")
    pr.add_argument("--save", help="also save the PNG that was sent")

    ic = sub.add_parser("icons").add_subparsers(dest="icmd", required=True)
    s = ic.add_parser("search")
    s.add_argument("query")
    s.add_argument("--prefixes", default="mdi,material-symbols,ph,tabler,fluent")
    s.add_argument("--limit", type=int, default=12)
    g = ic.add_parser("get")
    g.add_argument("id")

    f = sub.add_parser("font")
    f.add_argument("name")

    sty = sub.add_parser("style").add_subparsers(dest="scmd", required=True)
    sty.add_parser("list")
    ss = sty.add_parser("show")
    ss.add_argument("name")
    sd = sty.add_parser("default")
    sd.add_argument("name")
    sv = sty.add_parser("save")
    sv.add_argument("name")
    for k in ("font", "icon_prefix", "layout"):
        sv.add_argument(f"--{k.replace('_', '-')}", dest=k)
    for k in ("wrap_mm", "max_len_mm", "min_len_mm", "margin_mm", "line_gap"):
        sv.add_argument(f"--{k.replace('_', '-')}", dest=k, type=float)
    sv.add_argument("--invert", action="store_true", default=None)
    sv.add_argument("--border", action="store_true", default=None)
    sv.add_argument("--description")

    args = ap.parse_args()

    if args.cmd == "icons":
        if args.icmd == "search":
            out({"query": args.query, "icons": design.icon_search(args.query, args.prefixes, args.limit)})
        iid = design.icon_id(args.id, style_for(None)["icon_prefix"])
        design.icon_svg(iid)
        out({"id": iid, "cached": True})
    if args.cmd == "font":
        out({"name": args.name, **design.resolve_font(args.name)})
    if args.cmd == "style":
        s = load_styles()
        if args.scmd == "list":
            out({"file": str(styles_file()), "default": s.get("default", "builtin"),
                 "styles": {"builtin": design.BUILTIN_STYLE, **s.get("styles", {})}})
        if args.scmd == "show":
            out({"name": args.name, **style_for(args.name)})
        if args.scmd == "default":
            style_for(args.name)
            s["default"] = args.name
            out({"written": save_styles(s), "default": args.name})
        vals = {k: getattr(args, k) for k in ("font", "icon_prefix", "layout", "wrap_mm", "max_len_mm",
                                               "min_len_mm", "margin_mm", "line_gap", "invert", "border",
                                               "description") if getattr(args, k) is not None}
        s.setdefault("styles", {}).setdefault(args.name, {}).update(vals)
        out({"written": save_styles(s), "style": {args.name: s["styles"][args.name]}})

    printer, geo, img, info = build(args)
    base = {"printer": (printer or {}).get("id"), "media": geo["product"], **info}
    if args.cmd == "preview":
        img.save(args.out)
        out({"preview": args.out, "printed": False, **base})

    if not printer:
        sys.exit("print needs a registered printer (--printer)")
    copies = args.copies or 1
    if copies > MAX_COPIES:
        sys.exit(f"refusing more than {MAX_COPIES} copies in one call; media is consumable")
    if args.save:
        img.save(args.save)
    try:
        res = backends.send(img, printer, geo, copies, cut=not args.no_cut)
    except backends.BackendError as e:
        out({"printed": False, "error": str(e), **base}, 1)
    # `printed` is what the backend acknowledged. Several printers (P-touch, NIIMBOT) can
    # acknowledge a job that never leaves the printer: say so, and ask the user.
    out({"printed": bool(res.get("ok")), "copies": copies, **base, "result": res}, 0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
