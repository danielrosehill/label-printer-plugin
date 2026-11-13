# label-printer-plugin

Print labels on **Brother QL and P-touch** label printers from Claude Code — text and
QR labels, at the size of whatever roll is loaded, on whichever printer you name.

There are two ways to use this, and they are independent.

**Standalone (default).** Nothing to deploy. The plugin discovers printers on this
machine and the LAN, keeps a registry of them, renders labels itself and sends them
straight to the printer.

```
Claude Code ──▶ scripts/render.py ──raw TCP :9100──▶ Brother QL
                (renders PNG)     └─USB via ptouch-print──▶ Brother P-touch
```

**Via the bundled MCP server.** The older path, still supported: a streamable-HTTP MCP
that renders labels and posts them to a small USB print bridge. P-touch only, and it
needs the bridge deployed first — see [Running the MCP server](#running-the-mcp-server).

```
Claude Code ──MCP──▶ label-printer ──HTTP──▶ print bridge ──USB──▶ Brother P-touch
                     (renders PNG)           (:9180)               (24mm tape)
```

## Quick start

```bash
/plugin marketplace add danielrosehill/Claude-Code-Plugins
/plugin install label-printer
```

Then, in Claude Code:

> find my label printers

> print a label saying "Spare fuses / Garage shelf B" with a QR to https://inv.example/a/42

Or drive the scripts directly:

```bash
python3 scripts/labelctl.py discover
python3 scripts/labelctl.py registry add --id ql-810w --model QL-810W \
  --host 192.168.68.63 --description "Office shelf" --media DK-22210
python3 scripts/render.py preview --text "Spare fuses" --qr https://inv.example/a/42 -o /tmp/l.png
python3 scripts/render.py print   --text "Spare fuses" --qr https://inv.example/a/42
```

`preview` never opens a socket to the printer — see [No dry run](#no-dry-run).

## Skills

| Skill | Purpose |
|---|---|
| `profile-printers` | Find label printers and register them with a name and description |
| `print-label` | Print a label at a chosen media size |
| `qr-labels` | Print a label carrying a QR code |
| `label-templates` | Save a label you print repeatedly, and print from it |
| `install-drivers` | Install the Linux tooling — `brother_ql`, `ptouch-print`, mDNS, CUPS |
| `label-an-asset` | Tag one item — asset number, name, QR to its page *(MCP)* |
| `label-a-storage-unit` | Tag a box, bin or shelf *(MCP)* |
| `batch-label-run` | Label a whole shelf, or generate labels from a CSV *(MCP)* |
| `printer-troubleshooting` | Nothing printed — work out why |

`/label` routes to any of them.

## Printer support

| Backend | Models | Transport | Status |
|---|---|---|---|
| `brother_ql_network` | Brother QL-500 … QL-1060N | raw TCP `:9100` | working |
| `brother_ql_usb` | same, over USB | `brother_ql -b pyusb` | working |
| `ptouch_usb` | Brother PT (P-touch) | `ptouch-print` | working |
| `cups` | anything with a CUPS queue | `lp -d` | working |
| `zebra_wip` | Zebra ZD/ZT/GK/GX/ZQ | — | **discovered and registered, not yet printable** |
| `dymo_wip` | DYMO LabelWriter | — | **discovered and registered, not yet printable** |

Verified end to end 2026-08-16 against a **Brother QL-810W** over the network, on
Ubuntu with `brother_ql` 0.9.4 and Pillow 12.1.1. Printing to a `*_wip` backend fails
with an explicit message rather than attempting anything. What a Zebra backend would
involve is sketched in [`docs/backends.md`](docs/backends.md).

## Where things are stored

Two locations, deliberately separate. Ask `scripts/paths.sh --json` rather than
hard-coding either.

| | Path | Committed? |
|---|---|---|
| **Printer registry** — LAN addresses, true on one network | `~/.claude-plugins/label-printer/printers.json` | never |
| **Templates** — labels you reuse, worth mirroring | `<user-data-root>/label-printer/templates/` | yes, in your own repo |

The user-data root is `$CLAUDE_USER_DATA`, else whichever of `~/.claude-user-data` or
`~/.local/share/claude-plugins` already exists, else `~/.claude-user-data`. It adopts an
existing root rather than starting a second one, and reports which rule fired.

## Media

`reference/media-catalogue.json` carries DK and TZe product codes with their pixel
geometry — 24 DK geometries and 7 TZe widths, plus the product codes that map onto
them.

```bash
python3 scripts/labelctl.py media list
python3 scripts/labelctl.py media show DK-11202
```

The registry records which roll is loaded, and that decides the canvas. **Continuous**
rolls grow to fit the text, capped at 90 mm; **die-cut** labels are a fixed length and
text shrinks to fit. An `installed_media` that does not match the physical roll produces
a wrongly-sized label rather than an error.

## No dry run

`brother_ql print` converts *and* transmits in a single step. There is no dry-run flag,
and `--no-cut` suppresses the cutter, not the print. So `render.py preview` is a pure
Pillow path that never opens a socket — it is the only safe way to see a label before
spending media. Its output always carries `"printed": false`.

Other findings that cost time to work out — `brother_ql discover` being USB-only and
broken without `-b`, networked label printers not appearing in CUPS at all, the
harmless deprecation warning on every invocation — are in
[`docs/backends.md`](docs/backends.md).

## Label layout

Both renderers put the QR square on the left, the heading in large bold type, and an
optional second line beneath it. Tape narrower than about 18 mm drops the second line —
there is no room for it.

The standalone renderer sizes the canvas from the loaded media and caps a continuous
label at 90 mm, shrinking type to fit rather than stretching the roll. On die-cut media
the QR is additionally capped at 45% of the label length so it cannot squeeze the text
into a sliver.

The rest of this section describes the **MCP renderer**, whose behaviour differs:

QR labels are a uniform **62 mm** along the tape: QR square on the left, heading in
large bold type, optional second line beneath it. Long names **wrap to two lines**
rather than stretching the tape. A heading too wide to shrink legibly widens the label
instead, up to a 120 mm cap.

![Example asset label](docs/example-asset-label.png)

Tape narrower than 18 mm drops the second line — there is no room for it.

### Hebrew and other RTL text

Hebrew works in either field, **on its own**:

```
print_text_label(text="נקודת מסירת משלוחים")
```

Two things are handled for you. **Font fallback:** Inter carries no Hebrew glyphs at
all, so any string containing Hebrew or Arabic switches to the vendored Noto Sans
Hebrew faces — otherwise you get blank tape, not an error. **Bidi:** Pillow is normally
built without `libraqm`, so it lays glyphs out left-to-right and will not reorder RTL
text itself. The server applies the bidi algorithm explicitly and pins the layout
engine to `BASIC`, so the result is identical whether or not your Pillow has raqm.

Arabic will pick the same fallback font and be reordered correctly, but **contextual
letterforms are not shaped** — `BASIC` layout does no glyph joining. Hebrew needs no
joining, so it is unaffected. If you need correct Arabic, install a raqm-enabled
Pillow, drop the `_shape()` call and the `BASIC` pin, and let raqm do both.

#### Mixing scripts on one label does not work — use artwork instead

The font is chosen **per label, not per run**: one Hebrew character anywhere sends the
whole label to Noto Sans Hebrew, and that face has no Latin glyphs, so the Latin half
comes out as tofu boxes (`□□□□`). Splitting across `heading` and `subtext` does not
help — the choice is made once for both.

```
print_label(heading="Rosehill | רוזהיל")     # -> "□□□□□□□□ | רוזהיל"
```

Rather than a per-run font fallback, render the label yourself and submit it — see
**Custom artwork** below. That also fixes bidi properly, since a raqm-enabled Pillow
on the rendering side does real mixed-direction layout.

## Custom artwork

When the built-in layouts can't express the design — mixed scripts, a logo, custom
typography, columns — render your own bitmap and print it:

```python
label_canvas()
# {'tapeMm': 24, 'heightPx': 288, 'maxWidthPx': 3600, 'maxLengthMm': 300,
#  'scalePxPerMm': 12, ...}

print_image_label(image="<base64 PNG>", copies=1)
```

The tape width is the label's **height**; the label runs as long as you like along the
tape. Render at `heightPx` for the loaded tape (12 px/mm — the bridge downscales to the
180 dpi head and trims the blank leader, so no end margins are needed).

- **`image`** — PNG or JPEG, as a `data:` URL or a bare base64 string. Wrapped base64 is
  fine. 8 MiB decoded cap.
- **`fit`** — `scale` (default) resizes proportionally to the tape height; `pad` keeps
  the artwork's own scale and centres it across the tape; `exact` refuses anything whose
  height isn't already the tape height.
- Transparency is composited onto **white**. Submitting RGBA without this would print a
  solid black slab, since transparent converts to black rather than to bare tape.
- Length is capped at **300 mm**, looser than the 120 mm auto-layout cap — that one
  guards against a long string stretching tape, which doesn't apply to artwork composed
  deliberately.

Use `preview_image_label` to see the exact bitmap that would be sent, before spending
tape.

## Running the MCP server

Everything below is for the **MCP path only**. Skip it entirely if you are using the
standalone scripts.

The bridge, the `ptouch-print` patch some models need, and the hardware notes live in
**[ptouch-cube-print-bridge](https://github.com/danielrosehill/ptouch-cube-print-bridge)**.
Set that up first — the MCP path does not work without it.

### Tools

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
| `label_canvas` | The pixel canvas to render your own artwork onto |
| `preview_image_label` | Show submitted artwork as it would reach the printer, without printing |
| `print_image_label` | Print arbitrary PNG/JPEG artwork you rendered yourself |

The plugin ships no MCP connection. Register your deployed server on your gateway, and call its tools from there
(for example the `label-printer` upstream, `mcp__gateway__label-printer__<tool>`).

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
| `FONT_BOLD` / `FONT_REGULAR` | vendored Inter | Latin font paths |
| `FONT_HEBREW_BOLD` / `FONT_HEBREW_REGULAR` | vendored Noto Sans Hebrew | Used automatically for Hebrew/Arabic text |
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

**Standalone path** — Brother **QL-810W** over the network (`brother_ql_network`,
`tcp://…:9100`), DK-22210 continuous and DK-11202 die-cut, on Ubuntu with `brother_ql`
0.9.4, Python 3.14 and Pillow 12.1.1. Verified end to end 2026-08-16: mDNS discovery,
registry, preview and print. `brother_ql_usb`, `ptouch_usb` and `cups` follow the same
code path but no hardware was on hand for them.

**MCP path** — Brother **PT-P710BT** (P-Touch Cube Plus), 24 mm laminated tape,
`ptouch-print v1.8`, Ubuntu. `ptouch-print` also supports PT-P700, PT-P750W, PT-D460BT,
PT-D610BT, PT-E550W, PT-P900Wc and others — the rendering there is model-independent,
but only the P710BT has been exercised end to end.

## License

MIT — see [LICENSE](LICENSE). Vendored fonts are SIL OFL 1.1:
[Inter](https://github.com/rsms/inter) (`mcp-server/fonts/OFL.txt`) and
[Noto Sans Hebrew](https://github.com/notofonts/hebrew)
(`mcp-server/fonts/OFL-NotoSansHebrew.txt`). `ptouch-print` is a separate GPL-3.0
project.
