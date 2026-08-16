---
name: install-drivers
description: Install the Linux tooling label printing needs — brother_ql, ptouch-print, CUPS drivers, mDNS discovery and the Python rendering libraries.
---

# Install label printer drivers on Linux

Assumes Linux. Work out what is missing first, install only that, and re-check.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" backends
```

Every key is a yes/no. Map what came back `false` to the section below, install
those, then run it again — the second run is the verification, not the install
command's exit code.

## What each piece is for

| Tool | Needed for | Without it |
|---|---|---|
| `avahi-browse` | discovering networked printers | discovery finds nothing on the LAN and looks like an empty network |
| `brother_ql` | printing to Brother **QL** series | no DK label printing |
| `ptouch-print` | printing to Brother **PT** (P-touch) series | no TZe tape printing |
| `python_pillow` | rendering any label at all | nothing prints |
| `python_qrcode` or `qrencode` | QR labels | text labels still work |
| `cups_lp` | printers reached through a CUPS queue | only matters for the `cups` backend |

## Debian / Ubuntu

```bash
sudo apt update
sudo apt install -y avahi-utils python3-pil qrencode cups-client
```

`avahi-utils` is the one people miss; it is what provides `avahi-browse`.

### brother_ql — the QL series

A Python package, not a system driver. Install it for the user, not system-wide:

```bash
pipx install brother_ql || pip install --user brother_ql
```

Version 0.9.4 prints fine and emits a `brother_ql.devicedependent is deprecated`
warning on every invocation. That warning is noise — it is not a failure, and it
appears even on successful jobs.

It is, however, **incompatible with Pillow ≥ 10** — it resizes with the removed
`Image.ANTIALIAS`. This plugin works around it by pre-sizing the image, so no
Pillow pin is needed here. If the user calls `brother_ql` directly and hits
`AttributeError: module 'PIL.Image' has no attribute 'ANTIALIAS'`, that is the
cause, and it appears only for images that need resizing — see
[`docs/backends.md`](../../docs/backends.md).

For a **USB** QL, the user must be able to reach the device without root:

```bash
sudo usermod -aG lp "$USER"     # log out and back in for this to take effect
```

A networked QL needs none of that — it is a TCP socket on port 9100.

### ptouch-print — the P-touch series

Not packaged in Debian or Ubuntu. Build it from
<https://git.familie-radermacher.ch/linux/ptouch-print.git>:

```bash
sudo apt install -y build-essential cmake libusb-1.0-0-dev libgd-dev gettext
git clone https://git.familie-radermacher.ch/linux/ptouch-print.git
cd ptouch-print && cmake . && make && sudo make install
```

Two things about this driver that cost time if you do not know them:

- **Some models need an init patch.** The PT-P710BT in particular fails every
  job with a media error against unpatched upstream. The patch, and the hardware
  notes, are in
  [ptouch-cube-print-bridge](https://github.com/danielrosehill/ptouch-cube-print-bridge).
- **It is print-only.** It exposes no device settings whatsoever. Auto-power-off,
  Bluetooth pairing, auto-cut defaults and tape-feed are reachable only from
  Brother's Windows/macOS Printer Setting Tool over USB. Do not promise the user
  a setting change here — say plainly that Linux cannot reach it.

USB permissions, so the printer is usable without root:

```bash
sudo tee /etc/udev/rules.d/99-ptouch.rules >/dev/null <<'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="04f9", GROUP="lp", MODE="0660"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### Rendering libraries

```bash
pip install --user Pillow qrcode
```

`python3-pil` from apt covers Pillow. `qrcode` is not packaged everywhere; the
renderer falls back to the `qrencode` binary when the Python package is absent,
so either one is enough.

For Hebrew or other RTL text, add `python-bidi` — without it the renderer
reverses the string as a crude approximation, which is right for a single run
and wrong for anything mixed:

```bash
pip install --user python-bidi
```

## CUPS — only if you actually want a queue

Most label printing here bypasses CUPS entirely: `brother_ql` talks raw to
`:9100`, `ptouch-print` talks raw to USB. Set up a queue only when the user wants
to print from ordinary desktop applications too.

```bash
sudo apt install -y printer-driver-ptouch
sudo lpadmin -p Brother_QL_810W \
  -v "socket://BRW4CD577B584C6.local:9100" \
  -m "ptouch:0/ppd/ptouch-driver/Brother-QL-810W-ptouch-ql.ppd" \
  -D "Brother QL-810W" -E
```

Substitute the real node name — `BRW` + the MAC without separators, which
discovery reports as `hostname`. Prefer the mDNS name over the IP: these get
their address by DHCP and an IP baked into a queue breaks on the next lease.

Two traps:

- **The driverless route loses the media list.** `-m everywhere` over
  `ipp://…/ipp/print` produces a working queue whose PPD has no DK sizes in it —
  `29x90`, `62x100` and the rest are simply absent. Use the `ptouch` PPD if the
  sizes matter.
- **`cups-browsed` will hijack the queue**, rewriting it to
  `implicitclass://…` and breaking it. If a working queue goes strange, that is
  the first thing to check: `sudo systemctl disable --now cups-browsed`.

## Wi-Fi setup is out of scope, and often impossible from Linux

Getting a printer *onto* the network is a separate problem from printing to it,
and several Brother models cannot be configured from Linux at all — Wi-Fi setup
is restricted to the Windows/macOS Printer Setting Tool over USB. On those, **WPS
push-button is the only route that works from Linux**, and the printer may be
2.4 GHz only.

If the user is trying to get a printer onto Wi-Fi, say this rather than
attempting it, and point them at WPS.

## Finishing

Re-run `backends` and show the before/after. Then hand off to
`profile-printers` — installing the tooling is only useful once discovery has
been run and something is in the registry.
