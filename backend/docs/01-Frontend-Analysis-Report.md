# IBVAP — Frontend Analysis Report

**Document status:** Frozen specification. This document is derived entirely from the attached React source (`Lux-main`) and treats it as the product's functional contract. No frontend changes are proposed here.

---

## 1. Application Structure

React 18 SPA, `react-router-dom` for routing, Tailwind for styling, Recharts for charts, lucide-react for icons.

```
src/
  layouts/DashboardLayout.jsx      # Sidebar + Topbar shell wrapping every page
  routes/AppRoutes.jsx             # Route table
  pages/                           # One component per nav item
  components/{surveillance,dashboard,events,alerts,analytics,layout,common}/
  hooks/use{Cameras,Alerts,Detections}.js   # Currently return static mock arrays
  services/{api,cameraService,eventService,alertService}.js  # Stub clients, all unimplemented
  data/mock*.js                    # Placeholder datasets standing in for API responses
```

`src/services/api.js` is an intentional stub (`throw new Error('API integration is not configured')`) — this is the seam where the real backend integration must land. `cameraService`, `eventService`, `alertService` are similarly empty async stubs (`getAll: async()=>[]`). This confirms: **the intended integration point is a REST client layer per domain, with the hooks (`useCameras`, `useAlerts`, `useDetections`) as the consumption point for pages/components.**

## 2. Routing

| Path | Page | Purpose |
|---|---|---|
| `/` | Dashboard | Command overview / KPIs |
| `/surveillance` | Surveillance | Live grid, filtering, per-camera drill-down |
| `/cameras` | Cameras | Camera inventory/management |
| `/alerts` | Alerts | Alert triage list |
| `/events` | Events | Historical event log with filters |
| `/analytics` | Analytics | Aggregated charts |
| `/settings` | Settings | System/detection/alert/camera configuration (static placeholders) |
| `*` | → redirect to `/` | |

All routes render inside `DashboardLayout` (persistent Sidebar + Topbar).

## 3. Page-by-Page Analysis

### 3.1 Dashboard (`/`)
- **StatCard × 6**: Active Cameras (of N deployed), Cameras Offline, Active Alerts (+ critical count), People Detected (today), Vehicles Detected (today), Events Today (+ % vs average).
  - Currently hardcoded (`online` computed from mock cameras; others are literals) → **must become a single aggregate endpoint.**
- **ActivityOverview**: Recharts `AreaChart`, x-axis = hour buckets, y = detection/activity count for "Today". Needs a time-bucketed activity series.
- **CameraStatus**: first 4 cameras with status dot + badge. Needs live camera list (subset).
- **RecentAlerts**: first 4 alerts, type/camera/timestamp/severity badge. Needs alerts sorted by recency.

### 3.2 Surveillance (`/surveillance`)
Most stateful page. Client-side filtering only today — backend should support the same filters server-side for scale, but current UI filters an already-fetched camera+detection set:
- Search (name / id / location substring)
- Status filter: `all | online | warning | offline`
- Detection-type filter: `all | person | vehicle | intrusion | anpr` (note: `intrusion`/`anpr` are matched against `camera.alert` string today — placeholder logic that a real alert-type taxonomy must replace)
- View toggle: `grid | list`
- Camera selection → reveals **DetectionSummary**, **ActiveEvents**, **CameraDetails** for that camera

**CameraCard / VideoPlaceholder / DetectionOverlay**: each camera tile is a video area with a "LIVE"/"SIMULATED FEED" badge and bounding boxes drawn from `detections[]` (`{id, cameraId, type, confidence, trackId, bbox:{x,y,width,height}}`, all as **percentages** of frame width/height — i.e. normalized 0–100 coordinates, not pixels). **This is the exact contract the detection pipeline must emit for overlay rendering, and it must be delivered in near-real-time (WebSocket) per visible camera.**

The literal text "Awaiting stream connection" / "SIMULATED FEED" is a placeholder for an actual video element — the real implementation needs a playable stream (WebRTC/HLS/MJPEG) mounted where `VideoPlaceholder` sits.

**DetectionSummary**: counts of persons/vehicles/unknown for the selected camera + average confidence across current detections — computed client-side from the detections array; backend can simply expose current live detections per camera and let this remain client-computed, or return the summary directly.

**ActiveEvents**: last few events for a camera, "N minutes ago" style relative timestamps — needs a per-camera recent-events feed.

**CameraDetails**: static camera metadata (id, location, status, resolution, fps, connection, last updated) — a direct camera-record read.

### 3.3 Cameras (`/cameras`)
Reuses `CameraGrid`/`CameraCard` in inventory mode. Needs full CRUD eventually (add/edit/remove camera, though no create/edit UI exists yet in this phase — inventory view only).

### 3.4 Alerts (`/alerts`)
`AlertList` → `AlertCard` grid. Each alert: `{id, type, severity, cameraId, cameraName, objectType, location, timestamp, status}`. Severity ∈ `{critical, high, medium, low}`. Status ∈ `{active, reviewing, resolved}`. "View Details" button exists but is not wired — needs an alert detail view/endpoint and a status-transition action (acknowledge/resolve).

### 3.5 Events (`/events`)
`EventFilters` (camera / event type / severity / date — currently non-functional `<select>`s with a single static option each) + `EventTable`. Event shape: `{id, time, cameraName, event, objectType, location, severity, status}`. This is effectively the alert schema renamed/broadened (`mockEvents` is built from `mockAlerts` plus two extra "informational" events like "Patrol Vehicle" with no alert). **Conclusion: Events is the superset log (all detections/rule triggers, including non-alerting ones); Alerts is the subset that requires operator attention.** `EventDetails.jsx` exists as an unused placeholder aside ("Future event inspection" + image placeholder) — signals a planned per-event snapshot/detail drawer.

### 3.6 Analytics (`/analytics`)
- **ActivityChart**: bar chart, activity count per weekday.
- **AlertChart**: pie chart, alert count by category (`Intrusion / Vehicle / Loitering / Other`).
- **CameraAnalytics**: per-camera uptime % (progress bars) + "today" people/vehicle totals.
- Inline **Events by camera** list (camera name + event count).
All four need aggregation endpoints; three are chart-shaped, one is a simple ranked list.

### 3.7 Settings (`/settings`)
Four groups, currently all "Configuration pending backend connection":
- **System**: System status, Deployment mode, Server status (health/mode reporting)
- **Detection**: Human, Vehicle, ANPR, Face, Intrusion, Night detection — **toggle switches implying per-capability enable/disable flags**, confirming the roadmap of detector modules beyond Phase 1 (ANPR, face detection).
- **Alerts**: Alert notifications toggle, Alert severity threshold, Event retention (duration)
- **Camera**: Camera configuration, Stream configuration
This page defines the shape of a `settings`/config table plus toggle semantics per capability.

## 4. Shared Components

- `PageHeader` — title/subtitle, used on every page.
- `Badge` — colored pill; `tone` prop keyed off status/severity strings (`online, warning, offline, critical, high, medium, low, reviewing, resolved, active, neutral`). **Backend enums must exactly match these tone strings** (or the mapping layer must translate).
- `StatusDot` — colored dot, same status vocabulary as `Badge`.
- `Button`, `Modal`, `EmptyState` — generic; `Modal`/`EmptyState` not yet wired to any page but present for future dialogs (e.g. camera add/edit, empty list states).

## 5. Inferred Data Contracts (from mock shapes)

| Entity | Fields observed |
|---|---|
| Camera | `id, name, location, sector, status(online/warning/offline), resolution, fps, lastActive, detections:{persons,vehicles}, alert` |
| Detection | `id, cameraId, type(person/vehicle/...), confidence(0-1), trackId, bbox:{x,y,width,height}` (% of frame) |
| Alert | `id, type, severity(critical/high/medium/low), cameraId, cameraName, objectType, location, timestamp, status(active/reviewing/resolved)` |
| Event | `id, time, cameraName, event, objectType, location, severity, status` |

`cameraName` and `location` are denormalized onto alert/event records in the mocks — the API can either continue denormalizing (cheaper for the frontend, avoids joins client-side) or return `cameraId` and let a lookup map resolve names; **recommendation: denormalize in the API response** to match the existing contract exactly and avoid frontend changes.

## 6. Required Realtime (WebSocket) Behavior

The frontend has no live-update code today (all data is static), but the product vision ("real-time overview", "LIVE" badges, live detection overlays) requires:
- New detections streamed per visible camera (bbox overlay refresh)
- New alerts pushed to Alerts page / Dashboard "Recent Alerts" / Dashboard stat counters
- Camera status transitions (online → warning → offline) pushed to Cameras/Dashboard/Surveillance
- New events pushed to Events page (if kept open)

## 7. Missing / Placeholder Functionality Explicitly Signaled by the Code

- No authentication UI exists yet (no login page/route) — **assumption: Phase 1 backend implements auth (JWT) but the frontend login screen is out of scope for this phase or will be added without changing the analyzed structure; the API must still enforce auth on all endpoints.**
- No camera create/edit form, no alert "View Details" panel, no working `EventFilters`, no video player — these are the concrete gaps future frontend iterations will fill; backend should expose the endpoints now (CRUD, alert detail, filter query params) so the frontend gap can close without backend rework.
- `EventDetails.jsx` (unused) implies a per-event media viewer → snapshot storage & retrieval must exist even before the frontend consumes it.

## 8. Integration Points Summary

1. Replace `src/services/api.js` with a real fetch/axios client (base URL, auth header injection, error normalization).
2. Implement `cameraService`, `eventService`, `alertService` against the REST API defined in the API Specification document.
3. Replace `useCameras`/`useAlerts`/`useDetections` mock-returning hooks with data-fetching hooks (React Query or SWR recommended) hitting those services, plus a WebSocket subscription hook for realtime deltas.
4. Keep all component prop shapes identical to the mock shapes documented above so **zero component-level changes are required** — only the data-fetching layer changes.
