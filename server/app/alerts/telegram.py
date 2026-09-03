"""Telegram notifications - the phone half of the demo's beats.

Two things reach a phone, both from DEMO_ARCHITECTURE's beat sheet: the token issued when
someone is granted entry (beat 1), and a wrong-zone alert to the person who walked into a
zone their role forbids (beat 5). Dispatcher-wide alerting also routes here.

Fire-and-forget on purpose. A gate decision must not wait on, or be undone by, a network
call to a third party: if Telegram is slow or down, the light still goes green, the voice
still plays, the audit row is still written, and only the phone notification is missing. The
previous build made the same call and it was right.
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT_S = 6.0


class Telegram:
    def __init__(self, token: str, session: aiohttp.ClientSession, enabled: bool = True) -> None:
        self._token = token
        self._session = session
        self._enabled = enabled and bool(token)
        if not self._enabled:
            log.info("telegram disabled (no token configured)")

    def send(self, chat_id: str, text: str) -> None:
        """Queue a message. Returns immediately; never raises into the caller."""
        if not self._enabled or not chat_id:
            return
        asyncio.create_task(self._send(chat_id, text))

    async def _send(self, chat_id: str, text: str) -> None:
        try:
            async with self._session.post(
                API.format(token=self._token),
                data={"chat_id": chat_id, "text": text},
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_S),
            ) as r:
                if r.status != 200:
                    log.warning("telegram sendMessage returned %s: %s", r.status, (await r.text())[:200])
        except Exception as exc:  # noqa: BLE001
            # Deliberately swallowed: a notification failing is not a reason for a gate
            # decision, an audit write, or the dashboard to be affected in any way.
            log.warning("telegram send failed: %s", exc)

    # ------------------------------------------------------------------ the messages

    def entry_token(self, chat_id: str, name: str, token: str) -> None:
        self.send(chat_id, f"CHARON\n\nWelcome, {name}.\nYour session token: CH-{token}\n\n"
                           "This token is a receipt. Access is enforced by the system, not by "
                           "the token, and it is annulled the moment you leave.")

    def wrong_zone(self, chat_id: str, name: str, zone: str, reason: str) -> None:
        self.send(chat_id, f"CHARON ALERT\n\n{name}, you are in {zone} and your access does not "
                           f"cover it ({reason}).\nPlease leave the area.")

    def dispatcher_alert(self, chat_id: str, text: str) -> None:
        self.send(chat_id, f"CHARON ALERT\n\n{text}")
