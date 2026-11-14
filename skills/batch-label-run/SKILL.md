---
name: batch-label-run
description: Print many different labels in one run — a whole shelf of boxes, a list of assets, or labels generated from a CSV or inventory export. Use when the user wants to label multiple distinct items at once rather than one at a time.
---

# Batch label run

Two routes:

- **Any registered printer (scripts):** one `render.py print` per distinct label, with
  `-n` for its copies, in the order of the list. Same flags as `design-label`; a saved
  template keeps the per-row command short (`--template box --text "S-014"`).
- **The bundled MCP server (P-touch bridge setups):** `print_batch` takes up to 50
  different labels and prints them as one job, so the ~25 mm leader is paid once.

```bash
R='uv run -q --script ${CLAUDE_PLUGIN_ROOT}/scripts/render.py'
$R preview -p ptouch --template box --text "S-014 Cables" -o /tmp/longest.png   # the longest row first
$R print   -p ptouch --template box --text "S-014 Cables" -n 2
```

## Shape

```
print_batch(labels=[
  {"heading": "A-100", "subtext": "Instant Pot",      "qr_url": "https://inv.example/a/100", "copies": 1},
  {"heading": "A-101", "subtext": "Stand mixer",      "qr_url": "https://inv.example/a/101", "copies": 1},
  {"heading": "S-003", "subtext": "Cables & adapters","qr_url": "https://inv.example/s/3",   "copies": 2},
])
```

`heading` is the only required field. Omit `qr_url` for a text-only label. Note the
batch tool takes raw headings — apply the `A-` / `S-` prefixes yourself here, since it
does not run them through the template tools.

## Before you print

Batch runs are where tape gets wasted, so spend a moment first.

1. **Count the tape.** Total length ≈ `sum(copies) × 62 mm` for QR labels, plus about
   25 mm of leader trim per job. Thirty labels is roughly two metres. The printer
   **cannot** report remaining tape — ask the user to eyeball the cassette before a
   long run.
2. **Preview one representative label**, especially the longest name in the set, with
   `render.py preview` (or `preview_label` on the MCP route). One bad layout repeated thirty times is thirty wasted labels.
3. **Show the user the list and get a yes.** Print the headings and copy counts as a
   table. This is a physical, irreversible, consumable action — confirm it.
4. Check the printer is up immediately before starting (`printer_status`, or a
   `preview` against a bridge/hub printer, which reports its live tape).

## When it fails partway

`print_batch` stops at the first failure and reports `printedBefore` — the number of
labels that completed. **Do not blindly re-run the whole batch**; you will duplicate
everything before the failure. Re-run only the remainder, slicing the list from
`printedBefore`.

The usual cause is the printer powering off mid-run (it sleeps on idle and cannot be
woken over USB — see `printer-troubleshooting`).

## Generating from a file

When labels come from a CSV or inventory export:

- Read the file and map columns to `heading` / `subtext` / `qr_url` explicitly. Show
  the user the mapping before printing.
- Chunk anything over 50 rows into separate calls, and confirm between chunks rather
  than firing them all off.
- Watch for empty or malformed URLs in the data — a label with a dead QR is worse than
  no label, because it looks fine.
