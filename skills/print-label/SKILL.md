---
name: print-label
description: Print a label on a registered printer through its backend (CUPS, ptouch-print, brother_ql, a USB print bridge or a LAN print hub), at the size of the loaded media. Use on "print a label", "print it", "send that to the P-touch". For how the label should look (icon, font, two lines) use design-label first.
---

# Print a label

```bash
R='uv run -q --script ${CLAUDE_PLUGIN_ROOT}/scripts/render.py'
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry list    # empty -> run `setup`
```

Read `printers.md` in the user's Label-Templates repo (`labelctl.py repo status` finds it)
before the first print of a session. Printers are picked with `-p <id or alias>`; omitted, the registry's `default` (or its
only printer) is used. Nothing registered: run `setup`, never guess an address.

## Preview, then print

```bash
$R preview -p ptouch -t "Spare fuses" --subtext "Garage shelf B" -o /tmp/label.png
$R print   -p ptouch -t "Spare fuses" --subtext "Garage shelf B" -n 2
```

**`preview` never sends a job.** For bridge and hub printers it does read the printer's
status to learn the loaded tape (`--no-live` skips that). Read the PNG back when the
layout is new; skip it for a repeat the user already approved.

The JSON's `printed` is what the backend acknowledged. `printed: false` means nothing
was sent or the backend refused it. `printed: true` still isn't proof of a label: say
"sent", and ask if it came out on a first print or after trouble.

## Backends (set per printer in the registry)

| backend | Path |
|---|---|
| `cups` | `lp -d <cups_queue>` plus any `cups_options`. The generic default |
| `ptouch_usb` | `ptouch-print --image` on local USB |
| `brother_ql_network` / `brother_ql_usb` | `brother_ql print` over TCP 9100 / USB; the image is rotated and sized to the head for it |
| `http_bridge` | POST the PNG to a bridge: `bridge_type: ptouch` (ptouch-print bridge) or `niimblue` (niimblue-node) |
| `print_hub` | POST the PNG to a LAN Print Hub `target`; the hub queues and routes it |

## Media

The canvas comes from, in order: `--media`; the printer's live report (bridge/hub tape
printers report `tapeMm`); the registry's `installed_media`. Override with `--media` only
when the user physically swapped the roll, then record it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" media list
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry set-media --id ql-810w --media DK-11202
```

- **Continuous** (TZe tape, DK continuous): fixed height, the label grows with the text;
  `design-label` wraps it to two lines past ~85 mm.
- **Die-cut** (DK die-cut, NIIMBOT rolls): fixed size; text shrinks to fit.

A recorded media that doesn't match the physical roll gives a wrong-sized label, not an
error. Suspect that first when a print comes out misaligned.

## Judgement

- **Over 5 copies:** say what is about to print and get a yes. Over 20 is refused.
- **Placeholders:** a heading that is obviously a stand-in, or a QR to `example.com`, gets one question first.
- **Batches:** several different labels are one call each; give the total first (`batch-label-run`).
- **Second lines need height:** below ~14 mm tape `--subtext` is dropped; put both lines in `--text` with `\n`.
- **Don't auto-retry.** A "failed" job that printed would duplicate the label. Ask first.

## When it fails

| Symptom | Usually means |
|---|---|
| network printer, connection refused | asleep or off the LAN; `discover` reports `raw_port_9100` |
| USB P-touch not found / bridge health `ok: false` | powered off (it can't be woken over USB), or unplugged |
| `printed: true`, nothing came out | cover open, roll out, a phone app holding the printer over Bluetooth, or a USB drop; see `printer-troubleshooting` |
| `LIBUSB_ERROR_ACCESS` | user not in `lp`; see `install-drivers` |
| hub `state: failed` | the `error` field is the printer-side reason |

`printer-troubleshooting` goes further; NIIMBOT bridges have their own table in `niimbot-bridge-setup`.
