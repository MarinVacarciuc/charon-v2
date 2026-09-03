"""FastAPI application factory.

Startup order matters: the database has to be ready before the registry reads from it, and
the registry has to be running before any route can serve a frame or a health snapshot.
Shutdown reverses it - stop pollers before pulling the database out from under them.
"""
from __future__ import annotations

import logging

import aiohttp
from fastapi import FastAPI

from .api import routes_nodes
from .config import get_settings
from .db.database import Database
from .nodes.events_sink import BrainEvents
from .nodes.registry import NodeRegistry
from .push.hub import SseHub

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Charon brain")
    app.include_router(routes_nodes.router)

    @app.on_event("startup")
    async def startup() -> None:
        settings = get_settings()

        db = Database(settings.db_path, settings.migrations_dir)
        await db.connect()

        session = aiohttp.ClientSession()
        hub = SseHub()
        events = BrainEvents(db, hub)
        registry = NodeRegistry(db, session, events)
        await registry.load()
        await registry.start()

        app.state.settings = settings
        app.state.db = db
        app.state.session = session
        app.state.hub = hub
        app.state.registry = registry
        log.info("brain up: %d node(s) polling, db at %s", len(registry.all()), settings.db_path)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await app.state.registry.stop()
        await app.state.session.close()
        await app.state.db.close()
        log.info("brain down")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


app = create_app()
