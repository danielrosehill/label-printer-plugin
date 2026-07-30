# What the Linux driver exposes — and what it doesn't

If you drive a Brother P-touch from Linux, you are almost certainly using
[`ptouch-print`](https://git.familie-radermacher.ch/linux/ptouch-print.git). It is a
good tool, but it is a **print-only** driver. It has no notion of device settings, and
no amount of digging through its options will turn one up.

This page records the actual surface, so you can stop looking.

Verified **2026-07-30** against `ptouch-print v1.8.r15.gf7cce68+` talking to a
**Brother PT-P710BT** over USB on Ubuntu.

## The full option list

```
--copies=<number>          --debug
--font=<file>              --font-margin=<size>
--font-size=<size>         --force-tape-width=<px>
--timeout=<seconds>        -w, --write-png=<file>

print commands:
-a, --align=<l|c|r>        --chain
-c, --cutmark              -i, --image=<file>
-n, --newline=<text>       --precut
-p, --pad=<n>              -t, --text=<text>

other commands:
--info                     --list-supported
```

That is everything. Every one of those is about *this print job*. None of them touch
the printer's stored configuration.

## What `--info` can tell you

`--info` is the only read path into the device, and it reports the tape, not the
settings:

```
PT-P710BT found on USB bus 3, device 4
printer has 180 dpi, maximum printing width is 128 px
maximum printing width for this tape is 128px
media type = 0x01 (Laminated tape)
media width = 24 mm
tape color = 0x01 (White)
text color = 0x08 (Black)
error = 0x0000
```

Useful: tape width, media type, tape and text colour, and an error word. Not
available: remaining tape length, auto-power-off timeout, Bluetooth state, or
anything else in NVRAM.

## Auto power-off: not settable from Linux

**This is the one that costs people an afternoon.** The printer powers itself off
after a period of inactivity (60 minutes from the last *print job* on the P710BT —
status reads do not defer it), and it cannot be woken over USB, because when it powers
off it leaves the USB bus entirely. Someone has to physically press the button.

The setting exists. You just cannot reach it from Linux. Confirmed dead ends:

| Route | Why it fails |
|---|---|
| `ptouch-print` | No device-settings support at all — see the option list above |
| Bluetooth | Cannot carry device settings, by design |
| Brother's mobile apps (Design&Print, iPrint&Label) | Do not expose the setting |
| Brother's Printer Setting Tool under Wine | The tool reaches the printer through a Windows **kernel-mode** driver; Wine implements Win32 user space only, so it launches and sees no printer |

### The fix

Brother's **Printer Setting Tool → Device Settings → Basic → Auto Power Off**, set to
`None`. Values are `None / 10 / 20 / 30 / 40 / 50 / 60` minutes.

The tool is **Windows/macOS and USB-only**. The choice is written to the printer's own
NVRAM, so it is a **one-time change** — it survives reboots, re-cabling, and swapping
the host machine entirely. You need Windows or macOS once, not permanently.

On a headless Linux box, the practical route is a throwaway Windows VM with the
printer passed through by USB vendor:product id (`04f9:20af`). That is written up in
[`ptouch-cube-print-bridge`](https://github.com/danielrosehill/ptouch-cube-print-bridge),
along with the hardware notes this page summarises.

A factory reset of the printer (hold power while inserting the cassette, or *Reset* in
the Setting Tool) reverts it to 60 minutes and you get to do it again.

### Don't write a keep-alive

It cannot work. On the P710BT the idle timer is reset by **printing**, not by USB
activity — a status-poll loop looks like it is doing something and is not. Measured
across three power-on windows with a 300 s `--info` poll running throughout: the
printer still powered off at ~60 minutes each time, including in a window with zero
print jobs.

## Consequences for this MCP

- `printer_capabilities` returns this list, so the agent does not offer to change a
  setting it cannot reach.
- `printer_status` failing usually means **the printer is off**, not that anything is
  broken. The honest response is "press the power button", not a retry loop.
- Copies are passed to `ptouch-print --copies N` as a single multi-page job, with
  `--precut` so the auto-cutter separates them into individual labels. (Printing N
  separate one-page jobs also works and was the original approach, but it re-runs the
  ~25 mm leader trim every time and wastes tape.)
- Tape length remaining is unknowable, so batch runs cannot warn you before you run
  out. Check the cassette window before a long run.
