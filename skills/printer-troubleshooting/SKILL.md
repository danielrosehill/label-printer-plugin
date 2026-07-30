---
name: printer-troubleshooting
description: Diagnose why a label did not print — printer unreachable, powered off, media errors, wrong tape width, or bridge connectivity. Use when a print tool fails, printer_status reports not ok, or the user says the printer isn't working.
---

# Printer troubleshooting

Work down this list. Most failures are the first entry, and the fix is physical.

## 1. The printer is asleep — by far the most common

P-touch printers auto-power-off when idle (60 minutes on the PT-P710BT, timed from the
last **print job**, not from USB activity).

**It cannot be woken from software.** When it powers off it leaves the USB bus
entirely — there is no endpoint left to poke, and the device is bus-powered with no
remote-wakeup bit. Charging it from an always-on port does not help.

If `printer_status` reports unavailable, say so plainly and ask the user to **press the
power button**. Do not retry in a loop, and do not offer to wake it.

**Permanent fix, worth mentioning once:** the timeout can be set to `None`, but only
from Brother's Printer Setting Tool on Windows or macOS over USB. It is stored in the
printer's NVRAM, so it is a one-time job. It is *not* reachable from Linux by any
route — not `ptouch-print`, not Bluetooth, not the mobile apps, and not under Wine.
See [`docs/linux-printer-settings.md`](../../docs/linux-printer-settings.md).

## 2. The bridge is unreachable

An error mentioning `bridge unreachable` means the MCP cannot reach the print bridge —
the printer itself may be perfectly fine.

- Confirm `PRINT_BRIDGE_URL` points at the right host and port (default `:9180`).
- On the bridge host: `systemctl status <bridge-service>` and
  `curl -s localhost:9180/health`.
- If the bridge and the MCP are on different machines, check the network path between
  them before touching the printer.

## 3. Media errors

`printer_status` surfaces the printer's error word.

| Error | Meaning | Action |
|---|---|---|
| `0x0000` | OK | — |
| `0x0001` | No media, or the lid is open | Close the lid; check a cassette is seated |
| `0x0100` | "Replace media" | Usually a **rejected job**, not an empty cassette — see below |
| `0x0400` | Communication error | Re-seat the USB cable |

`0x0100` on a printer that visibly has tape is the signature of a **missing init
sequence** in `ptouch-print` — some models need the P700-family init flag and silently
fail without it, exiting 0 while printing nothing. The printer then stays in the error
state and refuses further jobs until power-cycled. Power-cycle it, and if it recurs on
every job, the driver needs patching rather than the printer needing tape. The patch
and the full write-up are in
[ptouch-cube-print-bridge](https://github.com/danielrosehill/ptouch-cube-print-bridge).

## 4. Layout looks wrong

- **Subtext missing?** Tape narrower than 18 mm has no room for a second line and it is
  dropped deliberately. Check `tapeMm` in `printer_status`.
- **Label far longer than expected?** A heading too wide to shrink legibly widens the
  label instead. Shorten the heading, or move the detail into `subtext`.
- **Blank tape before the label?** The print head sits ~25 mm behind the cutter. The
  bridge trims this with `--precut`; if you are seeing it, `--precut` is not being passed.

## What not to do

- Don't retry a failed print automatically. Printing is physical and consumable, and a
  "failure" that actually printed will duplicate the label. Confirm with the user
  whether anything came out before re-sending.
- Don't write a status-poll keep-alive to stop the printer sleeping. It cannot work —
  only printing defers the timer — and it produces convincing-looking logs while
  achieving nothing.
