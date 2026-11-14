"""Print backends: take a rendered label image and get it onto a printer.

Chosen per printer by the registry entry's `backend` field:

  cups          lp -d <cups_queue> [cups_options]          any printer with a CUPS queue (the generic default)
  ptouch_usb    ptouch-print --image                        Brother P-touch on local USB
  brother_ql_network / brother_ql_usb   brother_ql print    Brother QL over raw TCP 9100 or USB
  http_bridge   POST the PNG to a USB print bridge          bridge_type ptouch (ptouch-print bridge) or niimblue
  print_hub     POST the PNG to a LAN Print Hub             url + target; the hub queues and routes it

`live_media()` asks bridge/hub printers what tape is loaded, so the canvas matches
the cassette instead of whatever the registry last recorded. It is a status read
only; nothing in this module prints except `send()`.
"""
from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ALIASES = {"ptouch-print": "ptouch_usb", "ptouch": "ptouch_usb", "brother_ql": "brother_ql_network",
           "http-bridge": "http_bridge", "print-hub": "print_hub", "hub": "print_hub"}
BACKENDS = ["cups", "ptouch_usb", "brother_ql_network", "brother_ql_usb", "http_bridge", "print_hub"]


class BackendError(RuntimeError):
    pass


def norm(name: str | None) -> str:
    return ALIASES.get(name or "", name or "")


def _http(url: str, body: dict | None = None, timeout: int = 60) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return {"ok": False, "http": e.code, **json.loads(e.read() or b"{}")}
        except ValueError:
            return {"ok": False, "http": e.code}
    except urllib.error.URLError as e:
        raise BackendError(f"unreachable: {url} ({e.reason})") from e


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.convert("L").save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- live media
def hub_target(printer: dict) -> dict:
    url = printer["url"].rstrip("/")
    want = printer.get("target")
    for t in _http(url + "/targets", timeout=20).get("targets", []):
        if t["id"] == want or want in t.get("aliases", []):
            return t
    raise BackendError(f"print hub {url} has no target '{want}'")


def live_media(printer: dict) -> dict | None:
    """{'tape_mm', 'max_px', 'media'} reported by the bridge or hub, or None if the backend can't say."""
    be = norm(printer.get("backend"))
    try:
        if be == "print_hub":
            h = hub_target(printer).get("health", {})
        elif be == "http_bridge" and printer.get("bridge_type", "ptouch") == "ptouch":
            h = _http(printer["url"].rstrip("/") + "/health", timeout=20)
        else:
            return None
    except BackendError as e:
        return {"error": str(e)}
    if h.get("ok") is False:
        return {"error": h.get("error") or "printer reports not ok"}
    return {k: v for k, v in {"tape_mm": h.get("tapeMm"), "max_px": h.get("maxPx"),
                              "media": h.get("media")}.items() if v}


# ---------------------------------------------------------------- send
def send(img, printer: dict, geo: dict, copies: int, cut: bool = True) -> dict:
    be = norm(printer.get("backend"))
    if be in ("zebra_wip", "dymo_wip"):
        raise BackendError(f"backend '{be}' is not implemented; see docs/backends.md")

    if be == "print_hub":
        body = {"target": printer["target"], "png": base64.b64encode(_png(img)).decode(), "copies": copies}
        for k in ("density",):
            if printer.get(k) is not None:
                body[k] = printer[k]
        res = _http(printer["url"].rstrip("/") + "/jobs?wait=true", body, timeout=300)
        ok = res.get("state") == "done"
        return {"backend": be, "ok": ok, "job": res.get("id"), "state": res.get("state"),
                "error": res.get("error"), "result": res.get("result")}

    if be == "http_bridge":
        url = printer["url"].rstrip("/")
        if printer.get("bridge_type", "ptouch") == "ptouch":
            res = _http(url + "/print", {"imageDataUrl": "data:image/png;base64," + base64.b64encode(_png(img)).decode(),
                                         "copies": copies}, timeout=240)
            return {"backend": be, "ok": bool(res.get("ok")), "result": res}
        # niimblue-node REST server
        if not _http(url + "/connected", timeout=10).get("connected"):
            port = printer.get("serial_port")
            if not port:
                devs = [d["address"] for d in _http(url + "/scan", {"transport": "serial", "timeout": 3000}).get("devices", [])]
                port = next((d for pat in ("/dev/serial/by-id/", "/dev/ttyACM", "/dev/ttyUSB")
                             for d in devs if d.startswith(pat)), None)
                if not port:
                    raise BackendError("no NIIMBOT serial port on the bridge host; is it plugged in and on?")
            _http(url + "/connect", {"transport": "serial", "address": port})
        res = _http(url + "/print", {
            "printTask": printer.get("print_task", "B1"), "printDirection": "top",
            "imageBase64": base64.b64encode(_png(img)).decode(),
            "labelWidth": img.width, "labelHeight": img.height, "quantity": copies,
            "density": printer.get("density", 3), "waitUntilFinished": True}, timeout=180)
        return {"backend": be, "ok": res.get("ok", True) is not False, "result": res}

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        png = tf.name

    if be in ("brother_ql_network", "brother_ql_usb"):
        from PIL import Image
        # brother_ql wants the head width across the image: rotate the reading-orientation canvas,
        # and hand it exactly dots_printable wide so it never hits its Image.ANTIALIAS resize
        # (removed in Pillow 10).
        r = img.convert("L").rotate(-90, expand=True)
        want = geo["printable_px"]
        if r.size[0] != want:
            r = r.resize((want, max(1, round(r.size[1] * want / r.size[0]))), Image.LANCZOS)
        r.save(png)
        if not shutil.which("brother_ql"):
            raise BackendError("brother_ql is not installed; see the install-drivers skill")
        if be == "brother_ql_network":
            ident, b = f"tcp://{printer['host']}:{printer.get('port', 9100)}", "network"
        else:
            ident, b = printer.get("usb_id_path") or f"usb://0x{printer['usb_id'].replace(':', '/0x')}", "pyusb"
        cmd = ["brother_ql", "-b", b, "-p", ident, "-m", printer["model"], "print", "-l", geo["geometry_name"]]
        if geo.get("two_color"):
            cmd.append("--red")
        if not cut:
            cmd.append("--no-cut")
        runs = []
        for _ in range(copies):
            p = subprocess.run(cmd + [png], capture_output=True, text=True)
            runs.append({"rc": p.returncode, "stderr": p.stderr.strip()[-400:]})
            if p.returncode:
                break
        return {"backend": be, "ok": all(x["rc"] == 0 for x in runs) and len(runs) == copies, "runs": runs}

    img.convert("L").save(png)
    if be == "ptouch_usb":
        if not shutil.which("ptouch-print"):
            raise BackendError("ptouch-print is not installed; see the install-drivers skill")
        p = subprocess.run(["ptouch-print", "--copies", str(copies), "--image", png], capture_output=True, text=True)
        return {"backend": be, "ok": p.returncode == 0, "rc": p.returncode, "stderr": p.stderr.strip()[-400:]}

    if be == "cups":
        q = printer.get("cups_queue")
        if not q:
            raise BackendError(f"printer '{printer['id']}' uses cups but has no cups_queue")
        cmd = ["lp", "-d", q, "-n", str(copies)]
        for o in printer.get("cups_options", []):
            cmd += ["-o", o]
        p = subprocess.run(cmd + [png], capture_output=True, text=True)
        return {"backend": be, "ok": p.returncode == 0, "queue": q, "stdout": p.stdout.strip(),
                "stderr": p.stderr.strip()[-400:]}

    raise BackendError(f"unknown backend '{be}'. Known: {', '.join(BACKENDS)}")


if __name__ == "__main__":
    sys.exit("library module; use render.py")
