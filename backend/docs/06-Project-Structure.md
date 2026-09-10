# IBVAP — Complete Project Structure

```
ibvap/
├── docker-compose.yml
├── docker-compose.test.yml
├── .env.example
├── nginx/
│   ├── nginx.conf
│   └── conf.d/api-gateway.conf
├── docs/
│   ├── 01-Frontend-Analysis-Report.md
│   ├── 02-System-Architecture-Specification.md
│   ├── 03-Implementation-Guide.md
│   ├── 04-API-Specification.md
│   ├── 05-Database-Specification.md
│   └── 06-Project-Structure.md
├── libs/
│   └── ibvap_common/                # shared, versioned internal package (no service-to-service imports)
│       ├── ibvap_common/
│       │   ├── auth.py              # JWT validation, RBAC dependency
│       │   ├── logging.py           # structured logging setup + correlation ID
│       │   ├── settings.py          # BaseSettings mixin
│       │   ├── errors.py            # RFC7807 exception handlers
│       │   └── redis_streams.py     # producer/consumer-group helpers
│       └── pyproject.toml
├── frontend/                        # existing Lux-main React app (unmodified structure)
│   └── ...
│
├── services/
│   ├── auth-service/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── api/{auth.py}
│   │   │   ├── schemas/{user.py,token.py}
│   │   │   ├── models/{user.py,refresh_token.py}
│   │   │   ├── repositories/{user_repo.py,token_repo.py}
│   │   │   ├── services/{auth_service.py}
│   │   │   └── core/{config.py,security.py}
│   │   ├── alembic/{versions/}
│   │   ├── tests/{unit/,integration/}
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── camera-service/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── api/{cameras.py,sectors.py,settings.py,health.py}
│   │   │   ├── schemas/{camera.py,sector.py,setting.py}
│   │   │   ├── models/{camera.py,sector.py,camera_health.py,zone.py,setting.py}
│   │   │   ├── repositories/{camera_repo.py,sector_repo.py,setting_repo.py}
│   │   │   ├── services/{camera_service.py,health_monitor.py}
│   │   │   └── core/{config.py}
│   │   ├── alembic/{versions/}
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── ingestion-service/
│   │   ├── app/
│   │   │   ├── main.py                  # worker manager, spawns per-camera tasks
│   │   │   ├── workers/{camera_worker.py}
│   │   │   ├── capture/{rtsp.py,usb.py,onvif.py}
│   │   │   ├── preview/{mjpeg.py,hls.py}
│   │   │   ├── streaming/{frame_publisher.py}
│   │   │   ├── health/{heartbeat.py}
│   │   │   └── core/{config.py}
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── detection-service/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── inference/{yolo_runner.py,onnx_runner.py,model_registry.py}
│   │   │   ├── streaming/{frame_consumer.py,detection_publisher.py}
│   │   │   ├── schemas/{detection.py}
│   │   │   └── core/{config.py}
│   │   ├── models/                       # weights (mounted volume, not committed)
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── Dockerfile.gpu
│   │   └── pyproject.toml
│   │
│   ├── tracking-service/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── tracking/{bytetrack_runner.py,track_manager.py}
│   │   │   ├── streaming/{detection_consumer.py,track_publisher.py}
│   │   │   ├── schemas/{track.py}
│   │   │   └── core/{config.py}
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── event-alert-service/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── api/{events.py,alerts.py,health.py}
│   │   │   ├── schemas/{event.py,alert.py}
│   │   │   ├── models/{event.py,alert.py,detection.py,track.py}
│   │   │   ├── repositories/{event_repo.py,alert_repo.py}
│   │   │   ├── rules/{engine.py,intrusion.py,loitering.py,offline_alert.py,zone_crossing.py}
│   │   │   ├── streaming/{track_consumer.py,pubsub_publisher.py}
│   │   │   └── core/{config.py}
│   │   ├── alembic/{versions/}
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── media-service/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── api/{snapshots.py,recordings.py,health.py}
│   │   │   ├── schemas/{snapshot.py,recording.py}
│   │   │   ├── models/{snapshot.py,recording.py}
│   │   │   ├── repositories/{media_repo.py}
│   │   │   ├── storage/{backend.py,local_backend.py,s3_backend.py}
│   │   │   └── core/{config.py}
│   │   ├── alembic/{versions/}
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── analytics-service/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── api/{dashboard.py,analytics.py,health.py}
│   │   │   ├── schemas/{stats.py}
│   │   │   ├── repositories/{analytics_repo.py}
│   │   │   ├── jobs/{refresh_views.py,scheduler.py}
│   │   │   └── core/{config.py}
│   │   ├── alembic/{versions/}         # materialized view definitions
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── realtime-gateway/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── ws/{connection_manager.py,auth.py,topics.py}
│   │   │   ├── streaming/{pubsub_bridge.py}
│   │   │   └── core/{config.py}
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   └── notification-service/            # stub scaffold, Phase 2 activation
│       ├── app/{main.py,core/config.py}
│       ├── Dockerfile
│       └── pyproject.toml
│
├── infra/
│   ├── postgres/init/{01-schemas.sql}
│   ├── redis/redis.conf
│   └── monitoring/{prometheus.yml,grafana/dashboards/}
│
└── scripts/
    ├── seed_dev_data.py
    ├── synthetic_camera.py             # loops a test video as an RTSP/file source for M3+ testing
    └── run_integration_tests.sh
```

**Rule enforced across the tree:** no `services/*/app` directory ever imports from another `services/*` directory. The only shared code lives in `libs/ibvap_common`, installed as a normal dependency by each service's `pyproject.toml`.
