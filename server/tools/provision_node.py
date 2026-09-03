#!/usr/bin/env python
"""Flash the plugged-in board with the identity its MAC says it is, then verify it.

    python tools/provision_node.py

The six boards are visually identical and their identity exists only in flash, so the MAC is
the only thing that says which is which. Reading it first and looking the name up in the
registry removes the one mistake that is both easy to make and annoying to find later: a
board answering to the wrong name, which looks like a camera pointing at the wrong place.

Add --dry-run to read and identify without writing anything.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
REPO = SERVER_DIR.parent
FIRMWARE = REPO / "firmware"
ESPTOOL = Path.home() / "Library/Arduino15/packages/esp32/tools/esptool_py/5.2.0/esptool"

# Mirrors the nodes table in 002_seed.sql. Kept here too so provisioning works before the
# brain has ever run; the two are checked against each other below.
MAC_TO_NODE = {
    "28:84:85:9F:C6:20": "gate-in",
    "28:84:85:65:6E:24": "gate-out",
    "28:84:85:65:64:5C": "zone-reception",
    "28:84:85:9F:C0:EC": "zone-warehouse",
    "28:84:85:65:6E:F0": "zone-workshop",
    "28:84:85:9F:C7:50": "zone-server",
}


def find_port() -> str:
    ports = sorted(Path("/dev").glob("cu.usbmodem*"))
    if not ports:
        sys.exit("no board found - plug one in over USB-C")
    if len(ports) > 1:
        sys.exit(f"more than one board plugged in: {[p.name for p in ports]}\n"
                 f"unplug all but one, or pass --port")
    return str(ports[0])


def read_mac(port: str) -> str:
    out = subprocess.run([str(ESPTOOL), "--port", port, "read-mac"],
                         capture_output=True, text=True, timeout=90)
    m = re.search(r"^MAC:\s+([0-9a-fA-F:]{17})", out.stdout, re.M)
    if not m:
        sys.exit(f"could not read a MAC from {port}\n{out.stdout}\n{out.stderr}")
    return m.group(1).upper()


def ipv4(host: str) -> str | None:
    try:
        return socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)[0][4][0]
    except socket.gaierror:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wait", type=float, default=60, help="seconds to wait for the node to appear")
    args = ap.parse_args()

    port = args.port or find_port()
    print(f"port : {port}")
    mac = read_mac(port)
    node = MAC_TO_NODE.get(mac)
    print(f"mac  : {mac}")
    if node is None:
        print("\nThis MAC is not in the registry. Either it is a seventh board, or the")
        print("registry is wrong. Refusing to guess an identity - add it to MAC_TO_NODE")
        print("and to 002_seed.sql (they must agree) before flashing.")
        return 2
    print(f"node : {node}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    print(f"\nflashing {node}...")
    r = subprocess.run(["./flash_node.sh", node, port], cwd=FIRMWARE,
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        print(r.stdout[-3000:]); print(r.stderr[-3000:])
        sys.exit(f"flash failed for {node}")
    verified = r.stdout.count("Hash of data verified.")
    print(f"flashed, {verified} image sections hash-verified")

    print(f"\nwaiting for {node}.local ...")
    host = f"{node}.local"
    ip = None
    t0 = time.monotonic()
    while time.monotonic() - t0 < args.wait:
        ip = ipv4(host)
        if ip:
            break
        time.sleep(1.5)
    if not ip:
        print(f"  {host} did not resolve within {args.wait:.0f}s.")
        print("  The flash itself succeeded; this is a network or mDNS problem.")
        return 1
    print(f"  {host} -> {ip}")

    with urllib.request.urlopen(f"http://{ip}/status", timeout=8) as resp:
        s = json.loads(resp.read())

    checks = [
        ("node id matches the MAC", s["node"] == node),
        ("MAC as expected", s["mac"].upper() == mac),
        ("camera pin map found", s.get("cam_map") not in (None, "", "none")),
        ("pass sensor role correct", s["has_pass"] == node.startswith("gate")),
        ("joined a network", bool(s.get("ssid"))),
    ]
    print()
    for label, ok in checks:
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    print(f"\n  ssid {s['ssid']}  rssi {s['rssi']} dBm  fw {s['fw']}  heap {s['heap']}  die {s['die_c']} C")
    print(f"  near {s['near_cm']} cm (wake<{s['wake_cm']})   pass {s['pass_cm']} cm (count<{s['pass_thresh_cm']})")

    if not all(ok for _, ok in checks):
        return 1
    print(f"\n{node} provisioned and verified. Label this board '{node}' physically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
