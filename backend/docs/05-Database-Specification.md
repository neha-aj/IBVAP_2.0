# IBVAP — Database Specification

PostgreSQL 16. One schema per owning service. UUID PKs (`gen_random_uuid()`, `pgcrypto`). All tables: `created_at timestamptz default now()`, `updated_at timestamptz default now()` (trigger-maintained).

## 1. Schema: `auth`

### `auth.users`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| username | text unique not null | |
| password_hash | text not null | bcrypt/argon2 |
| role | text not null | `admin\|operator\|viewer` (check constraint) |
| is_active | boolean default true | |
| created_at / updated_at | timestamptz | |

### `auth.refresh_tokens`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → users.id | |
| token_hash | text not null | |
| expires_at | timestamptz not null | |
| revoked | boolean default false | |

Indexes: `refresh_tokens(user_id)`, `refresh_tokens(token_hash)`.

## 2. Schema: `camera`

### `camera.sectors`
| Column | Type |
|---|---|
| id | uuid PK |
| name | text unique |
| code | text unique (e.g. `Alpha`) |

### `camera.cameras`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | (external display id, e.g. `BOP-01-CAM-01`, stored as `external_id text unique`) |
| external_id | text unique not null | matches frontend `camera.id` |
| name | text not null | |
| location | text not null | |
| sector_id | uuid FK → sectors.id | |
| type | text not null | `rtsp\|usb\|ip\|file\|webcam` (`file`=uploaded video looped/played through the pipeline as a virtual camera; `webcam`=local capture device) |
| source_url | text | connection string, encrypted at rest |
| status | text not null default 'offline' | `online\|warning\|offline` |
| resolution | text | e.g. `1920×1080` |
| fps | integer default 0 | |
| last_active_at | timestamptz | |
| created_at / updated_at | timestamptz | |

### `camera.camera_health`
| Column | Type |
|---|---|
| id | uuid PK |
| camera_id | uuid FK → cameras.id |
| status | text |
| fps | integer |
| latency_ms | integer |
| checked_at | timestamptz |

Index: `camera_health(camera_id, checked_at desc)`.

### `camera.zones` *(Phase 2 rule engine input, scaffolded now)*
| Column | Type |
|---|---|
| id | uuid PK |
| camera_id | uuid FK → cameras.id |
| name | text |
| polygon | jsonb | list of normalized `{x,y}` points |
| zone_type | text | `restricted\|perimeter\|general` |

### `camera.settings`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| group_name | text not null | `system\|detection\|alerts\|camera` |
| key | text not null | e.g. `humanDetection` |
| value | jsonb not null | `{enabled: true}` / `{threshold: "medium"}` etc. |
| unique(group_name, key) | | |

Indexes: `cameras(status)`, `cameras(sector_id)`, `cameras(external_id)`.

## 3. Schema: `events` (owned by Event/Alert Service; also stores raw detections/tracks summaries needed for rule evaluation and history)

### `events.detections`
| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | high write volume, cheap PK |
| camera_id | uuid | references `camera.cameras.id` (cross-service ref, no FK) |
| track_id | bigint | |
| object_type | text | `person\|vehicle\|...` |
| confidence | numeric(4,3) | |
| bbox_x | numeric(6,3) | percentage 0-100 |
| bbox_y | numeric(6,3) | |
| bbox_w | numeric(6,3) | |
| bbox_h | numeric(6,3) | |
| frame_ts | timestamptz not null | |
| created_at | timestamptz | |

Indexes: `(camera_id, frame_ts desc)`, `(track_id)`.
Retention: partitioned by day (declarative partitioning), old partitions dropped/archived per `alerts` "Event retention" setting.

### `events.tracks`
| Column | Type |
|---|---|
| id | bigserial PK |
| camera_id | uuid |
| object_type | text |
| first_seen | timestamptz |
| last_seen | timestamptz |
| status | text | `active\|lost` |

### `events.events`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| camera_id | uuid not null | |
| event_type | text not null | e.g. `Fence Intrusion`, `Patrol Vehicle` |
| object_type | text | |
| severity | text not null | `critical\|high\|medium\|low` |
| location | text | denormalized from camera at write time |
| status | text not null default 'active' | `active\|reviewing\|resolved` |
| description | text | |
| snapshot_id | uuid | references `media.snapshots.id` |
| requires_review | boolean default false | if true, mirrored into `alerts` |
| created_at | timestamptz | |

Indexes: `(camera_id, created_at desc)`, `(severity)`, `(status)`, `(event_type)`.

### `events.alerts`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| event_id | uuid FK → events.id | |
| camera_id | uuid not null | denormalized |
| type | text not null | mirrors `event_type` |
| severity | text not null | |
| status | text not null default 'active' | `active\|reviewing\|resolved` |
| acknowledged_by | uuid | references `auth.users.id`, no FK across schema |
| acknowledged_at | timestamptz | |
| resolved_at | timestamptz | |
| created_at | timestamptz | |

Indexes: `(status)`, `(severity)`, `(camera_id, created_at desc)`.

## 4. Schema: `media`

### `media.snapshots`
| Column | Type |
|---|---|
| id | uuid PK |
| camera_id | uuid |
| event_id | uuid nullable |
| file_path | text not null |
| width / height | integer |
| created_at | timestamptz |

### `media.recordings`
| Column | Type |
|---|---|
| id | uuid PK |
| camera_id | uuid |
| event_id | uuid nullable |
| file_path | text not null |
| start_time / end_time | timestamptz |
| duration_seconds | integer |
| created_at | timestamptz |

Indexes: `(camera_id, created_at desc)` on both tables.

## 5. Schema: `analytics` (materialized views, refreshed on schedule)

- `analytics.mv_activity_by_hour(hour_bucket, count)`
- `analytics.mv_alerts_by_type(type, count)`
- `analytics.mv_camera_uptime(camera_id, uptime_pct)`
- `analytics.mv_events_by_camera(camera_id, camera_name, count)`
- `analytics.mv_daily_counters(day, people_detected, vehicles_detected, events_count, alerts_count, critical_alerts_count)`

Refresh via `REFRESH MATERIALIZED VIEW CONCURRENTLY` on a cron (e.g. every 60s) triggered by the Analytics Service, plus an on-demand short-TTL Redis cache in front of these endpoints.

## 6. Cross-Schema Reference Policy

No physical foreign keys across schemas (services are independently deployable/migratable). Referential integrity for cross-service IDs (e.g. `events.camera_id` → `camera.cameras.id`) is enforced at the application layer: the Event/Alert Service validates `camera_id` exists via the Camera Management Service's internal API (or a cached lookup) before insert.

## 7. Alembic Convention

Each service repo has its own `alembic/` directory targeting only its schema (`version_table_schema` set accordingly), so migrations can be applied/rolled back independently per service without coordinating a single monolithic migration history.
