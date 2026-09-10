from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from ibvap_common.errors import UnauthorizedError, install_error_handlers
from ibvap_common.logging import configure_logging, get_logger, install_correlation_id_middleware
from ibvap_common.metrics import install_metrics
from ibvap_common.redis_streams import build_redis_client

from app.api import health as health_routes
from app.api import system as system_routes
from app.core.config import get_settings
from app.streaming.health_poller import HealthPoller
from app.streaming.pubsub_bridge import PubSubBridge
from app.ws.auth import authenticate
from app.ws.connection_manager import ConnectionManager

settings = get_settings()
configure_logging(settings.service_name)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = ConnectionManager()
    redis_client = build_redis_client(settings)
    bridge = PubSubBridge(redis_client, manager, settings)
    health_poller = HealthPoller(redis_client, settings)

    app.state.connection_manager = manager
    app.state.redis_client = redis_client
    app.state.health_poller = health_poller

    bridge.start()
    health_poller.start()
    logger.info("realtime_gateway_started")
    yield
    await health_poller.stop()
    await bridge.stop()
    await redis_client.aclose()
    logger.info("realtime_gateway_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="IBVAP Realtime Gateway", version="0.1.0", lifespan=lifespan)
    install_correlation_id_middleware(app)
    install_metrics(app, settings.service_name)
    # Needed now that this service has a real REST route (`GET /api/v1/
    # system/health`), not just `/health`/`/ready`/the `/ws` handshake --
    # without this, `require_role`'s `UnauthorizedError`/`ForbiddenError`
    # would fall through FastAPI's default handling as an unhandled 500
    # instead of the RFC7807 401/403 every other service returns.
    install_error_handlers(app)
    app.include_router(health_routes.router)
    app.include_router(system_routes.router)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """SAS §8, API Spec §8: `wss://{host}/ws?token={jwt}`. Auth happens
        once at connect; after that it's `{"action":"subscribe"|"unsubscribe",
        "topics":[...]}` messages in, `{"event":..., "data":...}` envelopes
        out."""
        token = websocket.query_params.get("token")
        try:
            authenticate(token, settings)
        except UnauthorizedError:
            await websocket.close(code=4401, reason="Unauthorized")
            return

        manager: ConnectionManager = websocket.app.state.connection_manager
        await websocket.accept()
        connection_id = manager.connect(websocket)
        logger.info("ws_client_connected", connection_id=connection_id)

        try:
            while True:
                message = await websocket.receive_json()
                action = message.get("action")
                topics = message.get("topics", [])
                if action == "subscribe":
                    manager.subscribe(connection_id, topics)
                elif action == "unsubscribe":
                    manager.unsubscribe(connection_id, topics)
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("ws_client_error", connection_id=connection_id, error=str(exc))
        finally:
            manager.disconnect(connection_id)
            logger.info("ws_client_disconnected", connection_id=connection_id)

    return app


app = create_app()
