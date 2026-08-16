---
description: Label printing — discover printers, print a label, manage templates, install drivers
argument-hint: "[printers|print|qr|templates|drivers|status] ..."
---

# /label

Route on the first argument. With no argument, show this table and ask.

| Argument | Skill | For |
|---|---|---|
| `printers`, `discover`, `profile` | `profile-printers` | find label printers and register them |
| `print`, (bare text) | `print-label` | print a label |
| `qr` | `qr-labels` | print a label carrying a QR code |
| `templates`, `template` | `label-templates` | save and reuse a label |
| `drivers`, `install`, `setup` | `install-drivers` | install the Linux tooling |
| `status`, `trouble`, `broken` | `printer-troubleshooting` | nothing printed — work out why |

Arguments after the first are the label content or the printer id; pass them
through rather than re-asking.

If the registry is empty for anything but `printers` and `drivers`, run
`profile-printers` first — there is nothing to print to yet.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry list
```
