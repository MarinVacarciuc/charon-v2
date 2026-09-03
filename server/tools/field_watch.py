#!/usr/bin/env python
"""Continuous field-recon logger for all six nodes.

Run this once at the start of a walk-the-yard session (gate -> passage -> shed -> swivel ->
grill) and let it run in the background for the whole walk. It polls every node every second,
prints a state-change log line whenever something meaningfully changes (a node drops offline
or comes back, RSSI crosses a weak-signal band, a sensor trips), and writes every sample to a
CSV so the whole session can be reconstructed afterwards - which station had which coverage,
whether any node ever dropped, what its RSSI floor was.

    python tools/field_watch.py --out ../docs/evidence/field-recon-2026-09-03.csv

Ctrl-C to stop; the CSV is flushed continuously, so killing it loses nothing.
"""
from __future__ import annotations

import argparse
import csv
import json
import socket
import sys
import time
import urllib.request
from pathlib import Path

NODES = ["gate-in", "gate-out", "zone-reception", "zone-warehouse", "zone-workshop", "zone-server"]

WEAK_RSSI = -75  # below this, expect real trouble; matches typical WiFi usability guidance


def ipv4(host: str, cache: dict[str, str]) -> str | None:
    if host in cache:
        return cache[host]
    try:
        ip = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)[0][4][0]
        cache[host] = ip
        return ip
    except socket.gaierror:
        return None


def poll(ip: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{ip}/status", timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="CSV path to write samples to")
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not out_path.exists()
    f = open(out_path, "a", newline="")
    w = csv.writer(f)
    if new_file:
        w.writerow(["t", "node", "online", "ssid", "rssi", "near_cm", "near",
                    "pass_cm", "pass_blocked", "cam_on", "die_c", "heap"])

    dns_cache: dict[str, str] = {}
    last_online: dict[str, bool | None] = {n: None for n in NODES}
    last_rssi_band: dict[str, str] = {n: "" for n in NODES}
    t0 = time.time()

    print(f"watching {len(NODES)} nodes every {args.interval}s -> {out_path}")
    print("state changes print below; every sample is in the CSV regardless. Ctrl-C to stop.\n")

    try:
        while True:
            now = time.time()
            for node in NODES:
                ip = ipv4(f"{node}.local", dns_cache)
                status = poll(ip) if ip else None
                online = status is not None
                ts = time.strftime("%H:%M:%S", time.localtime(now))

                if online:
                    w.writerow([f"{now:.1f}", node, 1, status.get("ssid", ""), status.get("rssi", ""),
                               status.get("near_cm", ""), int(status.get("near", False)),
                               status.get("pass_cm", ""), int(status.get("pass_blocked", False)),
                               int(status.get("cam_on", False)), status.get("die_c", ""), status.get("heap", "")])
                else:
                    w.writerow([f"{now:.1f}", node, 0, "", "", "", "", "", "", "", "", ""])
                    dns_cache.pop(f"{node}.local", None)  # a dead node may come back with a new IP

                if online != last_online[node]:
                    label = "ONLINE" if online else "OFFLINE"
                    extra = f"  rssi={status['rssi']}dBm ssid={status['ssid']}" if online else ""
                    print(f"[{ts}] {node:16s} {label}{extra}")
                    last_online[node] = online

                if online:
                    rssi = status.get("rssi", 0)
                    band = "weak" if rssi < WEAK_RSSI else "ok"
                    if band != last_rssi_band[node] and last_rssi_band[node] != "":
                        print(f"[{ts}] {node:16s} signal -> {band} ({rssi} dBm)")
                    last_rssi_band[node] = band

            f.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()
        print(f"\nstopped after {time.time()-t0:.0f}s. samples in {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
