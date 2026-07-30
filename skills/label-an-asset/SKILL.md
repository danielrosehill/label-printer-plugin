---
name: label-an-asset
description: Print a QR-coded inventory label for a single asset — asset number big, item name underneath, QR linking to the item's page. Use when the user asks to label an item, print an asset tag, or tag something for inventory.
---

# Label an asset

Prints the standard asset label: QR code on the left, asset id in large bold type,
item name beneath it.

## What you need

| Field | Required | Notes |
|---|---|---|
| `asset_id` | yes | Bare number is fine — `100` prints as `A-100`. Pass `A-100` and it is left alone. |
| `name` | no | Item name, e.g. `Instant Pot`. Long names wrap to two lines automatically. |
| `url` | no | Encoded in the QR. The item's page in your inventory system. |
| `copies` | no | Defaults to 1. Max 20. |

If the user gives a URL and an asset number but no name, print it — the QR carries the
detail. Don't block on a missing name.

## Steps

1. If the user has not said the printer is on, call `printer_status` first. It is
   cheap and the printer sleeps often.
2. **Only when the layout is uncertain** — an unusually long name, an id longer than
   about 8 characters, or non-Latin text — call `preview_label` and check the render
   before spending tape. For routine labels skip straight to printing.
3. Call `print_asset_label`.

## Judgement

- **Confirm before printing more than a few copies.** Tape is consumable and the
  printer cannot report how much is left. For `copies` above 5, say what you are about
  to print and get a yes.
- **One asset, several copies** is `print_asset_label(copies=N)`. **Several different
  assets** is `print_batch` — use that instead of looping this tool.
- If the user gives a URL that is clearly a placeholder (`example.com`), ask before
  printing; a wrong QR is a label that has to be redone.

## Example

> "Here's the link, asset number is 100, it's an Instant Pot — print three copies."

```
print_asset_label(asset_id="100", name="Instant Pot",
                  url="https://inventory.example/a/100", copies=3)
```

Prints three identical 62 mm labels reading **A-100 / Instant Pot** with a scannable QR.
