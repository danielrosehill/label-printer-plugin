---
name: setup
description: First-time setup for label printing - create the user's Label-Templates repository (printers, styles, templates), register each label printer with the backend that reaches it (CUPS, ptouch-print, brother_ql, a USB print bridge, or a LAN print hub), and save the user's style defaults (font, icon set, wrap length). Use on "set up label printing", "add my label printer", "my labels should use font X", or when render.py says no printers are registered.
---

# Set up label printing

Everything personal lands in the user's **Label-Templates** repository: the printer record
(`printers.md` + `printers.json`), styles and templates. The plugin's user-data dir only
stores where that repo is. Machine-local USB printers go in the machine registry. Ask only
what the machine can't tell you.

## 0. The Label-Templates repo

```bash
L='python3 ${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py'
$L repo status
```

No repo yet: ask the user one question, private (default) or public, and where to clone it.
Then:

```bash
$L repo create --name Label-Templates --dir ~/repos            # --public if they chose it
```

That runs `gh repo create --template danielrosehill/Label-Templates-Template --clone` and
records the path in `<user-data-root>/label-printer/config.json`. Already have one on another
machine: clone it, then `$L repo set <path>`. No `gh`: clone the template, re-init git, push
it wherever they like, then `repo set`. If the repo is public, keep LAN addresses out of
`printers.json` (use the machine registry for those).

## 1. Tooling

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" backends
```

`uv` is enough for rendering (render.py installs Pillow, resvg-py and qrcode itself). The
transport tools depend on the backend; `install-drivers` covers them.

## 2. Register printers

Run `profile-printers` to discover USB, mDNS and CUPS printers. For each, pick the backend
by how the printer is reached:

| Reached via | Backend | Register with |
|---|---|---|
| A CUPS queue (any make that has a driver) | `cups` | `--cups-queue NAME [--cups-option media=...]` |
| P-touch on this machine's USB | `ptouch_usb` | `--usb-id 04f9:20af` |
| Brother QL on the LAN / USB | `brother_ql_network` / `brother_ql_usb` | `--host IP` / `--usb-id` |
| A ptouch-print HTTP bridge on another machine | `http_bridge` | `--url http://host:port --bridge-type ptouch` |
| A NIIMBOT behind a niimblue-node server | `http_bridge` | `--url ... --bridge-type niimblue [--serial-port /dev/serial/by-id/...]` (`niimbot-bridge-setup`) |
| A LAN Print Hub | `print_hub` | `--url http://hub:9190 --target <target id or alias>` |

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry add --id pt-cube --model PT-P710BT \
  --backend print_hub --url http://hub.local:9190 --target ptouch --media TZe-251 \
  --alias ptouch --default --shared
```

- `--shared` writes to the repo's `printers.json` (committed and pushed), for printers every
  machine can reach (a hub or bridge on a VPN). Without it the entry is machine-local.
- Then write the printer's section in the repo's `printers.md`: model, how it is reached,
  usual and alternative media, dpi, quirks ("assume 24 mm, check tapeMm"), with dates.
- `--media` is the usual roll. Bridge and hub printers report loaded tape live, which wins.
- Die-cut printers that print off-centre: `--offset-mm -2` (negative shifts left), `--margin-mm`.
- NIIMBOT: `--density 1-5` (3 is the default).

## 3. Default style

Ask for a font only if the user named one or cares; otherwise the built-in style
(IBM Plex Sans Bold, filled `mdi` icons, wrap at 85 mm) stands.

```bash
R='uv run -q --script ${CLAUDE_PLUGIN_ROOT}/scripts/render.py'
$R style save mine --font "Inter Bold" --icon-prefix mdi --wrap-mm 85 --description "..."
$R style default mine
$R font "Inter Bold"        # confirm it resolves to a real file, not the fallback
```

Styles save to the repo's `styles.json` and are committed. The template repo ships a
`house` style; edit it rather than adding a parallel one if the user has no strong view.

```bash
$L repo commit -m "printers.md: add the P-touch"     # after hand edits
```

## 4. Prove it

Preview a short label on each printer (`design-label` step 3) and Read the PNG. Print one
only with the user's go-ahead, and ask whether it came out.
