# IBVAP — API Specification

Base URL: `/api/v1`. All responses `application/json` (camelCase fields). Auth: `Authorization: Bearer {jwt}` unless noted. Errors: RFC7807 problem+json.

## 1. Auth Service

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/auth/login` | `{username, password}` → `{accessToken, refreshToken, user}` | none |
| POST | `/auth/refresh` | `{refreshToken}` → new `{accessToken, refreshToken}` | none |
| POST | `/auth/logout` | Revokes refresh token | required |
| GET | `/auth/me` | Current user profile + role | required |

## 2. Camera Management Service

| Method | Path | Description |
|---|---|---|
| GET | `/cameras` | List cameras. Query: `status`, `sector`, `search`, `page`, `pageSize`. Returns array shaped exactly like `mockCameras` (`id,name,location,sector,status,resolution,fps,lastActive,detections:{persons,vehicles},alert`). |
| GET | `/cameras/{id}` | Single camera detail (adds connection info for `CameraDetails`). |
| POST | `/cameras` | Create camera `{name, location, sector, type(rtsp|usb|ip|file|webcam), sourceUrl}`. `file` = uploaded video (sourceUrl = stored file path/URI); `webcam` = local device index/URI. Both run through the identical detection/tracking/event pipeline as rtsp/ip. |
| POST | `/cameras/{id}/upload` | Multipart video upload for a `file`-type camera; stores the file via Media Storage Service and sets `sourceUrl`. |
| PUT | `/cameras/{id}` | Update camera config. |
| DELETE | `/cameras/{id}` | Remove camera (stops ingestion worker). |
| GET | `/cameras/status/summary` | `{online, warning, offline, total}` — powers Dashboard camera stat cards. |
| GET | `/cameras/{id}/stream` | Returns live stream URL(s): `{mjpegUrl, hlsUrl}`. |
| GET | `/cameras/{id}/snapshot` | Latest snapshot image (redirect or binary). |
| GET | `/cameras/{id}/detections/current` | Current live detections for overlay: array of `{id, cameraId, type, confidence, trackId, bbox:{x,y,width,height}}`. |
| GET | `/cameras/{id}/health` | `{fps, lastFrameAt, latencyMs, status}`. |

## 3. Settings (part of Camera Management Service)

| Method | Path | Description |
|---|---|---|
| GET | `/settings` | All settings grouped as in Settings page: `system`, `detection`, `alerts`, `camera`. |
| PUT | `/settings/{group}/{key}` | Update a single toggle/value, e.g. `detection/humanDetection → {enabled: true}`. |

## 4. Detections (read path, Detection Service via Gateway)

| Method | Path | Description |
|---|---|---|
| GET | `/detections` | Historical detections. Query: `cameraId`, `type`, `from`, `to`, `page`, `pageSize`. |

## 5. Event/Alert Service

| Method | Path | Description |
|---|---|---|
| GET | `/events` | Query: `camera`, `eventType`, `severity`, `status`, `date`, `page`, `pageSize`. Returns `EventTable` shape: `{id,time,cameraName,event,objectType,location,severity,status}`. |
| GET | `/events/{id}` | Full event detail incl. `snapshotUrl` (for future `EventDetails`). |
| PATCH | `/events/{id}` | `{status}` transition. |
| GET | `/alerts` | Query: `status`, `severity`, `camera`, `page`, `pageSize`. Returns `AlertCard` shape: `{id,type,severity,cameraId,cameraName,objectType,location,timestamp,status}`. |
| GET | `/alerts/{id}` | Alert detail. |
| PATCH | `/alerts/{id}/status` | `{status: active|reviewing|resolved}`, sets `acknowledgedBy`/`resolvedAt` server-side. |

## 6. Media Storage Service

| Method | Path | Description |
|---|---|---|
| GET | `/media/snapshots/{id}` | Snapshot image/binary or signed URL. |
| GET | `/media/recordings/{id}` | Recording metadata + playback URL. |
| POST | `/media/snapshots` *(internal, service-to-service)* | Store a captured frame; returns `{id, url}`. |

## 7. Analytics Service

| Method | Path | Description |
|---|---|---|
| GET | `/dashboard/stats` | `{activeCameras, totalCameras, camerasOffline, activeAlerts, criticalAlerts, peopleDetectedToday, vehiclesDetectedToday, eventsToday, eventsTodayDeltaPct}`. |
| GET | `/analytics/activity-overview?range=today` | Time-bucketed series for `ActivityOverview` area chart: `[{h:"08:00", v:14}, ...]`. |
| GET | `/analytics/activity-weekly` | `[{name:"Mon", value:34}, ...]` for `ActivityChart`. |
| GET | `/analytics/alerts-by-type` | `[{name:"Intrusion", value:32}, ...]` for `AlertChart` pie. |
| GET | `/analytics/camera-uptime` | `[{name:"BOP-01", value:99.9}, ...]` for `CameraAnalytics`. |
| GET | `/analytics/events-by-camera` | `[{name:"BOP-01", count:84}, ...]`. |

## 8. Realtime Gateway (WebSocket)

`wss://{host}/ws?token={jwt}`

Client → server:
```json
{"action":"subscribe","topics":["alerts","events","camera:BOP-01-CAM-01"]}
{"action":"unsubscribe","topics":["camera:BOP-01-CAM-01"]}
```

Server → client events:
| Event | Payload | Fires on |
|---|---|---|
| `camera.status_changed` | `{cameraId, status}` | ingestion heartbeat state change |
| `detection.new` | `{cameraId, detections:[...]}` | new inference batch for a subscribed camera |
| `event.new` | Event shape (§5) | rule engine writes an event |
| `alert.new` | Alert shape (§5) | rule engine writes an alert |
| `alert.updated` | Alert shape (§5) | status transition |
| `system.health` | `{service, status}` | service health change (optional, ops use) |

## 9. Health/Ops (every service)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness. |
| GET | `/ready` | Readiness (DB/Redis reachability). |
| GET | `/metrics` | Prometheus exposition format. |

## 10. Standard Error Shape

```json
{
  "type": "https://ibvap.dev/errors/not-found",
  "title": "Camera not found",
  "status": 404,
  "detail": "No camera with id BOP-99-CAM-01",
  "traceId": "a1b2c3"
}
```

## 11. Auth/RBAC Matrix

| Role | Read (cameras/events/alerts/analytics) | Update alert/event status | Camera CRUD | Settings write | User management |
|---|---|---|---|---|---|
| `viewer` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `operator` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ |
