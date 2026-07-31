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
| `label_canvas` | The pixel canvas to render your own artwork onto |
| `preview_image_label` | Show submitted artwork as it would reach the printer, without printing |
| `print_image_label` | Print arbitrary PNG/JPEG artwork you rendered yourself |

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

Brother **PT-P710BT** (P-Touch Cube Plus), 24 mm laminated tape, `ptouch-print v1.8`,
Ubuntu. `ptouch-print` also supports PT-P700, PT-P750W, PT-D460BT, PT-D610BT,
PT-E550W, PT-P900Wc and others — the rendering here is model-independent, but only the
P710BT has been exercised end to end.

## License

MIT — see [LICENSE](LICENSE). Vendored fonts are SIL OFL 1.1:
[Inter](https://github.com/rsms/inter) (`mcp-server/fonts/OFL.txt`) and
[Noto Sans Hebrew](https://github.com/notofonts/hebrew)
(`mcp-server/fonts/OFL-NotoSansHebrew.txt`). `ptouch-print` is a separate GPL-3.0
project.
