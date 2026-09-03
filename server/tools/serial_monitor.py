#!/usr/bin/env python
"""Read a board's serial output, optionally resetting it first to catch the boot log.

    python tools/serial_monitor.py --port /dev/cu.usbmodemXXXX --seconds 20 --reset

These boards enumerate as native USB CDC, so the baud rate is ignored by the hardware; it is
still passed because pyserial wants one. --reset toggles DTR/RTS the way the upload tool
does, which is the only way to see setup() output on a board that is already running.
"""
from __future__ import annotations

import argparse
import sys
import time

import serial


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--reset", action="store_true", help="pulse DTR/RTS to reboot the board first")
    ap.add_argument("--until", default=None, help="stop early once this substring appears")
    args = ap.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.2) as ser:
        if args.reset:
            # Same sequence the uploader uses: EN low with IO0 high is a plain reset into the
            # application, not into the bootloader.
            ser.dtr = False
            ser.rts = True
            time.sleep(0.1)
            ser.rts = False
            time.sleep(0.05)
            ser.reset_input_buffer()

        deadline = time.monotonic() + args.seconds
        buf = b""
        while time.monotonic() < deadline:
            chunk = ser.read(4096)
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", "replace").rstrip("\r")
                print(text, flush=True)
                if args.until and args.until in text:
                    return 0
        if buf:
            print(buf.decode("utf-8", "replace"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
