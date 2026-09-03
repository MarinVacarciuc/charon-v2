"""Shared-secret admin auth for mutating routes.

Threat model A7 sat at "partly implemented" for the whole life of the previous build: it had
an audit trail but no authentication at all, and every destructive action - delete a person,
revoke a token, wipe the database - was an unauthenticated GET that any device on the network
could fire, including by being linked to. This closes the honest minimum.

Deliberately narrow, and the shape is the reasoning:

* Only MUTATING routes are guarded. Reads - the dashboard, the SSE stream, camera frames, the
  gate terminal - stay open on the LAN, because the gate terminal is a phone propped up
  outdoors that nobody is going to log into mid-take, and a login prompt there would be a
  fail-secure mechanism that fails the shoot instead.
* A single shared secret, not accounts. There is one operator. Per-user identity would be
  ceremony without a second user to distinguish.
* The token travels in a header, never a query string, so it does not end up in server logs or
  browser history.

What this is NOT, and the report says so: this is a shared secret over plain HTTP on a private
network. It stops an accident and a casual passer-by on the same LAN. It does not stop anyone
who can see the traffic. TLS and per-user credentials remain designed-not-built.
"""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

HEADER = "X-Charon-Admin"


async def require_admin(request: Request) -> None:
    """FastAPI dependency. Raises 401 unless the request carries the admin token.

    An empty configured token means auth is switched off, which is what bench and CI runs
    use. That has to be a deliberate, visible state rather than an accident, so startup logs
    a warning when it is empty - a system that is silently unprotected is worse than one that
    is openly unprotected.
    """
    expected = request.app.state.settings.admin_token
    if not expected:
        return
    supplied = request.headers.get(HEADER, "")
    # Constant-time compare: the timing signal is tiny over a network, but there is no reason
    # to hand one over for free.
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail=f"missing or wrong {HEADER} header")
