"""Policy tests.

Runs standalone (`python tests/test_policy.py`) as well as under pytest, so the check is
always one command away with no extra dependency.

These are not decorative. Two of the demo's seven beats are decided entirely by this module
- the Guard refused at the server room while IT is admitted, and the Cleaner admitted only
inside their window - and three of the cases below are regressions of defects the previous
implementation actually shipped.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.recognition.policy import (  # noqa: E402
    Denial,
    Person,
    ZoneGrant,
    effective_zones,
    overstay_deadline,
    permanent_zones,
    policy_ok,
    within_window,
    zone_allowed,
)

# The seeded matrix, mirrored here so a test failure points at the logic rather than at a
# database fixture.
ROLE_ZONES = {
    "ADMIN":   {"Reception", "Warehouse", "Workshop", "Server room"},
    "GUARD":   {"Reception", "Warehouse", "Workshop"},
    "WORKER":  {"Reception", "Warehouse", "Workshop"},
    "IT":      {"Reception", "Server room"},
    "VISITOR": {"Reception"},
    "CLEANER": {"Reception", "Warehouse", "Workshop", "Server room"},
}

def at(h: int, m: int = 0, d: int = 15) -> datetime:
    return datetime(2026, 9, d, h, m)


# ---------------------------------------------------------------- time windows

def test_window_normal_day():
    assert within_window(time(9, 0), time(17, 0), time(12, 0))
    assert not within_window(time(9, 0), time(17, 0), time(8, 59))
    assert not within_window(time(9, 0), time(17, 0), time(17, 1))

def test_window_is_inclusive_at_both_ends():
    assert within_window(time(9, 0), time(17, 0), time(9, 0))
    assert within_window(time(9, 0), time(17, 0), time(17, 0))

def test_window_crosses_midnight():
    # REGRESSION: the old check compared "HH:MM" lexically, so a night shift was refused
    # all night while the overstay sweep believed the person was still on shift.
    assert within_window(time(22, 0), time(6, 0), time(23, 30))
    assert within_window(time(22, 0), time(6, 0), time(2, 0))
    assert within_window(time(22, 0), time(6, 0), time(22, 0))
    assert not within_window(time(22, 0), time(6, 0), time(12, 0))
    assert not within_window(time(22, 0), time(6, 0), time(21, 59))


# ---------------------------------------------------------------- policy_ok

def test_suspended_is_refused_even_inside_hours():
    p = Person(name="X", role="ADMIN", status="suspended")
    ok, why = policy_ok(p, at(12))
    assert not ok and why == Denial.SUSPENDED

def test_valid_until_is_inclusive_on_the_day_itself():
    p = Person(name="X", role="GUARD", valid_until=date(2026, 9, 15))
    assert policy_ok(p, at(12, d=15))[0]
    assert not policy_ok(p, at(12, d=16))[0]
    assert policy_ok(p, at(12, d=16))[1] == Denial.EXPIRED

def test_out_of_hours_is_refused():
    p = Person(name="X", role="CLEANER", hours_from=time(18, 0), hours_to=time(20, 0))
    ok, why = policy_ok(p, at(14))
    assert not ok and why == Denial.OUT_OF_HOURS

def test_access_until_rescues_out_of_hours():
    p = Person(name="X", role="CLEANER", hours_from=time(18, 0), hours_to=time(20, 0),
               access_until=at(15))
    assert policy_ok(p, at(14))[0]          # extension is live
    assert not policy_ok(p, at(15, 1))[0]   # and lapses by itself

def test_access_until_cannot_rescue_suspension_or_expiry():
    # An extension is an hours override, nothing more. If it could revive a suspended badge
    # it would be a way to quietly undo a revocation.
    susp = Person(name="X", role="ADMIN", status="suspended", access_until=at(23))
    assert policy_ok(susp, at(14))[1] == Denial.SUSPENDED
    exp = Person(name="X", role="ADMIN", valid_until=date(2026, 9, 1), access_until=at(23))
    assert policy_ok(exp, at(14))[1] == Denial.EXPIRED


# ---------------------------------------------------------------- zones

def test_role_zones_apply_when_there_is_no_override():
    p = Person(name="Marin", role="GUARD")
    assert permanent_zones(p, ROLE_ZONES["GUARD"]) == ROLE_ZONES["GUARD"]

def test_override_can_narrow_an_admin():
    # REGRESSION: the old build short-circuited a role holding "all zones" before consulting
    # the per-person list, so an admin could not be restricted at all. This was an
    # authorisation gap found in review, and it comes straight back if overrides are
    # treated as additive.
    p = Person(name="Restricted admin", role="ADMIN", zone_overrides={"Reception"})
    assert permanent_zones(p, ROLE_ZONES["ADMIN"]) == {"Reception"}
    assert not zone_allowed(p, ROLE_ZONES["ADMIN"], "Server room", at(12))[0]

def test_override_can_also_widen():
    p = Person(name="Trusted visitor", role="VISITOR", zone_overrides={"Reception", "Workshop"})
    assert zone_allowed(p, ROLE_ZONES["VISITOR"], "Workshop", at(12))[0]

def test_beat_five_guard_denied_it_allowed_at_the_server_room():
    # The money shot: same door, two roles, two outcomes.
    guard = Person(name="Marin", role="GUARD")
    it = Person(name="Natalia", role="IT")
    ok_g, why_g = zone_allowed(guard, ROLE_ZONES["GUARD"], "Server room", at(12))
    ok_i, _ = zone_allowed(it, ROLE_ZONES["IT"], "Server room", at(12))
    assert not ok_g and why_g == Denial.ZONE_FORBIDDEN
    assert ok_i

def test_cleaner_is_bounded_by_time_not_by_place():
    cleaner = Person(name="Cleaner", role="CLEANER", hours_from=time(18, 0), hours_to=time(20, 0))
    assert zone_allowed(cleaner, ROLE_ZONES["CLEANER"], "Server room", at(18, 30))[0]
    ok, why = zone_allowed(cleaner, ROLE_ZONES["CLEANER"], "Server room", at(14))
    assert not ok and why == Denial.OUT_OF_HOURS   # refused on time, not on place


# ---------------------------------------------------------------- JIT grants

def test_grant_adds_a_zone_and_lapses_on_its_own():
    it = Person(name="Natalia", role="IT",
                grants=[ZoneGrant(zone="Workshop", expires_at=at(12, 15))])
    assert zone_allowed(it, ROLE_ZONES["IT"], "Workshop", at(12, 10))[0]
    ok, why = zone_allowed(it, ROLE_ZONES["IT"], "Workshop", at(12, 16))
    assert not ok and why == Denial.ZONE_FORBIDDEN   # no manual revert needed

def test_each_grant_expires_independently():
    p = Person(name="X", role="VISITOR", grants=[
        ZoneGrant(zone="Workshop", expires_at=at(12, 10)),
        ZoneGrant(zone="Warehouse", expires_at=at(13, 0)),
    ])
    assert effective_zones(p, ROLE_ZONES["VISITOR"], at(12, 30)) == {"Reception", "Warehouse"}

def test_a_grant_cannot_bypass_the_hours_check():
    # A pass says where, never when. Otherwise a five-minute grant would become a way around
    # a shift window.
    p = Person(name="X", role="VISITOR", hours_from=time(9, 0), hours_to=time(17, 0),
               grants=[ZoneGrant(zone="Server room", expires_at=at(23))])
    ok, why = zone_allowed(p, ROLE_ZONES["VISITOR"], "Server room", at(21))
    assert not ok and why == Denial.OUT_OF_HOURS


# ---------------------------------------------------------------- overstay

def test_overstay_uses_shift_end_anchored_to_entry():
    p = Person(name="X", role="WORKER", hours_from=time(9, 0), hours_to=time(17, 0))
    assert overstay_deadline(at(9, 30), p, grace_minutes=5) == at(17, 5)

def test_overstay_survives_a_shift_that_ends_after_midnight():
    # REGRESSION: anchoring to "today" instead of the entry date made the sweep stop working
    # the moment the clock passed midnight.
    p = Person(name="Night", role="GUARD", hours_from=time(22, 0), hours_to=time(6, 0))
    entry = at(22, 30, d=15)
    assert overstay_deadline(entry, p, grace_minutes=5) == datetime(2026, 9, 16, 6, 5)

def test_max_hours_wins_when_it_is_the_tighter_limit():
    p = Person(name="X", role="VISITOR", hours_from=time(9, 0), hours_to=time(17, 0), max_hours=2)
    assert overstay_deadline(at(10, 0), p, grace_minutes=5) == at(12, 5)


def _run() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as e:
            failed.append(name)
            print(f"  FAIL {name}  {e}")
        except Exception as e:                       # noqa: BLE001
            failed.append(name)
            print(f"  ERR  {name}  {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
