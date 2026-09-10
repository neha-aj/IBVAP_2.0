from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from ibvap_common.errors import install_error_handlers
from ibvap_common.logging import configure_logging, get_logger, install_correlation_id_middleware
from ibvap_common.metrics import install_metrics

from app.api import cameras as camera_routes
from app.api import health as health_routes
from app.api import internal as internal_routes
from app.api import sectors as sector_routes
from app.api import settings as settings_routes
from app.api import zones as zone_routes
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.repositories.setting_repo import SettingRepository
from app.services.settings_service import SettingsService

settings = get_settings()
configure_logging(settings.service_name)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed default Settings-page rows on first run so the page never renders
    # empty (Frontend Analysis Report §3.7).
    session_factory = get_session_factory()
    async with session_factory() as session:
        await SettingsService(SettingRepository(session)).get_all()
    # Phase 2 M23: this service's first-ever outbound calls to other
    # services (Media Service for upload proxying, Ingestion Service for
    # the public snapshot endpoint) -- one shared client for both, same
    # pattern every other service uses for its own outbound clients.
    app.state.http_client = httpx.AsyncClient()
    logger.info("camera_service_started")
    yield
    await app.state.http_client.aclose()
    logger.info("camera_service_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="IBVAP Camera Management Service", version="0.1.0", lifespan=lifespan)
    install_correlation_id_middleware(app)
    install_metrics(app, settings.service_name)
    install_error_handlers(app)
    app.include_router(camera_routes.router)
    app.include_router(zone_routes.router)
    app.include_router(sector_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(internal_routes.router)
    app.include_router(health_routes.router)
    return app


app = create_app()
