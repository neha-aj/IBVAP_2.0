from contextlib import asynccontextmanager

from fastapi import FastAPI

from ibvap_common.errors import install_error_handlers
from ibvap_common.logging import configure_logging, get_logger, install_correlation_id_middleware
from ibvap_common.metrics import install_metrics

from app.api import health as health_routes
from app.api import internal as internal_routes
from app.api import preview as preview_routes
from app.core.config import get_settings
from app.workers.worker_manager import WorkerManager

settings = get_settings()
configure_logging(settings.service_name)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = WorkerManager(settings)
    app.state.worker_manager = manager
    await manager.start()
    logger.info("ingestion_service_started")
    yield
    await manager.stop()
    logger.info("ingestion_service_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="IBVAP Stream Ingestion Service", version="0.1.0", lifespan=lifespan)
    install_correlation_id_middleware(app)
    install_metrics(app, settings.service_name)
    install_error_handlers(app)
    app.include_router(preview_routes.router)
    app.include_router(internal_routes.router)
    app.include_router(health_routes.router)
    return app


app = create_app()
