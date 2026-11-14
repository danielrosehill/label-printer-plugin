#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10.1"]
# ///
"""The curated label font library (fonts/library.json): list it, fetch fonts, pre-fetch defaults.

    fonts.py list [--script latin|hebrew]     the library, with what is already available
    fonts.py fetch "Secular One"              resolve one font (installed, cached or downloaded)
    fonts.py prefetch                         the user's style fonts + the library defaults
    fonts.py prefetch --all                   every font in the library (~30 MB)
    fonts.py check                            is libraqm available (correct Hebrew/Arabic shaping)?

Fonts are not shipped in the repo: they are OFL Google Fonts (IBM Plex from IBM's repo),
downloaded on first use into ~/.cache/label-printer/fonts. Every command prints JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import design  # noqa: E402

LIBRARY = Path(__file__).resolve().parent.parent / "fonts" / "library.json"
WEIGHT_NAMES = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black"}


def load() -> dict:
    return json.loads(LIBRARY.read_text())


def font_name(entry: dict) -> str:
    return f"{entry['family']} {WEIGHT_NAMES.get(entry.get('weight', 700), 'Bold')}"


def style_fonts() -> list[str]:
    """Fonts named in the user's styles.json (Label-Templates repo or user-data dir)."""
    try:
        from labelctl import resolve_paths
        p = Path(resolve_paths()["styles"])
        styles = json.loads(p.read_text()).get("styles", {}) if p.exists() else {}
    except Exception:  # noqa: BLE001
        styles = {}
    out = []
    for st in styles.values():
        out += [st[k] for k in ("font", "font_hebrew") if st.get(k)]
    return out


def main():
    ap = argparse.ArgumentParser(prog="fonts.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--script", choices=["latin", "hebrew"])
    f = sub.add_parser("fetch")
    f.add_argument("name")
    pf = sub.add_parser("prefetch")
    pf.add_argument("--all", action="store_true")
    sub.add_parser("check")
    a = ap.parse_args()
    lib = load()

    if a.cmd == "list":
        out = {}
        for script in ([a.script] if a.script else ["latin", "hebrew"]):
            out[script] = [{**e, "name": font_name(e),
                            "available": design.resolve_font(font_name(e), allow_download=False)["source"] != "fallback"}
                           for e in lib[script]]
        print(json.dumps({"defaults": lib["defaults"], **out}, indent=2, ensure_ascii=False))
    elif a.cmd == "fetch":
        print(json.dumps({"name": a.name, **design.resolve_font(a.name)}, indent=2))
    elif a.cmd == "prefetch":
        names = [lib["defaults"]["latin"], lib["defaults"]["hebrew"]] + style_fonts()
        if a.all:
            names += [font_name(e) for s in ("latin", "hebrew") for e in lib[s]]
        seen, res = set(), []
        for n in names:
            if n in seen:
                continue
            seen.add(n)
            r = design.resolve_font(n)
            res.append({"name": n, "source": r["source"], "path": r["path"]})
        bad = [r for r in res if r["source"].startswith("fallback")]
        print(json.dumps({"fonts": res, "failed": len(bad), "raqm": design.has_raqm()}, indent=2))
        sys.exit(1 if bad else 0)
    else:
        ok = design.has_raqm()
        print(json.dumps({"raqm": ok, "note": "Hebrew and mixed text are shaped by libraqm" if ok else
                          "libraqm missing: falling back to python-bidi reordering (correct order, no complex "
                          "shaping). Pillow's PyPI wheels bundle raqm (run render.py via uv); with a distro "
                          "Pillow install libraqm0 / libraqm (Debian/Ubuntu: sudo apt install libraqm0)."}, indent=2))


if __name__ == "__main__":
    main()
