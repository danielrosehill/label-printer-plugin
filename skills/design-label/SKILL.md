---
name: design-label
description: Turn a request like "four labels for the wine bottles with a wine icon" into a finished label sized to the loaded media, with a good icon, the user's font and a compact layout, then print it. Use on "print me N labels for X", "label with a Y icon", "make it two lines", "use Inter", "find an icon for X", or any label request where the look matters.
---

# Design a label

The design layer: content -> icon -> layout -> preview -> print. Printing itself goes
through whatever backend the printer is registered with (`print-label`).

```bash
R='uv run -q --script ${CLAUDE_PLUGIN_ROOT}/scripts/render.py'   # or python3 with Pillow, resvg-py, qrcode installed
```

## 0. Know the printers

Once per session: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py repo status`, then read
`printers.md` in the user's Label-Templates repo: which printer is the default, what tape
is usually loaded, quirks. Check `templates/` for a saved label before designing from
scratch (`labelctl.py template list`). No repo: run `setup`.

## 1. Read the request

| They say | Becomes |
|---|---|
| "four labels for wine bottles" | `-t "Wine Bottles" -n 4` |
| "with a wine icon" | `-i` from an icon search (step 2) |
| "on the P-touch / niimbot" | `-p <id or alias>` |
| "two lines", "stack it" | `--layout two-line` or a literal `\n` in `-t` |
| "in IBM Plex / Inter" | `--font "IBM Plex Sans Bold"` (a weight word is optional, Bold is the default) |
| "white on black", "with a border" | `--invert`, `--border` |

No icon asked for: suggest one if an obvious filled icon exists, otherwise go text-only. Don't ask.

## 2. Pick the icon

```bash
$R icons search "wine"        # filled icons first; outline/thin variants print faint
```

Prefer `mdi:*` (filled, consistent weight). A bare name like `-i lightbulb` resolves to the
style's `icon_prefix`. Read the candidates' names; if two are plausible, preview both.

## 3. Preview and look

```bash
$R preview -p ptouch -t "Wine Bottles" -i mdi:glass-wine -o /tmp/label.png
```

Then Read `/tmp/label.png`. The JSON says what happened: `media` (from the printer's
live report when it has one), `size_mm`, `lines` (the wrap it chose), `wrapped` (why),
`font.source` (`installed`, `cache`, `downloaded`, or `fallback` if the font name was wrong).

What the layouts do:

- **Continuous tape/roll** (TZe, DK continuous): height is fixed by the tape, length grows.
  `auto` keeps one line until it would pass `wrap_mm` (default 85 mm), then picks the
  two-line split giving the shortest label. Icon and QR sit at the left at full height.
- **Die-cut** (NIIMBOT rolls, DK die-cut): fixed size. `auto` puts the icon left on wide
  labels and on top on squarer ones, splitting text over two lines when that lets it grow.
- `one-line`, `two-line`, `text`, `icon` (icon only), `icon-top`, `qr` force a layout.

Check before printing: text not cramped against the icon, no stray one-word line, the
icon is solid. Skip the Read only for a repeat of a label the user already approved.

## 4. Print

```bash
$R print -p ptouch -t "Wine Bottles" -i mdi:glass-wine -n 4
```

Same flags as the preview. Over 5 copies, say what is about to print first; over 20 is
refused. `printed: true` means the backend accepted the job, **not** that a label came
out: tape printers can acknowledge and drop a job (cover open, Bluetooth app holding the
printer, a USB glitch). On a first print or after trouble, ask whether it came out.

## Styles and fonts

A style is a saved bundle of font, icon prefix, layout and wrap length, in the
Label-Templates repo's `styles.json` (committed on save). The default style applies unless `--style` or the printer's
own `style` says otherwise.

```bash
$R style list
$R style save house --font "IBM Plex Sans Bold" --icon-prefix mdi --wrap-mm 85
$R style default house
$R font "Inter SemiBold"     # where a font resolves; downloads it if it is not installed
```

Fonts resolve: file path -> installed (fontconfig) -> cache -> download (IBM Plex from
IBM's repository, anything else from Google Fonts) -> bundled Inter ExtraBold. Hebrew
lines switch to Noto Sans Hebrew automatically.

When the user reacts to a printed label ("too wide", "love that icon", "bigger text"),
save it into their style (`style save <default> --wrap-mm 70`) so the next label follows.
A label they will print again goes in `label-templates`.

## Design-only preview

No printer registered, or designing for another machine: pass media instead.

```bash
$R preview -t "Hall" -i lightbulb -m NIIMBOT-40x30 -o /tmp/n.png    # also 24mm, 12mm, DK-22210 ...
```
