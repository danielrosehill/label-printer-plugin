---
description: Label printing — design and print labels, set up printers and the Label-Templates repo, manage templates, install drivers
argument-hint: "[printers|print|qr|templates|drivers|status] ..."
---

# /label

Route on the first argument. With no argument, show this table and ask.

| Argument | Skill | For |
|---|---|---|
| `setup` | `setup` | Label-Templates repo, printers, default style |
| `printers`, `discover`, `profile` | `profile-printers` | find label printers and register them |
| (bare text), `design`, `icon`, `font` | `design-label` | design a label (icon, font, layout) and print it |
| `print` | `print-label` | print through the printer's backend |
| `niimbot` | `niimbot-bridge-setup` | set up or fix a NIIMBOT bridge |
| `qr` | `qr-labels` | print a label carrying a QR code |
| `templates`, `template` | `label-templates` | save and reuse a label |
| `drivers`, `install` | `install-drivers` | install the Linux tooling |
| `status`, `trouble`, `broken` | `printer-troubleshooting` | nothing printed — work out why |

Arguments after the first are the label content or the printer id; pass them
through rather than re-asking.

If the registry is empty for anything but `setup`, `printers` and `drivers`, run
`setup` first — there is nothing to print to yet.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry list
```
