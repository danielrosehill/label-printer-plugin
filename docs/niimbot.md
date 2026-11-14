# NIIMBOT printers

Folded in from the `niimbot-labels` plugin on 2026-11-14. **Confirmed** = checked on a real
B1 or in source code; **assumed** = not yet verified.

| Fact | Status |
|---|---|
| B1 printhead 384 dots (48 mm) at 203 dpi = 8 dots/mm | confirmed (niimprint and niimblue-node both use 384 px) |
| A 50x30 roll is sent as a 384x240 image, `printDirection: "top"`, `printTask: "B1"` | confirmed (niimblue-node README) |
| Narrower rolls (40 mm) are sent at their own width (320 px) and the printer centres them | confirmed on a 40x30 roll |
| On some units 40x30 prints sit against the right edge: compensate with the printer's `offset_mm` (e.g. -2) | reported on one B1; how much is enough varies |
| The B1 enumerates as USB CDC serial (`/dev/ttyACM*`, `cdc_acm`) plus a `usblp` interface | confirmed |
| USB id `3513:0002`, product "B1 LABEL PRINTER" | confirmed |
| Rolls carry an RFID tag (`GET /rfid`); it gives a barcode and label count, **not** dimensions | confirmed |
| A first print of "Modafinil / 100 mg" + `mdi:pill`, 40x30, density 3 came out centred and correctly sized | confirmed |

## Driver choice

- **niimblue-node** (`@mmote/niimblue-node`, MultiMote): used. CLI plus a REST server, B1 tested over USB
  serial, built on niimbluelib, the most actively maintained NIIMBOT protocol library. Its REST server is
  the bridge (`http_bridge`, `bridge_type: niimblue`).
- niimprint (AndBondStyle fork, Python): pins Python ~3.11, smaller protocol coverage, no HTTP server.
- niimbot-cups: a CUPS filter around niimprint; B1 not in its supported list.
- NiimPrintX: desktop GUI, not for headless use.

## Bridge API (niimblue-node `src/server/worker.ts`)

`GET /connected`, `POST /connect {transport:"serial", address}`, `POST /disconnect`, `GET /info`,
`GET /rfid`, `POST /scan {transport:"serial"}`, `POST /print {printTask, printDirection, imageBase64,
labelWidth, labelHeight, quantity, density, threshold, imageFit}`. POST bodies need
`Content-Type: application/json`.

## Lessons

- **Charge-only cables.** Two cables produced no kernel USB event at all while the printer was on and
  advertising over BLE; the third enumerated at once. No `journalctl -k` event on plug-in means swap the
  cable before suspecting the printer.
- A confined (snap) `lsusb` can miss the device; read `/sys/bus/usb/devices/*/idVendor` or the kernel log.
- Prefer the `/dev/serial/by-id/...` path over `ttyACM0`: it survives replugs and reboots.
