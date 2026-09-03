#!/usr/bin/env python
"""Bench soak for the node camera wake/sleep cycle.

The camera-off-by-default design rests on esp_camera_init / esp_camera_deinit being safe to
repeat indefinitely. That is not obvious: a failed or leaky deinit shows up as a slow heap
decline and then a board that stops serving frames hours into a shoot. This exercises the
cycle hard and reports the heap trend, so the decision to ship it is made on a measurement.

    python tools/camera_soak.py --ip 192.168.0.30 --fast 100 --full 10

--fast cycles wake and sleep without pulling a frame (about 2 s each); --full also grabs a
frame, which holds the camera up for the full idle timeout (about 20 s each).
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request


def get_json(ip: str, path: str, timeout: float = 15) -> dict:
    with urllib.request.urlopen(f"http://{ip}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def get_bytes(ip: str, path: str, timeout: float = 15) -> tuple[int, bytes]:
    with urllib.request.urlopen(f"http://{ip}{path}", timeout=timeout) as r:
        return r.status, r.read()


def wait_asleep(ip: str, limit: float) -> dict | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        s = get_json(ip, "/status")
        if not s["cam_on"]:
            return s
        time.sleep(0.3)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--fast", type=int, default=100)
    ap.add_argument("--full", type=int, default=10)
    args = ap.parse_args()

    start = get_json(args.ip, "/status")
    print(f"board {start['node']} fw {start['fw']}  uptime {start['uptime_s']}s  "
          f"heap {start['heap']}  die {start['die_c']} C\n")

    heap_asleep: list[int] = []
    temps: list[float] = []
    failures: list[tuple[str, int, str]] = []

    print(f"phase 1: {args.fast} fast cycles (wake, sleep, no frame)")
    for i in range(1, args.fast + 1):
        try:
            if not get_json(args.ip, "/wake?sec=1").get("cam_on"):
                failures.append(("fast", i, "wake returned cam_on=false"))
                continue
            s = wait_asleep(args.ip, 15)
            if s is None:
                failures.append(("fast", i, "did not sleep within 15 s"))
                continue
            heap_asleep.append(s["heap"])
            temps.append(s["die_c"])
        except Exception as e:  # noqa: BLE001
            failures.append(("fast", i, f"{type(e).__name__}: {e}"))
        if i % 20 == 0:
            print(f"  {i:3d}/{args.fast}  heap={heap_asleep[-1] if heap_asleep else '?'}"
                  f"  die={temps[-1] if temps else '?'} C  failures={len(failures)}")

    print(f"\nphase 2: {args.full} full cycles (wake, grab a frame, sleep)")
    frame_bytes: list[int] = []
    frame_ms: list[float] = []
    for i in range(1, args.full + 1):
        try:
            t0 = time.monotonic()
            code, body = get_bytes(args.ip, "/shot.jpg")
            frame_ms.append((time.monotonic() - t0) * 1000)
            if code != 200 or body[:2] != b"\xff\xd8" or body[-2:] != b"\xff\xd9":
                failures.append(("full", i, f"bad frame http={code} len={len(body)}"))
                continue
            frame_bytes.append(len(body))
            s = wait_asleep(args.ip, 35)
            if s is None:
                failures.append(("full", i, "did not sleep within 35 s"))
                continue
            heap_asleep.append(s["heap"])
            temps.append(s["die_c"])
            print(f"  {i:2d}/{args.full}  {len(body):6d} B in {frame_ms[-1]:5.0f} ms"
                  f"  heap={s['heap']}  die={s['die_c']} C")
        except Exception as e:  # noqa: BLE001
            failures.append(("full", i, f"{type(e).__name__}: {e}"))

    end = get_json(args.ip, "/status")
    print("\n=== result ===")
    print(f"cycles attempted : {args.fast + args.full}")
    print(f"failures         : {len(failures)}")
    for phase, i, why in failures[:10]:
        print(f"   {phase} cycle {i}: {why}")

    rebooted = end["uptime_s"] < start["uptime_s"]
    print(f"board rebooted   : {'YES - the cycle crashed it' if rebooted else 'no'}"
          f"  (uptime {start['uptime_s']}s -> {end['uptime_s']}s)")
    print(f"camera map       : {end['cam_map']}")

    if heap_asleep:
        drift = heap_asleep[-1] - heap_asleep[0]
        print(f"\nheap asleep      : first {heap_asleep[0]} B, last {heap_asleep[-1]} B, "
              f"min {min(heap_asleep)}, max {max(heap_asleep)}")
        print(f"heap drift       : {drift:+d} B over {len(heap_asleep)} sleeps "
              f"({drift / max(1, len(heap_asleep)):+.1f} B/cycle)")
        print("                   a steady decline here is a leak in init/deinit;")
        print("                   noise of a few hundred bytes either way is normal.")
    if temps:
        print(f"die temperature  : {min(temps):.1f} .. {max(temps):.1f} C "
              f"(start {temps[0]:.1f}, end {temps[-1]:.1f})")
    if frame_bytes:
        print(f"frame size       : median {int(statistics.median(frame_bytes))} B "
              f"({min(frame_bytes)} .. {max(frame_bytes)})")
    if frame_ms:
        print(f"wake + frame     : median {statistics.median(frame_ms):.0f} ms "
              f"({min(frame_ms):.0f} .. {max(frame_ms):.0f})")

    return 1 if (failures or rebooted) else 0


if __name__ == "__main__":
    raise SystemExit(main())
