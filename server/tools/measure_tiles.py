#!/usr/bin/env python
"""Measure how fast the dashboard's camera tiles actually update, and why.

    python tools/measure_tiles.py --seconds 30

Answers the question Marin asked on 2026-09-08 ("the tiles are badly choppy, maybe one frame
every few seconds - how many?") with a number rather than a guess. It could not be answered
then because the boards were off.

It separates the two things that can look identical from the outside:

  * how often the BRAIN gets a new frame from a node (the poller's own rate), and
  * how often a browser asking /frame.jpg is handed something it has not already seen.

If those two differ, the bottleneck is the serving path. If they agree and both are slow, the
bottleneck is upstream: the node, the camera wake cycle, or WiFi airtime - which was separately
measured on 2026-09-03 to spike to 2.1s when several boards are clustered with cameras awake.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request


def get(url: str, timeout: float = 6.0):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, dict(r.headers), r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1:8770")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--interval", type=float, default=0.1,
                    help="how often to ask - deliberately faster than any plausible frame rate")
    args = ap.parse_args()
    base = f"http://{args.host}"

    status, _, body = get(f"{base}/nodes")
    nodes = [n for n in json.loads(body)["nodes"] if n["online"]]
    if not nodes:
        print("No nodes are online. Power the boards up first - this measures live frames.")
        return 1
    print(f"watching {len(nodes)} online node(s) for {args.seconds:.0f}s: "
          f"{', '.join(n['id'] for n in nodes)}\n")

    # Per node: when we last saw a genuinely NEW frame, and the gaps between new frames.
    last_hash = {n["id"]: None for n in nodes}
    last_at = {n["id"]: None for n in nodes}
    gaps = {n["id"]: [] for n in nodes}
    served_ages = {n["id"]: [] for n in nodes}
    misses = {n["id"]: 0 for n in nodes}

    t_end = time.monotonic() + args.seconds
    while time.monotonic() < t_end:
        for n in nodes:
            nid = n["id"]
            try:
                code, headers, jpeg = get(f"{base}/frame.jpg?node={nid}")
            except Exception:
                misses[nid] += 1
                continue
            if code != 200:
                misses[nid] += 1
                continue
            # X-Frame-Age-Ms is how stale the brain's own cached frame was when it answered -
            # the difference between "the browser asked often" and "there was anything new".
            age = headers.get("X-Frame-Age-Ms")
            if age is not None:
                served_ages[nid].append(int(age))
            h = hashlib.md5(jpeg).hexdigest()
            now = time.monotonic()
            if h != last_hash[nid]:
                if last_at[nid] is not None:
                    gaps[nid].append(now - last_at[nid])
                last_hash[nid] = h
                last_at[nid] = now
        time.sleep(args.interval)

    print(f"{'node':16s} {'new frames':>10s} {'median gap':>12s} {'worst gap':>11s} {'effective fps':>14s}")
    for n in nodes:
        nid = n["id"]
        g = sorted(gaps[nid])
        if not g:
            print(f"{nid:16s} {'0':>10s} {'-':>12s} {'-':>11s} {'0':>14s}   "
                  f"(no new frame in {args.seconds:.0f}s)")
            continue
        med = g[len(g) // 2]
        print(f"{nid:16s} {len(g):>10d} {med:>11.2f}s {max(g):>10.2f}s {1/med:>13.2f}")

    print()
    for n in nodes:
        nid = n["id"]
        a = served_ages[nid]
        if a:
            a_sorted = sorted(a)
            print(f"  {nid:16s} frame age when served: median {a_sorted[len(a)//2]:5d} ms, "
                  f"worst {max(a):6d} ms" + (f", {misses[nid]} failed request(s)" if misses[nid] else ""))

    print("\nReading this: a large 'median gap' with a small 'frame age when served' means the")
    print("brain is handing over promptly but has nothing new - the bottleneck is the node or")
    print("the network. A large frame age means the serving path itself is lagging.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
