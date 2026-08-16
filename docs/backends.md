# Print backends

Which printers this plugin can drive, how, and what is not built yet.

A backend is chosen from the model at registration time (`labelctl.py registry
add` infers it) and stored in the registry. `render.py print` dispatches on it.

| Backend | Models | Transport | Status |
|---|---|---|---|
| `brother_ql_network` | Brother QL-500 … QL-1060N | raw TCP `:9100` | working |
| `brother_ql_usb` | same, over USB | libusb via `brother_ql -b pyusb` | working |
| `ptouch_usb` | Brother PT (P-touch) | libusb via `ptouch-print` | working |
| `cups` | anything with a CUPS queue | `lp -d <queue>` | working, untested breadth |
| `zebra_wip` | Zebra ZD/ZT/GK/GX/ZQ | — | **not implemented** |
| `dymo_wip` | DYMO LabelWriter | — | **not implemented** |

Discovery and registration work for every row, including the two unimplemented
ones. Printing to a `*_wip` backend exits with an explicit error rather than
attempting anything.

## Verified

Verified 2026-08-16 on Ubuntu (kernel 7.0.0), Python 3.14, against a Brother
QL-810W on a LAN.

- `brother_ql` 0.9.4, `brother_ql_network` to `tcp://<ip>:9100` — prints.
- mDNS discovery via `avahi-browse -atrp` — finds the printer, model, address.
- Rendering with Pillow 12.1.1 and the `qrcode` Python package.

Not verified in this pass: `brother_ql_usb`, `ptouch_usb`, `cups`. The command
shapes are taken from working deployments but no hardware was on hand.

## Findings worth not rediscovering

**`brother_ql discover` is not a network discovery tool.** It walks USB only.
In 0.9.4 it also raises `NotImplementedError: Backend None not implemented`
unless `-b` precedes the subcommand — `brother_ql discover` fails, `brother_ql
-b pyusb discover` works. This is why discovery here is mDNS-based.

**A networked label printer is often not a CUPS queue.** The QL-810W tested
against answers on `:9100`, advertises `_ipp._tcp` over mDNS, and does not
appear in `lpstat -v` at all. Anything that discovers printers by asking CUPS
will report an empty network next to a working printer.

**`brother_ql print` has no dry run.** It converts and transmits in a single
step; `--no-cut` suppresses the cutter, not the print. A label came out of the
printer during development on the assumption that it would not. Preview is
therefore a pure-PIL path in `render.py` that never opens a socket.

**`brother_ql` 0.9.4 is incompatible with Pillow ≥ 10, and fails only sometimes.**
`conversion.py` resizes with `Image.ANTIALIAS`, which Pillow removed in 10.0, so
a job that needs resizing dies with:

```
AttributeError: module 'PIL.Image' has no attribute 'ANTIALIAS'
```

The trap is that it is **conditional on the image dimensions**. brother_ql only
resizes when the image width differs from the label's printable width, so a
square test image at exactly `dots_printable` prints perfectly and a real
landscape label crashes — on the same printer, same Pillow, minutes apart. It
reads as an intermittent printer fault and is not one.

`render.py` avoids it rather than patching it: the image is rotated a quarter
turn and, if necessary, resized in Pillow to exactly `printable_px` before
`brother_ql` sees it, so the offending branch is never reached. That works on
any Pillow version. If you call `brother_ql` directly, either pin Pillow < 10
or pre-size the image yourself.

**The deprecation warning is noise.** Every `brother_ql` invocation on 0.9.4
prints `brother_ql.devicedependent is deprecated and will be removed in a future
release` to stderr, including successful ones. Do not treat it as a failure.

**Reachability says nothing about media.** A TCP connect to `:9100` succeeding
means the printer is powered and on the network. These printers have no ink, so
a failed print on a reachable printer is nearly always an exhausted roll or an
open cover — neither of which the printer reports.

**`ptouch-print` is print-only.** It exposes no device settings at all.
Auto-power-off, Bluetooth pairing, auto-cut defaults and tape-feed are reachable
only from Brother's Windows/macOS Printer Setting Tool over USB.

**Some Brother models cannot be put on Wi-Fi from Linux.** Wi-Fi configuration
is restricted to that same Setting Tool; the Wireless Direct web UI has no
wireless page. WPS push-button is the only route that works from Linux, and the
radio may be 2.4 GHz only.

## Adding Zebra

Not started. The shape it would take:

Zebra printers speak **ZPL II**, a text command language, over raw TCP `:9100`
or USB — so no rasteriser is needed and `render.py` would bypass PIL entirely
for this backend. A minimal label is:

```
^XA
^FO50,50^A0N,40,40^FDSpare fuses^FS
^FO50,120^BQN,2,6^FDMA,https://inv.example/a/42^FS
^XZ
```

`^BQ` is the QR field. Discovery already recognises Zebra model prefixes
(`ZD`, `ZT`, `GK`, `GX`, `ZQ`) and assigns `zebra_wip`, so the work is:

1. a `zebra_network` backend that emits ZPL and writes it to the socket
2. a media model in dots rather than the pixel canvas used for Brother
3. `^MD`/`^SD` darkness and `~JC` calibration, which Brother has no analogue for

The registry schema needs no changes — `host`, `port`, `model` already cover it.

## Adding DYMO

Also not started, and less tractable. LabelWriters have no page description
language; they take a raster over USB and the open-source path is
`dymo-cups-drivers` plus a CUPS queue. In practice a DYMO is best registered
with the `cups` backend once a queue exists, and `dymo_wip` exists mainly so
discovery names the device rather than silently ignoring it.

## Relationship to the MCP server

`mcp-server/` in this repo is a separate, older path: a streamable-HTTP MCP that
renders labels and posts them to a small print bridge over USB. It targets
P-touch only and requires that bridge to be deployed.

The `scripts/` layer documented here is standalone — it needs no bridge and no
MCP, and it is what the `profile-printers`, `print-label`, `qr-labels`,
`label-templates` and `install-drivers` skills use. The MCP remains for setups
already built around it; the four original skills (`label-an-asset`,
`label-a-storage-unit`, `batch-label-run`, `printer-troubleshooting`) still go
through it.
