# label-printer-plugin

Design and print labels from Claude Code. Say "four labels for the wine bottles with a wine
icon" and it picks a filled icon, sets the text in your font, wraps it to a compact layout
sized to whatever tape or roll is loaded, previews it, and sends it to the printer by
whatever route reaches it: CUPS, `ptouch-print`, `brother_ql`, a USB print bridge, or a
LAN print hub.

Brother QL (DK rolls), Brother P-touch (TZe tape) and NIIMBOT (die-cut rolls) are covered
with real media geometry; anything with a CUPS queue works through `cups`.

```
           design layer                         backend layer (per printer)
"4 labels, wine icon" ─▶ render.py ─▶ PNG ─┬─▶ cups         lp -d <queue>
  icon: Iconify, cached     │              ├─▶ ptouch_usb   ptouch-print (USB)
  font: by name, fetched    │              ├─▶ brother_ql   TCP 9100 / USB
  layout: one/two-line,     │              ├─▶ http_bridge  ptouch-print or niimblue-node bridge
  icon-top, QR              │              └─▶ print_hub    LAN Print Hub (queues + routes)
  media: live from printer ─┘
```

Your printers, styles and saved labels live in a **Label-Templates** repository of your
own, created from [Label-Templates-Template](https://github.com/danielrosehill/Label-Templates-Template).

## Quick start

```bash
/plugin marketplace add danielrosehill/Claude-Code-Plugins
/plugin install label-printer
```

Then, in Claude Code:

> set up label printing

> print me two labels saying "Flat Ethernet Cable" with an ethernet icon

> save that as a template

Or drive the scripts directly (`uv` installs the Python deps on the fly):

```bash
R="uv run -q --script scripts/render.py"
$R icons search wine                                         # filled icons first
$R preview -t "Wine Bottles" -i mdi:glass-wine -m 24mm -o /tmp/l.png   # design only, no printer
$R preview -p ptouch -t "Wine Bottles" -i mdi:glass-wine -o /tmp/l.png # sized to the loaded tape
$R print   -p ptouch -t "Wine Bottles" -i mdi:glass-wine -n 4
$R font "Inter SemiBold"                                     # resolves, downloads if missing
python3 scripts/labelctl.py template save --name wine --printer ptouch --text "Wine Bottles" --icon mdi:glass-wine
```

`preview` never sends a job; for bridge and hub printers it reads their status to learn the
loaded tape. See [No dry run](#no-dry-run).

## Skills

| Skill | Purpose |
|---|---|
| `design-label` | Request -> icon, font, layout -> preview -> print. The main entry point |
| `setup` | Create the Label-Templates repo, register printers and backends, set the default style |
| `print-label` | Print through the printer's backend; what `printed` does and doesn't prove |
| `label-templates` | Save a label you reprint, list them, print from one (committed to your repo) |
| `qr-labels` | Labels carrying a QR code |
| `batch-label-run` | Many different labels in one run, or from a CSV |
| `profile-printers` | Discover USB, mDNS and CUPS label printers |
| `niimbot-bridge-setup` | Run a niimblue-node bridge for a NIIMBOT printer |
| `install-drivers` | uv, `brother_ql`, `ptouch-print`, mDNS, CUPS, Python libs |
| `label-an-asset`, `label-a-storage-unit` | Asset and storage tags *(MCP)* |
| `printer-troubleshooting` | Nothing printed: work out why |

`/label` routes to any of them.

## Design

- **Icons:** any [Iconify](https://iconify.design) id (`mdi:ethernet`); a bare name uses the
  style's `icon_prefix` (default `mdi`, whose icons are filled and print solid). `icons search`
  ranks filled icons above outline/thin ones. Cached in `~/.cache/label-printer/icons`.
- **Fonts:** by name, e.g. `"IBM Plex Sans Bold"` (the default) or `"Inter SemiBold"`, or a
  `.ttf` path. Resolution: installed (fontconfig) -> cache -> download (IBM Plex from IBM's
  repository, anything else from Google Fonts) -> bundled Inter ExtraBold. Hebrew lines
  switch to Noto Sans Hebrew.
- **Layouts:** on continuous media, `auto` keeps one line until the label would pass
  `wrap_mm` (85 mm), then takes the two-line split giving the shortest label; icon and QR sit
  at the left at full height. On die-cut media the icon goes left on wide labels and on top on
  squarer ones. `one-line`, `two-line`, `text`, `icon`, `icon-top`, `qr` force one.
- **Styles:** named bundles of those settings in your repo's `styles.json`; one is the default.

## Printer support

| Backend | Printers | Transport | Status |
|---|---|---|---|
| `cups` | anything with a CUPS queue | `lp -d` (+ `cups_options`) | working |
| `brother_ql_network` | Brother QL-500 … QL-1060N | raw TCP `:9100` | working, verified 2026-08-16 on a QL-810W |
| `brother_ql_usb` | same, over USB | `brother_ql -b pyusb` | working |
| `ptouch_usb` | Brother PT (P-touch) | `ptouch-print` | working |
| `http_bridge` (`bridge_type: ptouch`) | P-touch on another machine | POST to a [ptouch-print bridge](https://github.com/danielrosehill/ptouch-cube-print-bridge) | matches the bridge API; not yet printed end to end from this script |
| `http_bridge` (`bridge_type: niimblue`) | NIIMBOT B1/B21/D11… | [niimblue-node](https://github.com/MultiMote/niimblue-node) REST server | ported from code that printed on a B1; this path not yet printed end to end |
| `print_hub` | anything behind a [LAN Print Hub](https://github.com/danielrosehill/LAN-Print-Hub) target | POST PNG to `/jobs` | live status verified 2026-11-14 (P-touch and NIIMBOT targets); PNG submit matches the hub's API, not yet printed end to end |
| `zebra_wip`, `dymo_wip` | Zebra, DYMO | — | discovered and registered, not yet printable |

Bridge and hub tape printers report the loaded tape (`tapeMm`, `maxPx`), and that wins over
the registry, so a 12 mm cassette swapped in for the usual 24 mm renders correctly.

## Where things are stored

| | Path | Committed? |
|---|---|---|
| **Label-Templates repo**: `printers.md` + `printers.json` (shared registry), `styles.json`, `templates/<printer-or-media>/` | your own repo, from the template | yes; the scripts commit and push on save |
| **Pointer to it** | `<user-data-root>/label-printer/config.json` (`label_templates_repo`) | in your user-data repo |
| **Machine registry**: USB/LAN printers true on one box | `~/.claude-plugins/label-printer/printers.json` | never |
| **Icon and font cache** | `~/.cache/label-printer/` | no |

`labelctl.py repo status` (or `scripts/paths.sh --json`) shows where everything resolves.
Without a repo, styles and templates fall back to the user-data dir. The user-data root is
`$CLAUDE_USER_DATA`, else whichever of `~/.claude-user-data` or
`~/.local/share/claude-plugins` already exists, else `~/.claude-user-data`.

## Media

`reference/media-catalogue.json` carries DK, TZe and NIIMBOT product codes with their pixel
geometry. `--media` also takes `24mm` (tape) and `40x30` (NIIMBOT).

```bash
python3 scripts/labelctl.py media list
python3 scripts/labelctl.py media show NIIMBOT-40x30
```

**Continuous** media grows with the text; **die-cut** labels are a fixed size and text
shrinks to fit. A recorded media that doesn't match the physical roll produces a
wrongly-sized label rather than an error; live-reporting printers avoid that.

## No dry run

`brother_ql print` converts *and* transmits in a single step. There is no dry-run flag,
and `--no-cut` suppresses the cutter, not the print. So `render.py preview` is a pure
rendering path that never sends a job; its output always carries `"printed": false`.

`"printed": true` on a real print means the backend accepted the job. Tape printers can
accept a job and print nothing (cover, phone app holding the printer, a USB drop), so the
skills ask whether a label came out instead of assuming it.

Other findings that cost time to work out — `brother_ql discover` being USB-only and
broken without `-b`, networked label printers not appearing in CUPS at all, the
harmless deprecation warning on every invocation — are in
[`docs/backends.md`](docs/backends.md). NIIMBOT facts and lessons: [`docs/niimbot.md`](docs/niimbot.md).

## Label layout (MCP path)

The bundled MCP server (below) has its own renderer. The rest of this section describes the **MCP renderer**, whose behaviour differs:

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

**Design + hub path (2.0)** — Brother **PT-P710BT** on 24 mm TZe and a **NIIMBOT B1** on
40x30 rolls, both through a LAN Print Hub, 2026-11-14 (labels rendered by this plugin's
design layer were previewed against the live printers, which reported their loaded media. Real
prints that day went through the hub's own renderer, whose tape layout this one ports; a
first real print through `render.py print` on these backends is still to be done).

**Standalone path** — Brother **QL-810W** over the network (`brother_ql_network`,
`tcp://…:9100`), DK-22210 continuous and DK-11202 die-cut, on Ubuntu with `brother_ql`
0.9.4, Python 3.14 and Pillow 12.1.1. Verified end to end 2026-08-16: mDNS discovery,
registry, preview and print. `brother_ql_usb`, `ptouch_usb` and `cups` follow the same
code path but no hardware was on hand for them.

**MCP path** — Brother **PT-P710BT** (P-Touch Cube Plus), 24 mm laminated tape,
`ptouch-print v1.8`, Ubuntu. `ptouch-print` also supports PT-P700, PT-P750W, PT-D460BT,
PT-D610BT, PT-E550W, PT-P900Wc and others — the rendering there is model-independent,
but only the P710BT has been exercised end to end.

## History

- **2.0.0 (2026-11-14):** design layer (Iconify icons with search, fonts by name with
  download, auto two-line wrap, styles), pluggable backends (`http_bridge`, `print_hub`
  added; live tape detection), NIIMBOT media, and the per-user Label-Templates repo
  ([template](https://github.com/danielrosehill/Label-Templates-Template)). Folded in the
  private `niimbot-labels` plugin (NIIMBOT renderer layouts, niimblue-node bridge setup,
  hardware notes), whose repo was then deleted. The icon + text tape layout comes from
  [LAN Print Hub](https://github.com/danielrosehill/LAN-Print-Hub)'s renderer.
  `lan-print-scan` keeps documents, scanning and hub transport, and defers label design here.
- **1.x (2026-08 to 2026-11):** Brother QL/P-touch discovery, registry, DK/TZe catalogue,
  QR labels, templates, and the original P-touch MCP server.

## License

MIT — see [LICENSE](LICENSE). Vendored fonts are SIL OFL 1.1:
[Inter](https://github.com/rsms/inter) (`mcp-server/fonts/OFL.txt`) and
[Noto Sans Hebrew](https://github.com/notofonts/hebrew)
(`mcp-server/fonts/OFL-NotoSansHebrew.txt`). `ptouch-print` is a separate GPL-3.0
project.
