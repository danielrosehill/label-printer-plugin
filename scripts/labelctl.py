#!/usr/bin/env python3
"""Discover label printers, keep a registry of them, and look up label media.

Python 3 standard library only — no install step. Rendering and printing need
Pillow and (optionally) qrcode; those live in render.py, which is a separate
script precisely so that discovery and the registry keep working on a bare box.

Subcommands:
    paths                       where config, registry, styles and templates resolve to
    repo status|set|create|commit   the user's Label-Templates repository
    discover [--json]           find label printers on this machine and LAN
    registry list|add|remove|show|set-media
    template list|save|show|remove
    media list|show <name>      the bundled DK/TZe/NIIMBOT catalogue
    backends                    which print backends are usable here

Two registries are merged, machine entries winning on the same id:
  machine  ~/.claude-plugins/label-printer/printers.json   USB and LAN printers true on this box only;
           never committed
  shared   <user-data>/label-printer/printers.json         printers reachable from every machine the
           user has (a print hub or bridge on a VPN); `registry add --shared` writes here
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

PLUGIN = "label-printer"
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = PLUGIN_ROOT / "reference" / "media-catalogue.json"

# Brother USB ids we can name on sight. lsusb gives us vid:pid and nothing else
# useful, so this table is how a bare `04f9:20af` becomes "PT-P710BT".
USB_IDS = {
    "04f9:209b": "QL-700",
    "04f9:209c": "QL-810W",
    "04f9:209d": "QL-820NWB",
    "04f9:2042": "QL-500",
    "04f9:2015": "QL-570",
    "04f9:20af": "PT-P710BT",
    "04f9:20e0": "PT-P750W",
    "04f9:2061": "PT-P700",
}

# model -> backend. Deciding this at discovery time is what lets `print` stay
# printer-agnostic later on.
def backend_for(model: str, host: str | None) -> str:
    m = (model or "").upper()
    if m.startswith("QL"):
        return "brother_ql_network" if host else "brother_ql_usb"
    if m.startswith("PT"):
        return "ptouch_usb"
    if re.match(r"^(ZD|ZT|GK|GX|ZQ)", m):
        return "zebra_wip"
    if "LABELWRITER" in m or m.startswith("LW"):
        return "dymo_wip"
    if media_family_for(m) == "NIIMBOT":
        return "http_bridge"  # niimblue-node bridge; see docs/niimbot.md
    return "cups"


def media_family_for(model: str) -> str | None:
    m = (model or "").upper()
    if m.startswith("QL"):
        return "DK"
    if m.startswith("PT"):
        return "TZe"
    if re.match(r"^(B1|B21|B3S|D11|D110|D101)\b", m) or "NIIMBOT" in m:
        return "NIIMBOT"
    return None


def load_catalogue() -> dict:
    with CATALOGUE.open() as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# paths — mirrors scripts/paths.sh so Python callers need not shell out
# --------------------------------------------------------------------------
def resolve_paths() -> dict:
    home = Path.home()

    def guard(p: Path) -> Path:
        claude = home / ".claude"
        if p == claude or claude in p.parents:
            sys.exit(f"{PLUGIN}: refusing path inside ~/.claude: {p}")
        return p

    if os.environ.get("LABEL_PRINTER_CONFIG_DIR"):
        config_dir, config_source = Path(os.environ["LABEL_PRINTER_CONFIG_DIR"]), "env-override"
    else:
        config_dir, config_source = home / ".claude-plugins" / PLUGIN, "default"

    xdg_root = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "claude-plugins"
    if os.environ.get("LABEL_PRINTER_DATA"):
        data_root, data_source = Path(os.environ["LABEL_PRINTER_DATA"]), "env-override"
    elif os.environ.get("CLAUDE_USER_DATA"):
        data_root, data_source = Path(os.environ["CLAUDE_USER_DATA"]), "claude-user-data"
    elif (home / ".claude-user-data").is_dir():
        data_root, data_source = home / ".claude-user-data", "adopted-existing"
    elif xdg_root.is_dir():
        data_root, data_source = xdg_root, "adopted-existing"
    else:
        data_root, data_source = home / ".claude-user-data", "default"

    data_dir = data_root / PLUGIN
    guard(config_dir)
    guard(data_dir)
    # The user's Label-Templates repository, when they have one, holds the shared printer
    # registry, styles and templates. The user-data dir then only stores its path.
    repo = None
    cfg = data_dir / "config.json"
    if os.environ.get("LABEL_TEMPLATES_REPO"):
        repo = Path(os.path.expanduser(os.environ["LABEL_TEMPLATES_REPO"]))
    elif cfg.exists():
        try:
            raw = json.loads(cfg.read_text()).get("label_templates_repo")
            repo = Path(os.path.expanduser(raw)) if raw else None
        except ValueError:
            repo = None
    if repo is not None and not (repo / "templates").is_dir():
        repo = None  # configured but not cloned here: fall back rather than write into nothing
    home_dir = repo or data_dir
    return {
        "config_dir": str(config_dir),
        "config_file": str(config_dir / "printers.json"),
        "config_source": config_source,
        "data_root": str(data_root),
        "data_dir": str(data_dir),
        "repo": str(repo) if repo else None,
        "shared_registry": str(home_dir / "printers.json"),
        "styles": str(home_dir / "styles.json"),
        "templates": str(home_dir / "templates"),
        "data_source": data_source,
    }


# --------------------------------------------------------------------------
# the Label-Templates repository
# --------------------------------------------------------------------------
TEMPLATE_REPO = "danielrosehill/Label-Templates-Template"


def repo_commit(message: str, paths: list[str] | None = None) -> dict:
    """Commit and push changes in the user's Label-Templates repo. No-op without one."""
    repo = resolve_paths()["repo"]
    if not repo:
        return {"committed": False, "reason": "no Label-Templates repo configured"}
    paths = paths or ["printers.json", "printers.md", "styles.json", "templates"]
    paths = [x for x in paths if (Path(repo) / x).exists()]
    git = ["git", "-C", repo]
    subprocess.run(git + ["add", "--", *paths], capture_output=True)
    if subprocess.run(git + ["diff", "--cached", "--quiet"]).returncode == 0:
        return {"committed": False, "reason": "nothing changed"}
    c = subprocess.run(git + ["commit", "-q", "-m", message], capture_output=True, text=True)
    if c.returncode:
        return {"committed": False, "error": c.stderr.strip()[-300:]}
    pu = subprocess.run(git + ["push", "-q"], capture_output=True, text=True)
    return {"committed": True, "pushed": pu.returncode == 0, **({"push_error": pu.stderr.strip()[-300:]} if pu.returncode else {})}


def repo_set(path: str) -> None:
    p = Path(os.path.expanduser(path)).resolve()
    if not (p / "templates").is_dir():
        sys.exit(f"{p} does not look like a Label-Templates repo (no templates/)")
    d = Path(resolve_paths()["data_dir"])
    d.mkdir(parents=True, exist_ok=True)
    cfg = d / "config.json"
    data = json.loads(cfg.read_text()) if cfg.exists() else {}
    data["label_templates_repo"] = str(p).replace(str(Path.home()), "~", 1)
    cfg.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({"written": str(cfg), **data}, indent=2))


def repo_create(name: str, parent: str, public: bool, owner: str | None) -> None:
    if not shutil.which("gh"):
        sys.exit("gh (GitHub CLI) is needed to create the repo from the template")
    full = f"{owner}/{name}" if owner else name
    par = Path(os.path.expanduser(parent))
    par.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["gh", "repo", "create", full, "--template", TEMPLATE_REPO,
                        "--public" if public else "--private", "--clone"],
                       cwd=par, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr.strip())
    repo_set(str(par / name))


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------
def _run(cmd: list[str], timeout: int = 12) -> str:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def discover_mdns() -> list[dict]:
    """Label printers advertising over mDNS.

    Deliberately not `brother_ql discover`: that only ever walks USB, and in
    0.9.4 it raises NotImplementedError unless -b precedes the subcommand.
    Deliberately not `lpstat`: a network label printer is usually not a CUPS
    queue at all — the QL-810W this was written against is reachable on :9100
    and absent from CUPS entirely.
    """
    if not shutil.which("avahi-browse"):
        return []
    out = _run(["avahi-browse", "-atrp"], timeout=15)
    found: dict[str, dict] = {}
    for line in out.splitlines():
        if not line.startswith("="):
            continue
        f = line.split(";")
        if len(f) < 10:
            continue
        name, hostname, addr, port = f[3], f[6], f[7], f[8]
        txt = ";".join(f[9:])
        if ":" in addr:  # skip IPv6, the v4 record carries the same TXT
            continue
        model = ""
        m = re.search(r'"usb_MDL=([^"]+)"', txt) or re.search(r'"ty=([^"]+)"', txt)
        if m:
            model = m.group(1).replace("Brother ", "").strip()
        is_label = "kind=label" in txt or re.match(r"^(QL|PT|ZD|ZT|GK|GX|ZQ)", model.upper())
        if not is_label:
            continue
        key = addr
        if key not in found:
            found[key] = {
                "via": "mdns",
                "name": name.replace("\\032", " "),
                "model": model,
                "host": addr,
                "hostname": hostname.rstrip("."),
                "port": 9100,
                "raw_port_9100": _tcp_open(addr, 9100),
            }
    return list(found.values())


def discover_usb() -> list[dict]:
    if not shutil.which("lsusb"):
        return []
    out = _run(["lsusb"], timeout=8)
    found = []
    for line in out.splitlines():
        m = re.search(r"ID ([0-9a-f]{4}:[0-9a-f]{4})\s*(.*)", line)
        if not m:
            continue
        vidpid, desc = m.group(1), m.group(2).strip()
        if vidpid in USB_IDS:
            found.append(
                {
                    "via": "usb",
                    "name": desc or USB_IDS[vidpid],
                    "model": USB_IDS[vidpid],
                    "usb_id": vidpid,
                    "host": None,
                }
            )
        elif vidpid.startswith("04f9:"):  # a Brother we do not have in the table
            found.append(
                {
                    "via": "usb",
                    "name": desc or "Unknown Brother",
                    "model": "",
                    "usb_id": vidpid,
                    "host": None,
                    "note": "Brother device not in the known-id table; confirm the model by hand.",
                }
            )
    return found


def discover_cups() -> list[dict]:
    if not shutil.which("lpstat"):
        return []
    out = _run(["lpstat", "-v"], timeout=8)
    found = []
    for line in out.splitlines():
        m = re.match(r"device for (\S+?): (.+)", line.strip())
        if not m:
            continue
        queue, uri = m.group(1), m.group(2)
        if re.search(r"(QL|PT|ptouch|label|zebra|dymo)", queue + uri, re.I):
            found.append({"via": "cups", "name": queue, "model": "", "cups_queue": queue, "uri": uri, "host": None})
    return found


def _tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def discover() -> list[dict]:
    results = discover_mdns() + discover_usb() + discover_cups()
    for r in results:
        r["suggested_backend"] = backend_for(r.get("model", ""), r.get("host"))
        r["media_family"] = media_family_for(r.get("model", ""))
        r["suggested_id"] = _slug(r.get("model") or r.get("name") or "printer")
    return results


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
def _registry_file(shared: bool = False) -> Path:
    paths = resolve_paths()
    return Path(paths["shared_registry"] if shared else paths["config_file"])


def load_registry(scope: str = "merged") -> dict:
    """scope: merged (what printing uses) | machine | shared."""
    def read(p: Path) -> dict:
        if not p.exists():
            return {"bridge": {"name": socket.gethostname(), "location": ""}, "printers": []}
        with p.open() as fh:
            return json.load(fh)

    if scope != "merged":
        return read(_registry_file(scope == "shared"))
    machine, shared = read(_registry_file()), read(_registry_file(True))
    ids = {p["id"] for p in machine["printers"]}
    for p in shared["printers"]:
        if p["id"] not in ids:
            machine["printers"].append({**p, "scope": "shared"})
    return machine


def save_registry(reg: dict, shared: bool = False) -> str:
    p = _registry_file(shared)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(reg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    tmp.replace(p)
    if shared:
        repo_commit(f"printers: update {p.name}", ["printers.json"])
    return str(p)


def registry_add(args) -> None:
    reg = load_registry("shared" if args.shared else "machine")
    if any(p["id"] == args.id for p in reg["printers"]):
        sys.exit(f"printer id '{args.id}' already registered — use `registry remove` first")
    entry = {
        "id": args.id,
        "name": args.name or args.id,
        "model": args.model,
        "backend": args.backend or backend_for(args.model, args.host),
        "description": args.description or "",
    }
    if args.host:
        entry["host"] = args.host
        entry["port"] = args.port
    if args.usb_id:
        entry["usb_id"] = args.usb_id
    if args.cups_queue:
        entry["cups_queue"] = args.cups_queue
    if args.media:
        entry["installed_media"] = args.media
    for k in ("url", "target", "bridge_type", "serial_port", "style"):
        if getattr(args, k, None):
            entry[k] = getattr(args, k)
    for k in ("offset_mm", "margin_mm", "density"):
        if getattr(args, k, None) is not None:
            entry[k] = getattr(args, k)
    if args.cups_option:
        entry["cups_options"] = args.cups_option
    if args.alias:
        entry["aliases"] = args.alias
    if args.default:
        entry["default"] = True
    fam = media_family_for(args.model)
    if fam:
        entry["media_family"] = fam
    reg["printers"].append(entry)
    print(json.dumps({"written": save_registry(reg, args.shared), "printer": entry}, indent=2))


def _scope_of(pid: str) -> bool:
    """True if the id lives only in the shared registry."""
    machine = {p["id"] for p in load_registry("machine")["printers"]}
    shared = {p["id"] for p in load_registry("shared")["printers"]}
    return pid in shared and pid not in machine


def registry_set_media(args) -> None:
    shared = _scope_of(args.id)
    reg = load_registry("shared" if shared else "machine")
    cat = load_catalogue()
    if args.media not in cat["products"]:
        sys.exit(f"unknown media '{args.media}' — see `labelctl.py media list`")
    for p in reg["printers"]:
        if p["id"] == args.id:
            fam = cat["products"][args.media]["family"]
            if p.get("media_family") and p["media_family"] != fam:
                sys.exit(
                    f"{args.media} is {fam} media; printer '{args.id}' takes "
                    f"{p['media_family']}. Loading it is physically impossible."
                )
            p["installed_media"] = args.media
            print(json.dumps({"written": save_registry(reg, shared), "printer": p}, indent=2))
            return
    sys.exit(f"no printer with id '{args.id}'")


def registry_remove(args) -> None:
    shared = _scope_of(args.id)
    reg = load_registry("shared" if shared else "machine")
    before = len(reg["printers"])
    reg["printers"] = [p for p in reg["printers"] if p["id"] != args.id]
    if len(reg["printers"]) == before:
        sys.exit(f"no printer with id '{args.id}'")
    print(json.dumps({"written": save_registry(reg, shared), "removed": args.id}, indent=2))


# --------------------------------------------------------------------------
# templates — user content, so these live under the user-data root, not the
# vault. A template is a label you print repeatedly with one field changing.
# --------------------------------------------------------------------------
def templates_dir() -> Path:
    return Path(resolve_paths()["templates"])


def _find_template(name: str) -> Path:
    """'shelf-bin' or 'ptouch-24mm/shelf-bin'; folders are optional when the name is unique."""
    d = templates_dir()
    parts = name.split("/")
    if len(parts) > 1:
        p = d / _slug(parts[0]) / f"{_slug(parts[-1])}.json"
        if p.exists():
            return p
    hits = sorted(d.rglob(f"{_slug(parts[-1])}.json")) if d.is_dir() else []
    if not hits:
        sys.exit(f"no template '{name}' under {d}")
    if len(hits) > 1:
        sys.exit(f"template '{name}' is ambiguous: " + ", ".join(str(h.relative_to(d)) for h in hits)
                 + " - name it as folder/name")
    return hits[0]


def template_save(args) -> None:
    folder = _slug(args.folder or args.printer or args.media or "general")
    d = templates_dir() / folder
    d.mkdir(parents=True, exist_ok=True)
    tpl = {
        "name": args.name,
        "description": args.description or "",
        "text": args.text,
        "subtext": args.subtext or "",
        "qr": args.qr or "",
        "icon": args.icon or "",
        "layout": args.layout or "",
        "style": args.style or "",
        "media": args.media or "",
        "printer": args.printer or "",
        "copies": args.copies or 0,
    }
    tpl = {k: v for k, v in tpl.items() if v or k in ("name", "text")}
    p = d / f"{_slug(args.name)}.json"
    with p.open("w") as fh:
        json.dump(tpl, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    res = {"written": str(p), "template": tpl}
    if not args.no_commit:
        res["repo"] = repo_commit(f"templates: save {folder}/{p.stem}", ["templates"])
    print(json.dumps(res, indent=2, ensure_ascii=False))


def template_list() -> None:
    d = templates_dir()
    out = []
    if d.is_dir():
        for p in sorted(d.rglob("*.json")):
            with p.open() as fh:
                t = json.load(fh)
            out.append({"id": str(p.relative_to(d).with_suffix("")), "name": t.get("name"),
                        "description": t.get("description", ""), "text": t.get("text", ""),
                        "icon": t.get("icon", ""), "printer": t.get("printer", ""), "media": t.get("media", "")})
    print(json.dumps({"templates_dir": str(d), "repo": resolve_paths()["repo"], "count": len(out),
                      "templates": out}, indent=2, ensure_ascii=False))


def template_show(name: str) -> dict:
    with _find_template(name).open() as fh:
        return json.load(fh)


def template_remove(name: str) -> None:
    p = _find_template(name)
    p.unlink()
    print(json.dumps({"removed": str(p), "repo": repo_commit(f"templates: remove {p.stem}", ["templates"])}, indent=2))


# --------------------------------------------------------------------------
# backends
# --------------------------------------------------------------------------
def backends() -> dict:
    def have(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except ImportError:
            return False

    return {
        "uv": bool(shutil.which("uv")),
        "brother_ql": bool(shutil.which("brother_ql")),
        "ptouch-print": bool(shutil.which("ptouch-print")),
        "cups_lp": bool(shutil.which("lp")),
        "avahi-browse": bool(shutil.which("avahi-browse")),
        "qrencode": bool(shutil.which("qrencode")),
        "python_pillow": have("PIL"),
        "python_qrcode": have("qrcode"),
        "python_resvg": have("resvg_py"),
        "fontconfig": bool(shutil.which("fc-match")),
        "notes": {
            "zebra": "ZPL backend not implemented yet — see docs/backends.md",
            "dymo": "DYMO backend not implemented yet — see docs/backends.md",
        },
    }


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(prog="labelctl.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("paths")
    sub.add_parser("backends")
    d = sub.add_parser("discover")
    d.add_argument("--json", action="store_true")

    r = sub.add_parser("registry").add_subparsers(dest="rcmd", required=True)
    r.add_parser("list")
    r.add_parser("show")
    a = r.add_parser("add")
    a.add_argument("--id", required=True)
    a.add_argument("--model", required=True)
    a.add_argument("--name")
    a.add_argument("--description")
    a.add_argument("--backend")
    a.add_argument("--host")
    a.add_argument("--port", type=int, default=9100)
    a.add_argument("--usb-id", dest="usb_id")
    a.add_argument("--cups-queue", dest="cups_queue")
    a.add_argument("--media")
    a.add_argument("--url", help="http_bridge / print_hub base URL")
    a.add_argument("--target", help="print_hub target id or alias")
    a.add_argument("--bridge-type", dest="bridge_type", choices=["ptouch", "niimblue"])
    a.add_argument("--serial-port", dest="serial_port", help="niimblue bridge: serial path on the bridge host")
    a.add_argument("--offset-mm", dest="offset_mm", type=float, help="die-cut print-position calibration, negative = left")
    a.add_argument("--margin-mm", dest="margin_mm", type=float)
    a.add_argument("--density", type=int)
    a.add_argument("--style", help="default style for this printer")
    a.add_argument("--cups-option", dest="cups_option", action="append", help="extra lp -o option, repeatable")
    a.add_argument("--alias", action="append", help="another name for --printer, repeatable")
    a.add_argument("--default", action="store_true", help="use when --printer is omitted")
    a.add_argument("--shared", action="store_true", help="write to the shared (user-data) registry")
    rm = r.add_parser("remove")
    rm.add_argument("--id", required=True)
    sm = r.add_parser("set-media")
    sm.add_argument("--id", required=True)
    sm.add_argument("--media", required=True)

    m = sub.add_parser("media").add_subparsers(dest="mcmd", required=True)
    m.add_parser("list")
    ms = m.add_parser("show")
    ms.add_argument("name")

    rp = sub.add_parser("repo").add_subparsers(dest="pcmd", required=True)
    rp.add_parser("status")
    rs = rp.add_parser("set")
    rs.add_argument("path")
    rc = rp.add_parser("create")
    rc.add_argument("--name", default="Label-Templates")
    rc.add_argument("--dir", required=True, help="parent directory to clone into")
    rc.add_argument("--owner", help="GitHub user/org; default: the gh account")
    rc.add_argument("--public", action="store_true", help="default is private")
    rm2 = rp.add_parser("commit")
    rm2.add_argument("-m", "--message", default="label-printer: update")

    t = sub.add_parser("template").add_subparsers(dest="tcmd", required=True)
    t.add_parser("list")
    ts = t.add_parser("save")
    ts.add_argument("--name", required=True)
    ts.add_argument("--text", required=True)
    ts.add_argument("--subtext")
    ts.add_argument("--qr")
    ts.add_argument("--icon")
    ts.add_argument("--layout")
    ts.add_argument("--style")
    ts.add_argument("--copies", type=int)
    ts.add_argument("--media")
    ts.add_argument("--printer")
    ts.add_argument("--description")
    ts.add_argument("--folder", help="templates/<folder>/; default: the printer id, else the media, else general")
    ts.add_argument("--no-commit", action="store_true", help="don't commit/push the Label-Templates repo")
    tsh = t.add_parser("show")
    tsh.add_argument("name")
    trm = t.add_parser("remove")
    trm.add_argument("name")

    args = ap.parse_args()

    if args.cmd == "paths":
        print(json.dumps(resolve_paths(), indent=2))
    elif args.cmd == "backends":
        print(json.dumps(backends(), indent=2))
    elif args.cmd == "discover":
        print(json.dumps(discover(), indent=2))
    elif args.cmd == "registry":
        if args.rcmd in ("list", "show"):
            print(json.dumps(load_registry(), indent=2))
        elif args.rcmd == "add":
            registry_add(args)
        elif args.rcmd == "remove":
            registry_remove(args)
        elif args.rcmd == "set-media":
            registry_set_media(args)
    elif args.cmd == "repo":
        if args.pcmd == "status":
            paths = resolve_paths()
            st = ""
            if paths["repo"]:
                st = subprocess.run(["git", "-C", paths["repo"], "status", "-sb"], capture_output=True, text=True).stdout
            print(json.dumps({"repo": paths["repo"], "git": st.strip(), "styles": paths["styles"],
                              "shared_registry": paths["shared_registry"], "templates": paths["templates"]}, indent=2))
        elif args.pcmd == "set":
            repo_set(args.path)
        elif args.pcmd == "create":
            repo_create(args.name, args.dir, args.public, args.owner)
        else:
            print(json.dumps(repo_commit(args.message), indent=2))
    elif args.cmd == "template":
        if args.tcmd == "list":
            template_list()
        elif args.tcmd == "save":
            template_save(args)
        elif args.tcmd == "show":
            print(json.dumps(template_show(args.name), indent=2, ensure_ascii=False))
        elif args.tcmd == "remove":
            template_remove(args.name)
    elif args.cmd == "media":
        cat = load_catalogue()
        if args.mcmd == "list":
            print(json.dumps(
                {k: {kk: vv for kk, vv in v.items()} for k, v in cat["products"].items()},
                indent=2))
        else:
            prod = cat["products"].get(args.name)
            if not prod:
                sys.exit(f"unknown media '{args.name}'")
            geo = cat["geometry"][prod["family"]][prod["geometry"]]
            print(json.dumps({"product": args.name, **prod, "geometry_detail": geo}, indent=2))


if __name__ == "__main__":
    main()
