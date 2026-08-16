---
name: print-label
description: Print a label on a registered printer at a chosen media size, with an optional second line. Previews first when the layout is uncertain.
---

# Print a label

Works against the registry that `profile-printers` built, so it is
printer-agnostic: pick a printer by id, or let it pick when only one is
registered.

## Before printing

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry list
```

If the registry is empty, run `profile-printers` first — do not guess an
address.

## Preview, then print

**`preview` never opens a socket to the printer.** That separation is
load-bearing: `brother_ql print` converts *and* transmits in one step with no
dry-run flag, so the only safe way to see a label before spending media is to
render it and stop.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py" preview \
  --text "Spare fuses" --subtext "Garage shelf B" --printer ql-810w -o /tmp/label.png
```

Read the PNG back and look at it when the layout is uncertain — a long heading,
non-Latin text, or an unfamiliar media size. For routine labels skip straight to
printing; a preview the user did not ask for is a round trip they did not want.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py" print \
  --text "Spare fuses" --subtext "Garage shelf B" --printer ql-810w --copies 2
```

Both commands print a JSON object with a `printed` field. `printed: false` means
nothing was sent — do not report a preview as a completed print.

## Choosing the media size

The canvas comes from the printer's `installed_media`, so normally you pass
nothing. Override with `--media` **only when the user has physically changed the
roll**, and record it afterwards so the next print is right too:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" media list
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" media show DK-11202
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry set-media --id ql-810w --media DK-11202
```

Two geometries behave differently and it is worth saying which the user is on:

- **Continuous roll** (`DK-22210`, all TZe) — the label grows to fit the text,
  capped at 90 mm. You choose the length by choosing the words.
- **Die-cut** (`DK-11202`, `DK-11201`, the round ones) — the length is fixed by
  the label itself. Text shrinks to fit; it cannot overflow onto the next one.

An `installed_media` that does not match the physical roll produces a
*wrong-sized label*, not an error. If a print comes out visibly misaligned,
suspect that before suspecting the printer.

## Judgement

- **Confirm before more than a few copies.** Media is consumable and no Brother
  label printer reports how much is left. Above 5 copies, say what is about to
  print and get a yes. The renderer refuses more than 20 outright.
- **Ask before printing a placeholder.** A heading that is obviously a stand-in,
  or a QR pointing at `example.com`, is a label that has to be redone. One
  question is cheaper than one wasted label.
- **Do not loop this for a batch.** Several different labels is one call each,
  and that is fine, but tell the user the total first.
- **Two-line labels need height.** Below roughly 18 mm the second line is
  dropped rather than rendered illegibly. On 12 mm tape, put everything in
  `--text`.
- For a QR label see `qr-labels`; for something printed repeatedly see
  `label-templates`.

## When it fails

`print` returns the backend's exit code and stderr. Common causes, in the order
worth checking:

| Symptom | Usually means |
|---|---|
| network printer, connection refused | asleep or off the LAN — `discover` reports `raw_port_9100` |
| USB P-touch not found | auto-powered-off; it cannot be woken over USB, someone must press the button |
| job accepted, nothing emerges | roll ran out, or the cover is open |
| `LIBUSB_ERROR_ACCESS` | user not in the `lp` group — see `install-drivers` |
| `deprecation warning: brother_ql.devicedependent` | noise, not a failure; it appears on successful jobs too |

`printer-troubleshooting` goes further. Note that a reachable printer says
nothing about whether it has media — reachability is a TCP connect, and the
printer has no ink to run out of, so a failed print on a reachable printer is
almost always the roll or the cover.
