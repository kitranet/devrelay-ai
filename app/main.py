"""ASGI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.errors import register_exception_handlers


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="DevRelay AI API",
        version="0.1.0",
        description="Backend foundation for engineering handoffs.",
        lifespan=lifespan,
    )
    register_exception_handlers(application)
    application.include_router(health.router)
    return application


app = create_app()
