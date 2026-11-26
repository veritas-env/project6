"""Application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis import Redis

from .api import admin, auth, bookings, flights
from .core import errors
from .core.config import Settings, get_settings
from .core.db import make_engine, make_sessionmaker
from .core.logging import configure_logging
from .core.sessions import SessionStore


def create_app(settings: Settings | None = None, redis_client: Redis | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.env != "test":
        configure_logging()

    engine = make_engine(settings.database_url)
    redis_client = redis_client or Redis.from_url(settings.redis_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        engine.dispose()

    show_docs = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        docs_url="/api/docs" if show_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if show_docs else None,
        swagger_ui_oauth2_redirect_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.redis = redis_client
    app.state.session_store = SessionStore(
        redis_client, settings.session_idle_minutes * 60, settings.session_absolute_hours * 3600
    )

    errors.install(app)

    @app.get("/api/health", include_in_schema=False)
    def health() -> dict:
        return {"status": "ok"}

    for module in (auth, flights, bookings, admin):
        app.include_router(module.router)
    return app


def app_factory() -> FastAPI:  # for `uvicorn --factory app.main:app_factory`
    return create_app()
