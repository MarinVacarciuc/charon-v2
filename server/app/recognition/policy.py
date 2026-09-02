"""Access policy: may this person be here, now?

Deliberately pure. Nothing in this module touches the database, the clock, or the network -
callers pass the facts in and get a decision out. That is what makes the awkward cases
(midnight shifts, an override that narrows rather than widens, a grant expiring mid-scene)
testable without hardware, which matters because they are exactly the cases the previous
implementation got wrong.

Three defects carried over from that implementation are fixed here, and each is marked at
the code that fixes it:

  1. A time window could not cross midnight. The old check compared "HH:MM" strings
     lexically, so "22:00" <= "01:00" <= "06:00" was false and a night shift was refused all
     night. Its overstay sweep *did* handle midnight, so two halves of one system disagreed.
  2. A per-person zone list could widen access but never narrow it for an ADMIN, because the
     role's "all zones" value was short-circuited before the override was consulted. Found in
     an adversarial review of the old build; re-introducing additive-only overrides silently
     re-opens it.
  3. Authorisation was decided after the new location had already been written. Nothing here
     writes anything, so a caller cannot repeat that ordering by accident.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time


class Denial:
    """Reason codes. Strings rather than an enum because they go straight to the UI, the
    audit log and the voice line, and a stable short code is easier to match on there."""

    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"
    OUT_OF_HOURS = "OUT OF HOURS"
    ZONE_FORBIDDEN = "ZONE NOT ALLOWED"


@dataclass(frozen=True)
class ZoneGrant:
    """A just-in-time pass. Each zone carries its own expiry, so one lapsing leaves the
    others alone and nothing has to be manually reverted."""

    zone: str
    expires_at: datetime


@dataclass
class Person:
    name: str
    role: str
    status: str = "active"                    # active | suspended
    hours_from: time = time(0, 0)
    hours_to: time = time(23, 59)
    valid_until: date | None = None           # inclusive; None = no expiry
    access_until: datetime | None = None      # temporary out-of-hours extension
    max_hours: float | None = None
    # Empty means "inherit the role". A non-empty set REPLACES the role's zones entirely,
    # in both directions - see defect 2 above.
    zone_overrides: set[str] = field(default_factory=set)
    grants: list[ZoneGrant] = field(default_factory=list)


def within_window(start: time, end: time, now: time) -> bool:
    """Is `now` inside the daily window [start, end], inclusive at both ends?

    A window whose end is before its start wraps past midnight: 22:00-06:00 means the late
    evening *and* the small hours, not the empty set. Fixes defect 1.
    """
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def policy_ok(person: Person, now: datetime) -> tuple[bool, str]:
    """Is this person allowed on site at all right now?

    Order matters: suspension and expiry are absolute, and an out-of-hours extension must not
    be able to rescue either of them. Returns (allowed, reason); reason is "" when allowed.
    """
    if person.status == "suspended":
        return False, Denial.SUSPENDED

    # Inclusive: someone valid until the 30th is still valid all day on the 30th.
    if person.valid_until is not None and now.date() > person.valid_until:
        return False, Denial.EXPIRED

    if within_window(person.hours_from, person.hours_to, now.time()):
        return True, ""

    # Outside the window, but an admin may have extended them. This is the only thing
    # access_until does: it cannot revive a suspended or expired person.
    if person.access_until is not None and now < person.access_until:
        return True, ""

    return False, Denial.OUT_OF_HOURS


def permanent_zones(person: Person, role_zones: set[str]) -> set[str]:
    """Zones this person holds permanently, ignoring temporary grants.

    A non-empty override set replaces the role's zones outright. It is checked before any
    role handling, with no special case for a role that happens to hold everything - that
    special case was defect 2.
    """
    if person.zone_overrides:
        return set(person.zone_overrides)
    return set(role_zones)


def active_grants(person: Person, now: datetime) -> list[ZoneGrant]:
    """Grants that have not lapsed. Expiry is by comparison, never by a cleanup job, so a
    grant is dead the instant it is due regardless of whether anything swept it."""
    return [g for g in person.grants if g.expires_at > now]


def effective_zones(person: Person, role_zones: set[str], now: datetime) -> set[str]:
    """Everywhere this person may currently be: permanent zones plus live grants."""
    return permanent_zones(person, role_zones) | {g.zone for g in active_grants(person, now)}


def zone_allowed(person: Person, role_zones: set[str], zone: str, now: datetime) -> tuple[bool, str]:
    """May this person be in this specific zone, right now?

    Both halves are checked: being inside your permitted window does not put you everywhere,
    and holding a zone does not let you be there at four in the morning. The Cleaner exists in
    the demo to make the second half visible - all four zones, but only 18:00 to 20:00.
    """
    ok, reason = policy_ok(person, now)
    if not ok:
        return False, reason
    if zone not in effective_zones(person, role_zones, now):
        return False, Denial.ZONE_FORBIDDEN
    return True, ""


def overstay_deadline(entry: datetime, person: Person, grace_minutes: int = 5) -> datetime | None:
    """When this person stops being expected on site, or None if nothing caps them.

    Anchored to the entry timestamp rather than to today, so a shift that began yesterday
    evening is still measured from when it actually began. Where both a shift end and a
    maximum duration apply, whichever falls first wins: the tighter constraint is the real one.
    """
    from datetime import timedelta

    candidates: list[datetime] = []

    shift_end = datetime.combine(entry.date(), person.hours_to, tzinfo=entry.tzinfo)
    if shift_end <= entry:
        # The shift ends after midnight relative to when they arrived.
        shift_end += timedelta(days=1)
    candidates.append(shift_end)

    if person.max_hours is not None:
        candidates.append(entry + timedelta(hours=person.max_hours))

    if not candidates:
        return None
    return min(candidates) + timedelta(minutes=grace_minutes)
