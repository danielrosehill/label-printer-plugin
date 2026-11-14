---
name: qr-labels
description: Print a label carrying a QR code — what to encode, how big it has to be to scan, and how it shares the label with text.
---

# QR labels

A QR label is a normal label with `--qr`. What makes it its own skill is that a
QR can be printed perfectly and still be useless, and neither the printer nor the
render will tell you.

```bash
uv run -q --script "${CLAUDE_PLUGIN_ROOT}/scripts/render.py" preview \
  --text "A-100" --subtext "Instant Pot" \
  --qr "https://inventory.example/a/100" --printer ql-810w -o /tmp/label.png

uv run -q --script "${CLAUDE_PLUGIN_ROOT}/scripts/render.py" print \
  --text "A-100" --subtext "Instant Pot" \
  --qr "https://inventory.example/a/100" --printer ql-810w
```

The QR sits square on the left, sized to the media height; text takes the rest.
On die-cut media it is capped at 45% of the label length so it cannot squeeze the
text into a sliver.

## What to encode

- **A URL that will still resolve.** The point of a QR on a physical object is
  that someone scans it in two years. A link to a local dev server, a session
  URL, or anything with a token in it is worth flagging before printing.
- **Short beats long.** QR density rises with payload; a long URL on 12 mm tape
  produces a code too fine for the print head to resolve. Prefer a short
  canonical link over a tracking-laden one.
- **Plain text is valid too** — a serial number, a wifi credential, a phone
  number. It does not have to be a URL.

## Whether it will actually scan

Three things decide this, and only the first is visible in the preview:

1. **Module size.** The renderer sizes the QR to the media height, so narrow
   tape means a physically small code. On 12 mm tape a long URL will not scan
   reliably no matter how clean the print.
2. **Print resolution.** DK media prints at 300 dpi, TZe at 180. The same QR is
   coarser on tape.
3. **Contrast and material.** Clear and matte-silver stock scans worse than
   white paper.

The renderer uses error-correction level M, which tolerates roughly 15% damage —
a reasonable default for a label that will get scuffed. It does not compensate
for a code that is simply too small.

**Scan the first one before printing the batch.** This is the whole judgement of
this skill: a QR label is verified by a phone camera, not by looking at it. If
the user is about to print twenty, print one, ask them to scan it, then print the
rest.

## Combining with text

Always put something human-readable on the label as well. A QR-only label is
unidentifiable when the code will not scan, which is exactly when you need to
know what it was.

- `--text` is the large line — the id, the thing you read across a room.
- `--subtext` is the small line — the name, dropped automatically on 12 mm tape and narrower.

## Generating a QR on its own

Occasionally the user wants the code as an image rather than a label — for a
document, a sign, a slide:

```bash
qrencode -o /tmp/qr.png -s 10 -m 1 "https://example.com/thing"
```

`-s` is pixels per module, `-m` the quiet-zone margin in modules. Keep `-m` at 1
or more; a QR with no quiet zone fails to scan against a busy background even
though it looks fine.

## Judgement

- **Ask before printing a placeholder URL.** `example.com`, `localhost`, an
  unresolved template variable — these produce a label that must be redone.
- **One object, one code.** If the user is labelling several things, each needs
  its own URL; printing copies of one QR onto different objects defeats the
  purpose. Check which they meant before printing copies.
- If the payload is long and the tape is narrow, say so before printing rather
  than after — suggest a shorter URL or wider media.
