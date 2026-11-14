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

## Bridge setup (niimblue-node REST server)

Run on the host the printer is USB-attached to (Node 22):

```bash
mkdir -p ~/niimblue-node && cd ~/niimblue-node && npm init -y && npm i @mmote/niimblue-node@1.4.1
```

systemd unit (adjust `User` and paths). The B1 is a CDC serial device owned `root:dialout`; without
`SupplementaryGroups=dialout` the server starts but `/connect` fails with EACCES.

```ini
[Unit]
Description=NIIMBOT label print bridge (niimblue-node REST server)
After=network-online.target
Wants=network-online.target
[Service]
User=<user>
SupplementaryGroups=dialout
WorkingDirectory=/home/<user>/niimblue-node
ExecStart=/usr/bin/node /home/<user>/niimblue-node/node_modules/@mmote/niimblue-node/cli.mjs server -h 0.0.0.0 -p 9181
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
```

`sudo systemctl daemon-reload && sudo systemctl enable --now niimblue-bridge; curl -s localhost:9181/connected`.
The server has no authentication: keep it on a trusted LAN/tailnet. Update with
`npm i @mmote/niimblue-node@latest` and a restart.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Bridge unreachable | `systemctl status niimblue-bridge`; `journalctl -u niimblue-bridge -n 50` |
| No NIIMBOT found | `ls /dev/serial/by-id/`; no kernel event on plug-in = charge-only cable |
| `/connect` EACCES | add `SupplementaryGroups=dialout` to the unit |
| Port busy / stale connection | `curl -X POST -H 'Content-Type: application/json' -d '{}' localhost:9181/disconnect` |
| Print shifted sideways | re-seat the roll in the guides; then tune `offset_mm` |
| Faint print | raise density (4-5); prefer filled icons |
| Wrong size | `GET /rfid` gives barcode and count only; pick the right media yourself |
