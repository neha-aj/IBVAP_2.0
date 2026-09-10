from contextlib import asynccontextmanager

from fastapi import FastAPI

from ibvap_common.errors import install_error_handlers
from ibvap_common.logging import configure_logging, get_logger, install_correlation_id_middleware
from ibvap_common.metrics import install_metrics

from app.api import auth as auth_routes
from app.api import health as health_routes
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService

settings = get_settings()
configure_logging(settings.service_name)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bootstrap: create the first admin user if the table is empty, so a
    # fresh `docker compose up` is immediately usable (IG M1 completion criteria).
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AuthService(UserRepository(session), TokenRepository(session), settings)
        await service.ensure_bootstrap_admin(
            settings.bootstrap_admin_username, settings.bootstrap_admin_password
        )
    logger.info("auth_service_started")
    yield
    logger.info("auth_service_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="IBVAP Auth Service", version="0.1.0", lifespan=lifespan)
    install_correlation_id_middleware(app)
    install_metrics(app, settings.service_name)
    install_error_handlers(app)
    app.include_router(auth_routes.router)
    app.include_router(health_routes.router)
    return app


app = create_app()
