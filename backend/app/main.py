import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router
from app.core.config import Settings
from app.core.database import Database
from app.core.exceptions import register_exception_handlers
from app.middleware.correlation_id import CorrelationMiddleware


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database = database if database is not None else Database(settings)
        try:
            yield
        finally:
            if database is None:
                app.state.database.close()

    logger = logging.getLogger("greencity")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(handler)
    app = FastAPI(title="GreenCity API", version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(router)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=False, allow_methods=["GET", "POST", "PATCH"],
                       allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
                       expose_headers=["X-Correlation-ID"])
    return app
