---
name: niimbot-bridge-setup
description: Install, update or repair a niimblue-node REST server that drives a USB NIIMBOT label printer (B1, B21, D11...) for this plugin, and register it. Use on "set up the niimbot", "the niimbot bridge is down", "update niimblue", "move the NIIMBOT to another machine".
---

# NIIMBOT bridge

NIIMBOT printers have no CUPS/IPP driver. A small Node server, niimblue-node, owns the USB
serial link and takes PNGs over HTTP; this plugin's `http_bridge` backend (or a LAN Print
Hub's `niimblue` driver) talks to it. Facts and lessons: `docs/niimbot.md`.

## Install on the machine the printer is plugged into

```bash
mkdir -p ~/niimblue-node && cd ~/niimblue-node && npm init -y && npm i @mmote/niimblue-node
sed "s/<user>/$USER/g" ${CLAUDE_PLUGIN_ROOT}/bridge/niimblue-bridge.service | sudo tee /etc/systemd/system/niimblue-bridge.service
sudo systemctl daemon-reload && sudo systemctl enable --now niimblue-bridge
curl -s localhost:9181/connected
ls -l /dev/serial/by-id/      # note the printer's stable path
```

Node 18+ is needed. The unit's `SupplementaryGroups=dialout` is what lets it open the serial port.
The server has no auth: bind it to a trusted LAN or VPN only.

Update: `cd ~/niimblue-node && npm i @mmote/niimblue-node@latest && sudo systemctl restart niimblue-bridge`.

## Register it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry add --id niimbot --model B1 \
  --backend http_bridge --bridge-type niimblue --url http://<host>:9181 \
  --serial-port /dev/serial/by-id/<path> --media NIIMBOT-40x30 --density 3
```

Then preview with `design-label` and print one test label.

## When it fails

| Symptom | Check | Fix |
|---|---|---|
| bridge unreachable | `systemctl status niimblue-bridge`; network path | restart it; `journalctl -u niimblue-bridge -n 50` |
| no serial port found | `ls /dev/ttyACM* /dev/serial/by-id/`; `journalctl -k --since -5min` | no kernel event = charge-only cable; otherwise power the printer on |
| `/connect` EACCES | unit lacks `SupplementaryGroups=dialout` | restore the unit from `bridge/` |
| port busy / stale | `curl localhost:9181/connected` | `curl -X POST -H 'Content-Type: application/json' -d '{}' localhost:9181/disconnect` |
| print shifted sideways | roll not centred under the head | re-seat the roll; set the printer's `offset_mm` |
| faint | density | `--density 4` or `5` on the registry entry; filled icons |
| wrong size / cut off | `GET /rfid` | register the right `NIIMBOT-<across>x<along>` media |
