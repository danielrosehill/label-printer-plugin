---
name: label-templates
description: Save a label you print repeatedly as a reusable template, list what is saved, and print from one with fields overridden.
---

# Label templates

A template is a label the user prints again and again with one field changing —
a shelf tag, a cable label, a decanted-container label. Saving it means not
re-deciding the media, the printer and the wording every time.

Templates are **user content**, so they live under the user-data root rather
than the machine-local vault — they are worth mirroring to another machine, and
they contain nothing network-specific. Ask the resolver for the path:

```bash
sh "${CLAUDE_PLUGIN_ROOT}/scripts/paths.sh" --json
```

`data_source` in that output says which rule fired. `adopted-existing` means the
user already keeps plugin content under that root and this plugin is filing
alongside it rather than starting a second one — worth mentioning once, in plain
terms, when you first report the path.

## Save one

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" template save \
  --name "shelf-bin" \
  --text "BIN" --subtext "Workshop" \
  --media DK-22210 --printer ql-810w \
  --description "Workshop bin tag; number and QR set per use"
```

Store the parts that stay the same and leave the varying field as a stub. The
`description` is what makes it findable later — write it for someone who has
forgotten why the template exists.

## Use one

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" template list
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" template show shelf-bin

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py" print \
  --template shelf-bin --text "BIN 14" --qr "https://inv.example/b/14"
```

Anything passed explicitly wins over the template; anything omitted falls back to
it. So the printer and media come from the template and only the changing field
is typed.

## Manage them

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" template remove shelf-bin
```

To edit one, `show` it, then `save` over it with the same `--name` — the file is
plain JSON named after the slug, so hand-editing is fine too.

## Judgement

- **Offer to save a template rather than creating one unasked.** The signal is
  the user printing something structurally identical for the second or third
  time; a template made from a one-off is clutter.
- **A template naming a printer is a portability trade.** It saves typing on
  this machine and is wrong on another, where the id may not exist. For
  templates the user is likely to sync, leave `--printer` off and let the
  registry decide.
- **Do not put a specific QR in a template** unless every print really does
  point at the same page. A stale URL copied across twenty labels is the
  expensive mistake here.
- Removing a template is not destructive in any meaningful sense — but it is
  still the user's file. Say which file you are deleting before you do it.
