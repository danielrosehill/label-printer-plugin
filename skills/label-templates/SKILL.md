---
name: label-templates
description: Save a label the user prints repeatedly as a named template in their Label-Templates repository, list what is saved, and print from one with fields overridden. Use on "save this as a template", "print the shelf label again", "what label templates do I have".
---

# Label templates

Templates live in the user's **Label-Templates** repository (created by `setup` from
`danielrosehill/Label-Templates-Template`), under `templates/<printer-or-media>/<name>.json`.
Without a repo they fall back to `<user-data-root>/label-printer/templates/`.

```bash
L='python3 ${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py'
R='uv run -q --script ${CLAUDE_PLUGIN_ROOT}/scripts/render.py'
$L repo status          # which repo, its git state, where styles/printers/templates resolve
```

## Save one

```bash
$L template save --name flat-ethernet-cable --printer ptouch --media TZe-251 \
  --text "Flat Ethernet Cable" --icon mdi:ethernet --copies 2 \
  --description "Reference look for item labels: icon left, two lines, 80 mm"
```

- The folder defaults to the printer id (else the media); `--folder tape-12mm` sets it.
- Store what stays the same; leave the varying field as a stub ("Item Name").
- Write `description` for someone who has forgotten why it exists.
- Saving commits and pushes the repo (`--no-commit` to batch several, then `$L repo commit -m "..."`).

When the user approves a printed label ("that one's great"), offer to save it.

## Use one

```bash
$L template list
$R preview --template flat-ethernet-cable --text "Patch Cables" -o /tmp/l.png
$R print   --template pt-p710bt-24mm/item-with-icon --text "Spare Fuses" --icon mdi:fuse -n 2
```

Flags win over template fields. Name a template by `name`, or `folder/name` when two share
a name. A template's `media` is a preference, not an order: when the printer reports a
different tape loaded, the label is rendered for what is loaded and the JSON says
`media_mismatch`. Tell the user (a 12 mm template on 24 mm tape still prints, just bigger).

## Manage

```bash
$L template show shelf-edge
$L template remove shelf-edge       # commits the removal
```

The files are plain JSON; hand edits are fine, then `$L repo commit -m "..."`.
