"""ASGI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health
from app.api.routes import repositories
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.errors import register_exception_handlers
from app.core.config import Settings
from app.services.repository_analysis import RepositoryScanner
from app.services.inference import build_inference_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    configured_settings = settings or get_settings()
    application = FastAPI(
        title="DevRelay AI API",
        version="0.1.0",
        description="Backend foundation for engineering handoffs.",
        lifespan=lifespan,
    )
    register_exception_handlers(application)
    application.state.repository_scanner = RepositoryScanner(configured_settings)
    application.state.inference_service = build_inference_service(configured_settings)
    application.include_router(health.router)
    application.include_router(repositories.router)
    return application


app = create_app()
