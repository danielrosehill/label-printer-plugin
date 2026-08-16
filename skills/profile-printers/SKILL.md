---
name: profile-printers
description: Find label printers on this machine and LAN and record them in a local registry with a name, id and description so later prints can pick one.
---

# Profile the label printers

Builds the registry every other skill reads. Run it once per machine, and again
whenever a printer moves network, gets replaced, or a second one appears.

The registry is **machine-local** — it lives in the vault, not the user-data
root, because it holds LAN addresses that are true on one network only. Ask the
resolver rather than hard-coding the path:

```bash
sh "${CLAUDE_PLUGIN_ROOT}/scripts/paths.sh" --json
```

## 1. See what is out there

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" discover
```

Three probes, merged: **mDNS** (`avahi-browse`) for networked printers, **USB**
(`lsusb`, matched against a table of Brother product ids), and **CUPS**
(`lpstat -v`) for anything already set up as a queue. Each result carries a
`suggested_backend`, a `media_family` and a `suggested_id`.

Three things worth knowing before you trust a quiet result:

- **A network label printer is usually not a CUPS queue.** The QL-810W this was
  written against answers on `:9100` and does not appear in `lpstat` at all. An
  empty `lpstat` is not evidence that there is no printer.
- **`brother_ql discover` only ever walks USB**, and in 0.9.4 it raises
  `NotImplementedError: Backend None not implemented` unless `-b` comes *before*
  the subcommand. Do not use it to look for a networked printer — use mDNS.
- **USB printers that are asleep may not enumerate.** P-touch models auto-power-off
  and cannot be woken over USB. If the user expects one and it is absent, ask them
  to press the power button before concluding anything.

If discovery returns nothing at all, check the tooling is present before
declaring the network empty:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" backends
```

No `avahi-browse` means no mDNS discovery — that is a missing tool, not a
missing printer. The `install-drivers` skill fixes it.

## 2. Name each one

Discovery gives a model and an address. It cannot give the thing that actually
matters when the user later says *"print this on the office one"* — so ask.

For each printer worth keeping, get:

| Field | Why |
|---|---|
| `id` | Short, kebab-case, typed in later. `suggested_id` is a fine default. |
| `name` | Human label — "Brother QL-810W". |
| `description` | **Where it is and what it is for.** This is what disambiguates. |
| `media` | Which roll or cassette is physically loaded right now. |

Ask about description and media together, in one question, and offer the
discovered values as defaults. Do not interrogate them field by field.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry add \
  --id ql-810w --model QL-810W --host 192.168.68.63 \
  --name "Brother QL-810W" \
  --description "Office shelf, die-cut DK rolls" \
  --media DK-22210
```

`--backend` is inferred from the model and whether a host was given; pass it
only to override. For a USB printer pass `--usb-id 04f9:20af` and no host; for
one reached through CUPS pass `--cups-queue <name>`.

## 3. Record what is loaded

The registry's `installed_media` is what decides the pixel canvas, so a wrong
value produces a wrongly-sized label rather than an error. Update it whenever
the roll changes:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry set-media --id ql-810w --media DK-22205
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" media list
```

`set-media` refuses media from the wrong family — TZe tape cannot go in a QL,
and being told so is more useful than a label that silently comes out wrong.

## Judgement

- **Do not register every printer discovery finds.** Ordinary document printers
  turn up in the CUPS probe. Register label printers, and say which you skipped.
- **Ask before overwriting an existing entry.** `registry add` refuses a
  duplicate id on purpose; removing and re-adding loses the description the user
  wrote, so offer `set-media` first if the roll is all that changed.
- A printer that discovery found but that reports `raw_port_9100: false` is on
  the network but not accepting jobs — it is asleep, or the port is blocked.
  Register it, and say so.
- **Zebra and DYMO can be discovered and registered but not yet printed to.**
  If one turns up, register it if the user wants the record, and be explicit
  that printing will fail until that backend exists. See `docs/backends.md`.

## Finishing

Show the registry as it now stands and where it was written:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/labelctl.py" registry list
```

Then say what they can do next — print one label to check the media setting is
right before anyone relies on it.
