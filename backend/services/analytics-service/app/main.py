from contextlib import asynccontextmanager

from fastapi import FastAPI

from ibvap_common.db import build_engine
from ibvap_common.errors import install_error_handlers
from ibvap_common.logging import configure_logging, get_logger, install_correlation_id_middleware
from ibvap_common.metrics import install_metrics

from app.api import analytics as analytics_routes
from app.api import dashboard as dashboard_routes
from app.api import health as health_routes
from app.core.config import get_settings
from app.jobs.scheduler import RefreshScheduler

settings = get_settings()
configure_logging(settings.service_name)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = build_engine(settings)
    scheduler = RefreshScheduler(engine, interval_seconds=settings.refresh_interval_seconds)
    app.state.scheduler = scheduler
    await scheduler.start()
    logger.info("analytics_service_started")
    yield
    await scheduler.stop()
    await engine.dispose()
    logger.info("analytics_service_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="IBVAP Analytics Service", version="0.1.0", lifespan=lifespan)
    install_correlation_id_middleware(app)
    install_metrics(app, settings.service_name)
    install_error_handlers(app)
    app.include_router(dashboard_routes.router)
    app.include_router(analytics_routes.router)
    app.include_router(health_routes.router)
    return app


app = create_app()
