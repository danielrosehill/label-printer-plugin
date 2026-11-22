---
name: ip-address-labels
description: Print IP address labels for network devices (printer, server, NAS, router/firewall, desktop, bridges) in one common format, device name over its fixed IP with a filled icon, from a saved device list. Use on "label the printer with its IP", "print IP stickers", "IP address labels for the NAS and router", or after a device gets a new reservation.
---

# IP address labels

One format for every device, so a shelf of kit reads the same:

```
[icon]  Device Name
        10.0.0.72
```

Two lines, the user's house style (font, filled icons), one label per device. On 12 mm tape
this comes out about 37–52 mm long; on 24 mm about 70 mm.

## Device list

Kept in the user-data overlay, `<user-data>/label-printer/ip-labels.json`, not in the plugin:

```json
{
  "devices": [
    {"name": "DeskJet 5200", "ip": "10.0.0.72", "icon": "mdi:printer", "check": "ping"},
    {"name": "Bridge printer", "ip": "10.0.0.2:9181", "icon": "mdi:label", "check": "http"}
  ]
}
```

- `ip` is printed as written, so a service port (`10.0.0.2:9181`) is allowed for devices that
  have no address of their own (a USB printer behind a bridge).
- Suggested icons (filled mdi): printer `mdi:printer`, server `mdi:server`, NAS `mdi:nas`,
  router/firewall `mdi:router-network`, desktop `mdi:desktop-tower-monitor`, label printer
  `mdi:label`, access point `mdi:access-point`, camera `mdi:cctv`.
- New device the user names: add it to the file before printing, so the next run has it.

## Steps

1. **Verify each address before printing.** A label with a stale IP is worse than none. Ping
   it (or GET the port for `http`), and where you can, confirm it is a fixed address (DHCP
   reservation on the router, or a static config on the device). Report anything that is only
   "currently at" rather than reserved.
2. **Read the loaded tape** (`hubctl.py targets` → `health.tapeMm`, or `render.py preview`
   without `--no-live`). If it differs from what the user said is loaded, stop and say so:
   don't render for one width and print on another.
3. Preview every label in one go and look at it:
   ```bash
   render.py preview --text 'NAS\n10.0.0.50' --layout two-line --icon mdi:nas \
     --printer <label-printer> --media <tape> -o /tmp/ip-nas.png
   ```
4. Print, one job per device (`render.py print`, same flags plus `--copies` if asked).
5. Say which labels went out and which addresses were verified as reserved vs only live.
