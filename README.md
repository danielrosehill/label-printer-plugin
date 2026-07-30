# label-printer-plugin

Print labels on a **Brother P-touch** label printer from Claude Code — single labels,
N copies, batch runs, and QR-coded templates for inventory work.

A Claude Code plugin plus the streamable-HTTP **MCP server** behind it. The MCP renders
labels with PIL and `qrcode` and hands the bitmap to a small HTTP **print bridge** on
the Linux host the printer is wired to; the bridge drives `ptouch-print` over USB.

```
Claude Code ──MCP──▶ label-printer ──HTTP──▶ print bridge ──USB──▶ Brother P-touch
                     (renders PNG)           (:9180)               (24mm tape)
```

The bridge, the `ptouch-print` patch some models need, and the hardware notes live in
**[ptouch-cube-print-bridge](https://github.com/danielrosehill/ptouch-cube-print-bridge)**.
Set that up first — this repo is useless without it.

## Tools

| Tool | What it does |
|---|---|
| `printer_status` | Bridge reachability, loaded tape width, printer error word |
| `printer_capabilities` | What the driver does and does **not** expose — check before promising a setting |
| `preview_label` | Render a label and return the image **without printing** |
| `print_label` | General-purpose: heading, optional subtext, optional QR, N copies |
| `print_text_label` | Text only, no QR, up to 3 stacked lines |
| `print_asset_label` | Inventory asset template — `A-` prefix, name underneath |
| `print_storage_label` | Storage unit template — `S-` prefix, contents underneath |
| `print_batch` | Up to 50 different labels in one run |

## Skills

| Skill | Purpose |
|---|---|
| `label-an-asset` | Tag one item — asset number, name, QR to its page |
| `label-a-storage-unit` | Tag a box, bin or shelf |
| `batch-label-run` | Label a whole shelf, or generate labels from a CSV |
| `printer-troubleshooting` | Nothing printed — work out why |

## Label layout

QR labels are a uniform **62 mm** along the tape: QR square on the left, heading in
large bold type, optional second line beneath it. Long names **wrap to two lines**
rather than stretching the tape. A heading too wide to shrink legibly widens the label
instead, up to a 120 mm cap.

![Example asset label](docs/example-asset-label.png)

Tape narrower than 18 mm drops the second line — there is no room for it.

## Install

```bash
claude plugins install label-printer@danielrosehill
```

Point it at your deployed MCP:

```bash
export LABEL_PRINTER_MCP_URL=http://<host>:<port>/mcp
```

## Running the MCP server

Source is in [`mcp-server/`](mcp-server/). It speaks streamable HTTP on `:3000` by
default, or stdio with `MCP_TRANSPORT=stdio`.

```bash
docker build -t label-printer-mcp mcp-server/
docker run -d --name label-printer -p 3000:3000 \
  -e PRINT_BRIDGE_URL=http://<bridge-host>:9180 \
  label-printer-mcp
```

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `PRINT_BRIDGE_URL` | `http://127.0.0.1:9180` | Where the print bridge listens |
| `LABEL_WIDTH_MM` | `62` | Preferred QR-label length along the tape |
| `LABEL_TAPE_MM` | `24` | Fallback tape width when the printer is off |
| `ASSET_PREFIX` | `A-` | Prefix applied by `print_asset_label` |
| `STORAGE_PREFIX` | `S-` | Prefix applied by `print_storage_label` |
| `FONT_BOLD` / `FONT_REGULAR` | vendored Inter | Font paths |
| `MCP_TRANSPORT` | `streamable_http` | Or `stdio` |
| `MCP_HTTP_HOST` / `MCP_HTTP_PORT` | `0.0.0.0` / `3000` | HTTP bind |

The MCP has **no authentication** — bind it to a trusted LAN or VPN, or put it behind a
gateway that authenticates.

## Linux users: read this before hunting for settings

`ptouch-print` is a **print-only** driver. It exposes no device settings at all, so
**auto power-off cannot be changed from Linux** — not through the driver, not over
Bluetooth, not in the mobile apps, and not under Wine. It is a one-time change in
Brother's Windows/macOS Printer Setting Tool, stored in the printer's NVRAM.

The printer also **cannot be woken over USB** once it sleeps. Someone has to press the
button.

Full details, the complete option list, and the measurements behind the 60-minute
figure: **[`docs/linux-printer-settings.md`](docs/linux-printer-settings.md)**.

## Tested on

Brother **PT-P710BT** (P-Touch Cube Plus), 24 mm laminated tape, `ptouch-print v1.8`,
Ubuntu. `ptouch-print` also supports PT-P700, PT-P750W, PT-D460BT, PT-D610BT,
PT-E550W, PT-P900Wc and others — the rendering here is model-independent, but only the
P710BT has been exercised end to end.

## License

MIT — see [LICENSE](LICENSE). Vendored [Inter](https://github.com/rsms/inter) fonts are
SIL OFL 1.1 (`mcp-server/fonts/OFL.txt`). `ptouch-print` is a separate GPL-3.0 project.
