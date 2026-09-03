#!/usr/bin/env python
"""Measure the mDNS stall the resolver exists to avoid.

    python tools/measure_dns.py gate-in.local

Reports AF_UNSPEC (the OS default) against AF_INET (what the brain uses). The gap is the
whole justification for app/nodes/resolver.py, and the number belongs in the report as a
measurement rather than a claim.
"""
from __future__ import annotations

import socket
import statistics
import sys
import time


def timed(host: str, family: int, runs: int) -> list[float]:
    out = []
    for _ in range(runs):
        t0 = time.perf_counter()
        try:
            socket.getaddrinfo(host, None, family=family, type=socket.SOCK_STREAM)
        except socket.gaierror:
            pass
        out.append(time.perf_counter() - t0)
    return out


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "gate-in.local"
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    print(f"resolving {host}, {runs} runs each\n")
    for label, fam in (("AF_UNSPEC (OS default)", socket.AF_UNSPEC), ("AF_INET (explicit)", socket.AF_INET)):
        ts = timed(host, fam, runs)
        print(f"{label:24s} median {statistics.median(ts)*1000:8.1f} ms   "
              f"min {min(ts)*1000:7.1f}   max {max(ts)*1000:7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
