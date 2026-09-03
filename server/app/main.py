"""FastAPI application factory.

Startup order matters: the database has to be ready before the registry reads from it, and
the registry has to be running before any route can serve a frame or a health snapshot.
Shutdown reverses it - stop pollers before pulling the database out from under them.
"""
from __future__ import annotations

import logging

import aiohttp
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import routes_admin, routes_nodes, routes_people
from .config import SERVER_DIR, get_settings
from .db.database import Database
from .db.repositories import embeddings
from .recognition.engine import RecognitionEngine
from .nodes.events_sink import BrainEvents
from .nodes.registry import NodeRegistry
from .push.hub import SseHub

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Charon brain")
    app.include_router(routes_nodes.router)
    app.include_router(routes_people.router)
    app.include_router(routes_admin.router)

    @app.on_event("startup")
    async def startup() -> None:
        settings = get_settings()

        db = Database(settings.db_path, settings.migrations_dir)
        await db.connect()

        engine = RecognitionEngine(
            str(settings.models_dir / "face_detection_yunet_2023mar.onnx"),
            str(settings.models_dir / "face_recognition_sface_2021dec.onnx"),
        )
        roster = await embeddings.load_all(db)
        engine.load_samples(roster)
        log.info("recognition engine loaded: %d enrolled people, %d total samples",
                 engine.enrolled_people, sum(len(v) for v in roster.values()))

        session = aiohttp.ClientSession()
        hub = SseHub()
        events = BrainEvents(db, hub, engine)
        registry = NodeRegistry(db, session, events)
        await registry.load()
        await registry.start()

        app.state.settings = settings
        app.state.db = db
        app.state.engine = engine
        app.state.session = session
        app.state.hub = hub
        app.state.registry = registry
        app.state.events = events
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

    @app.get("/")
    async def root():
        # Typing a bare host during filming should land on the product, not a 404.
        return RedirectResponse("/dashboard/")

    # Plain static files, no build step: the dashboard is hand-written HTML+JS on purpose
    # (docs/BUILD_PLAN.md) - one fewer moving part to break the day before filming.
    app.mount("/", StaticFiles(directory=str(SERVER_DIR / "static"), html=True), name="static")

    return app


app = create_app()
