---
name: label-a-storage-unit
description: Print a QR-coded label for a storage box, bin, shelf or crate — unit id big, contents summary underneath, QR linking to the unit's page. Use when the user asks to label a box, bin, shelf, tote or storage unit.
---

# Label a storage unit

Same layout as an asset label, different id convention: storage ids take the `S-`
prefix, and the second line describes *what is inside* rather than naming one item.

## What you need

| Field | Required | Notes |
|---|---|---|
| `unit_id` | yes | Bare number is fine — `3` prints as `S-3`. Pass `S-003` and it is left alone. |
| `contents` | no | Short summary, e.g. `Cables & adapters`. Not an inventory — the QR carries that. |
| `url` | no | Encoded in the QR. The unit's page in your inventory system. |
| `copies` | no | Defaults to 1. Max 20. |

## Steps

1. Call `printer_status` if the printer's state is unknown.
2. Call `print_storage_label`.

## Judgement

- **Keep `contents` short.** It is a shelf-legible hint, not a manifest — two or three
  words. "Cables & adapters" is right; "USB-C cables, HDMI, DisplayPort, adapters and
  chargers" wraps to two cramped lines and reads worse. If the user gives a long list,
  offer to shorten it rather than printing it.
- **Boxes usually want more than one label.** A box labelled on one face only is
  invisible on a shelf. Two or three copies — one per visible face — is a sensible
  default to *suggest*, but don't silently multiply what the user asked for.
- Labelling a whole shelf of boxes at once is `print_batch`.

## Example

> "Label box 3 — it's cables and adapters."

```
print_storage_label(unit_id="3", contents="Cables & adapters",
                    url="https://inventory.example/s/3", copies=2)
```

after confirming the second copy with the user.
