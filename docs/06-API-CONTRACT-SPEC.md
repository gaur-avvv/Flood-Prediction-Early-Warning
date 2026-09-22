# 06 — API Contract Specification

## 1. Conventions (apply to every endpoint)

| Concern | Rule |
|---|---|
| Base path | `/v1`. Legacy unversioned paths remain as deprecated aliases for one release (REQ-API-01). |
| Content type | `application/json` for data; `application/geo+json` for layers; `application/vnd.mapbox-vector-tile` for tiles; `application/cap+xml` for CAP export. |
| Authentication | `X-API-Key` header for machine clients; session cookie for the console. Scopes: `read:public`, `read:agency`, `write:operator`, `admin`, `notify`, `read:sensitive`. |
| Authorisation failures | `401` when credentials are absent/invalid; `403` when the scope is insufficient. Never leak which was the case beyond that. |
| Timestamps | RFC 3339 UTC with `Z` (`2026-09-21T09:30:00Z`) in every field whose name ends in `_at`, `_from`, `_to` or `as_of`. |
| Units | Metres for depth and elevation, millimetres for rainfall, m³/s for discharge, km² for area, decimal degrees for raw coordinates. Units are stated in field names (`depth_m`, `rainfall_24h_mm`). |
| Probability | Float `0.0–1.0`, never a percentage. Percentages appear only in rendered messages. |
| Provenance | Every hazard-bearing response includes the block in §1.1. |
| Errors | One shape (§4). Never a bare string. |
| Rate limits | Per key: read 600/min, scan 6/min, train 1/hour, notify 30/min. Exceeded → `429` with `Retry-After`. |
| Idempotency | `Idempotency-Key` header supported on all `POST`s; the same key returns the original result. |
| Caching | Immutable resources (runs, their layers and tiles) send `Cache-Control: public, max-age=<long>` plus a strong `ETag`. Mutable resources send a short `max-age` and `ETag`. **No `no-cache` by default** (REQ-MAP-04). |
| Pagination | Cursor-based: `?limit=&cursor=`, response carries `next_cursor`. Layer endpoints use `bbox` + `limit` instead. |
| Field selection | `?fields=` reduces payload for low-bandwidth clients. |
| Trace | Every response carries `X-Request-Id`; server logs carry the same id. |

### 1.1 Standard provenance block
```json
{
  "run_id": "run_2026-09-21T09:15Z_mumbai",
  "as_of": "2026-09-21T09:15:00Z",
  "model_version": "ensemble-2.1.0",
  "validation_scope": "In-sample training metrics; synthetic holdout. Not operationally validated.",
  "data_sources": [
    { "name": "Open-Meteo",            "licence": "CC-BY-4.0", "retrieved_at": "2026-09-21T09:14:31Z" },
    { "name": "Open-Meteo Flood/GloFAS","licence": "Copernicus", "retrieved_at": "2026-09-21T09:14:36Z" },
    { "name": "OpenTopoData (SRTM 30m)","licence": "Public domain","retrieved_at": "2026-09-01T11:02:00Z" },
    { "name": "SoilGrids (ISRIC)",     "licence": "CC-BY-4.0", "retrieved_at": "2026-09-01T11:02:12Z" },
    { "name": "OpenStreetMap contributors","licence": "ODbL",   "retrieved_at": "2026-09-01T11:03:40Z" }
  ],
  "enriched_fields": ["elevation_m", "soil_moisture_pct"],
  "degraded": [{ "source": "Open-Meteo Flood/GloFAS", "reason": "timeout", "fallback": "neutral_marked" }]
}
```

---

## 2. Endpoint catalogue

`A` = anonymous allowed · `K` = API key · `KS` = key with a specific scope.

| Method | Path | Auth | Cache | Purpose |
|---|---|---|---|---|
| GET | `/v1/health` | A | none | Liveness + dependency status |
| GET | `/v1/ready` | A | none | Readiness gate for orchestrators |
| GET | `/v1/runs` | K | 30 s | List recent scan runs (city, resolution, time, status) |
| GET | `/v1/runs/{run_id}` | K | immutable | Run metadata, layer list, legend, provenance |
| POST | `/v1/runs` | KS `write:operator` | — | Trigger a scan (queued; returns run id) |
| POST | `/v1/scan` | KS `write:operator` | — | Synchronous-capable scan for small budgets (demonstration path) |
| GET | `/v1/layers/{layer}` | K | per run | GeoJSON layer, `bbox`-filtered |
| GET | `/v1/tiles/{layer}/{run_id}/{z}/{x}/{y}.mvt` | K | immutable | Vector tile |
| GET | `/v1/cells/{h3}` | K | short | Single-cell detail: scores, drivers, exposure, history |
| GET | `/v1/hotspots` | K | per run | Hotspot objects (query, not compute) |
| GET | `/v1/hotspots/{hotspot_id}` | K | per run | Hotspot detail incl. member cells and lifecycle history |
| GET | `/v1/wards` | K | long | Ward list with geometry and provenance |
| GET | `/v1/wards/{ward_id}` | K | long | Single ward geometry + metadata |
| GET | `/v1/wards/readiness` | K | per run | Ward readiness for a run |
| GET | `/v1/actions` | K | per run | Prioritised action list with component weights |
| GET | `/v1/alerts` | KS `read:agency` | short | Alert list (filters: city, severity, status, window) |
| GET | `/v1/alerts/{alert_id}` | KS `read:agency` | short | Alert detail + delivery and acknowledgement status |
| GET | `/v1/alerts/{alert_id}/cap` | KS `read:agency` | short | CAP 1.2 XML rendering |
| POST | `/v1/alerts/{alert_id}/ack` | KS `notify` | — | Acknowledge (responder flow) |
| POST | `/v1/alerts/evaluate` | KS `write:operator` | — | Re-evaluate alert policy for a run (queued) |
| POST | `/v1/subscriptions` | K | — | Create a subscription with consent (citizen/agency) |
| DELETE | `/v1/subscriptions/{id}` | K | — | Withdraw consent and stop delivery |
| POST | `/v1/webhooks/test` | KS `admin` | — | Fire a test webhook payload |
| GET | `/v1/sources/health` | K | 60 s | Per-source freshness and failure counters |
| GET | `/v1/metrics/model` | K | 5 min | Model metadata and evaluation metrics block |
| POST | `/v1/train` | KS `admin` | — | Queue retraining (legacy `/train` alias) |
| GET | `/v1/predict` | K | short | Point prediction with enrichment (single cell) |
| POST | `/v1/predict/bulk` | K | short | Bulk point prediction, capped and validated |
| GET | `/v1/nowcast` | K | short | Nowcast with a declared response model |
| GET | `/v1/openapi.json`, `/docs`, `/redoc` | A | — | Contract surfaces |

### 2.1 Deprecation mapping (legacy → new)

| Legacy path | Status | Replacement | Notes |
|---|---|---|---|
| `/health` | deprecated alias | `/v1/health` + `/v1/ready` | Legacy always returned `healthy`; the alias now returns the real status |
| `/predict` | deprecated alias | `/v1/predict` | Alias keeps the old body but now enriches; the response gains provenance |
| `/predict/bulk` | deprecated alias | `/v1/predict/bulk` | Cap raised only with a key |
| `/nowcast` | deprecated alias | `/v1/nowcast` | Now schema-declared |
| `/hotspots` | deprecated alias | `/v1/runs`, `/v1/layers/hotspots` | Old shape retained; **synthetic generation removed**, so numbers will change — this is the fix, not a regression, and must be explained in the release note |
| `/wards/readiness` | deprecated alias | `/v1/wards/readiness` | Old shape retained with real inputs |
| `/data/ingest` | deprecated alias | `/v1/runs` (scan) or `/v1/admin/ingest` | Now authenticated |
| `/data/summary` | deprecated alias | `/v1/sources/health` | Richer and honest |
| `/email/config` | deprecated alias | `/v1/sources/health` + `/v1/alerts` | Configuration reporting folded in |
| `/email/ward-alert`, `/email/hotspot-alert`, `/email/nowcast-alert` | **deprecated, restricted** | `/v1/alerts/evaluate` + `/v1/alerts` | Now authenticated; recipients must be registered subscriptions or an allowlisted group (fixes the open-relay finding) |
| `/train`, `/train/status` | deprecated alias | `/v1/train`, `/v1/metrics/model` | Now authenticated |

---

## 3. Detailed specifications for the new surface

### 3.1 `POST /v1/runs` — trigger a scan
```json
// request
{
  "city": { "name": "Mumbai", "lat": 19.0760, "lon": 72.8777, "radius_km": 15 },
  "resolution": 8,
  "min_severity": "WATCH",
  "cell_budget": 6000,
  "enrich": true,
  "notify": false
}
```
```json
// 202 Accepted
{
  "run_id": "run_2026-09-21T09:15Z_mumbai",
  "status": "queued",
  "estimated_cells": 2137,
  "cell_budget": 6000,
  "poll": "/v1/runs/run_2026-09-21T09:15Z_mumbai"
}
```
Notes: queued by default; `cell_budget` above the configured maximum is rejected (`budget_exceeded`), not clamped silently. `notify: true` enqueues alert evaluation after the run completes.

### 3.2 `GET /v1/runs/{run_id}` — run metadata
```json
{
  "run_id": "run_2026-09-21T09:15Z_mumbai",
  "city": "Mumbai", "resolution": 8,
  "status": "completed",
  "started_at": "2026-09-21T09:15:02Z",
  "finished_at": "2026-09-21T09:16:12Z",
  "cells_scanned": 2137, "cells_excluded": 12,
  "threshold": 0.5,
  "counts": { "ADVISORY": 210, "WATCH": 96, "WARNING": 31, "EMERGENCY": 4 },
  "hotspots": 27,
  "previous_run_id": "run_2026-09-21T09:00Z_mumbai",
  "changed_cells": 143,
  "layers": ["cells", "hotspots", "wards"],
  "legend": { "probability": [0,0.2,0.4,0.65,0.85,1.0], "depth_m": [0,0.1,0.2,0.5,1.0] },
  "provenance": { "...": "§1.1 block" }
}
```

### 3.3 `GET /v1/layers/{layer}` — GeoJSON
`layer` ∈ `cells | hotspots | wards | facilities | shelters | pumps | roads`.

Query: `bbox=minLon,minLat,maxLon,maxLat` (required for `cells`), `run_id` (default: latest), `min_severity`, `limit`, `simplify` (0–1 tolerance in metres), `fields`.

```json
{
  "type": "FeatureCollection",
  "run_id": "run_2026-09-21T09:15Z_mumbai",
  "as_of": "2026-09-21T09:15:00Z",
  "layer": "hotspots",
  "count": 27,
  "truncated": false,
  "provenance": { "...": "§1.1 block" },
  "features": [
    {
      "type": "Feature",
      "id": "hs_9f2a41",
      "geometry": { "type": "Polygon", "coordinates": [[[72.87,19.05],[72.88,19.05],[72.88,19.06],[72.87,19.05]]] },
      "properties": {
        "hotspot_id": "hs_9f2a41",
        "severity": "WARNING",
        "cell_count": 14, "area_km2": 10.36,
        "max_probability": 0.91, "mean_probability": 0.77,
        "max_depth_cm": 62, "dominant_driver": "drainage_deficit",
        "lifecycle": "intensifying",
        "first_seen": "2026-09-21T07:45:00Z",
        "last_seen": "2026-09-21T09:15:00Z",
        "ward_id": "ward_mum_014",
        "exposed_population": 3120,
        "facilities_inside": 2
      }
    }
  ]
}
```

### 3.4 `GET /v1/tiles/{layer}/{run_id}/{z}/{x}/{y}.mvt`
- Immutable per run. Returns `200` with `Content-Type: application/vnd.mapbox-vector-tile`, `ETag: "run_id-layer-z-x-y"`, `Cache-Control: public, max-age=86400, immutable`.
- Returns `204 No Content` for a tile with no features in that layer (a positive signal that the tile was computed and is empty — better than a `404` the client logs as an error).
- Properties are quantised exactly as in §3.3, with `max_probability` as an integer in `0–100` inside tiles to save bytes.

### 3.5 `GET /v1/wards` and `GET /v1/wards/readiness`
```json
// GET /v1/wards?city=mumbai
{
  "city": "mumbai",
  "provenance": "h3_agglomerated",
  "source": "H3 res-8 agglomeration (no municipal boundary dataset configured)",
  "count": 22,
  "wards": [
    {
      "ward_id": "ward_mum_014",
      "name": "Zone 14 (H3)",
      "name_is_official": false,
      "area_km2": 6.31,
      "population": 48200,
      "bbox": [72.85, 19.03, 72.90, 19.08],
      "geometry": { "type": "Polygon", "coordinates": [["..."]] }
    }
  ]
}
```
```json
// GET /v1/wards/readiness?city=mumbai&run_id=run_2026-09-21T09:15Z_mumbai
{
  "run_id": "run_2026-09-21T09:15Z_mumbai",
  "as_of": "2026-09-21T09:15:00Z",
  "wards": [
    {
      "ward_id": "ward_mum_014",
      "name": "Zone 14 (H3)",
      "readiness_grade": "D",
      "readiness_description": "High – Immediate mobilisation required",
      "risk_score": 72.4,
      "flood_probability_area_weighted": 0.68,
      "inundation_risk_score": 68.0,
      "drainage_stress_score": 79.1,
      "infrastructure_exposure_score": 66.2,
      "component_weights": { "inundation": 0.45, "drainage_stress": 0.35, "exposure": 0.20 },
      "hotspots": {
        "count": 4,
        "worst_severity": "WARNING",
        "max_depth_cm": 62,
        "ids": ["hs_9f2a41", "hs_1c77b0"]
      },
      "recommended_actions": ["Clear all major drains and culverts", "Deploy pumps and HRD team"],
      "pre_position_resources": ["5× portable pumps (1500 L/min)", "2 HRD teams"],
      "population_exposed": 3120,
      "geometry": { "type": "Polygon", "coordinates": [["..."]] }
    }
  ]
}
```

### 3.6 `GET /v1/actions` — the priority queue
```json
{
  "run_id": "run_2026-09-21T09:15Z_mumbai",
  "weights": { "severity": 0.35, "exposed_population": 0.30, "criticality": 0.20, "accessibility": 0.15 },
  "items": [
    {
      "rank": 1,
      "target_type": "hotspot",
      "target_id": "hs_9f2a41",
      "ward_id": "ward_mum_014",
      "severity": "WARNING",
      "score": 88.2,
      "components": { "severity": 0.91, "exposed_population": 0.78, "criticality": 0.90, "accessibility": 0.60 },
      "rationale": "Highest severity in the city with two hospitals inside and one degraded approach road.",
      "facilities_inside": ["hospital:mum_gen_hosp_02", "school:mum_sch_118"],
      "recommended_action": "Deploy 4 pumps and pre-position one team; verify road access via the northern approach.",
      "map_deep_link": "/console?city=mumbai&run=run_2026-09-21T09:15Z_mumbai&focus=hs_9f2a41"
    }
  ]
}
```
Every component is exposed with its weight so the ranking is explainable (REQ-ACT-02) — and so a jury question about "why is this first?" has a one-line answer on screen.

### 3.7 Alerts and CAP export
```json
// GET /v1/alerts?city=mumbai&status=created&severity=WARNING
{
  "count": 3,
  "alerts": [
    {
      "alert_id": "alr_7d31c0",
      "created_at": "2026-09-21T09:16:20Z",
      "hazard": "urban_flood",
      "severity": "WARNING",
      "urgency": "immediate",
      "certainty": "likely",
      "audiences": ["responder", "ward_officer", "citizen"],
      "valid_from": "2026-09-21T09:16:20Z",
      "valid_to": "2026-09-21T11:16:20Z",
      "area": {
        "label": "Zone 14 (H3), Mumbai",
        "hotspot_id": "hs_9f2a41",
        "ward_id": "ward_mum_014",
        "cells": ["8928308280fffff"],
        "geometry": { "type": "Polygon", "coordinates": [["..."]] }
      },
      "instruction": "Move to higher ground now; avoid the northern underpass.",
      "reason": ["rainfall_24h above 100 mm", "drainage capacity below 45%", "soil saturated"],
      "source_run_id": "run_2026-09-21T09:15Z_mumbai",
      "status": "created",
      "suppression_key": "sha256:ward_mum_014|WARNING|urban_flood",
      "deliveries": { "email": { "scheduled": 42, "sent": 41, "failed": 1 }, "webhook": { "sent": 2 } },
      "acknowledged_by": ["responder:sdrf_unit_3"]
    }
  ]
}
```
`GET /v1/alerts/{alert_id}/cap` returns `application/cap+xml`:
```xml
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>alr_7d31c0</identifier>
  <sender>floodshield@example.org</sender>
  <sent>2026-09-21T09:16:20Z</sent>
  <status>Actual</status>
  <msgType>Alert</msgType>
  <scope>Public</scope>
  <info>
    <category>Met</category>
    <event>Urban Flood Warning</event>
    <urgency>Immediate</urgency>
    <severity>Severe</severity>
    <certainty>Likely</certainty>
    <effective>2026-09-21T09:16:20Z</effective>
    <expires>2026-09-21T11:16:20Z</expires>
    <headline>Urban flood warning — Zone 14 (H3), Mumbai</headline>
    <instruction>Move to higher ground now; avoid the northern underpass.</instruction>
    <area>
      <areaDesc>Zone 14 (H3), Mumbai</areaDesc>
      <polygon>19.05,72.87 19.05,72.88 19.06,72.88 19.06,72.87 19.05,72.87</polygon>
    </area>
  </info>
</alert>
```
### 3.8 `POST /v1/subscriptions`
```json
// request
{
  "channel": "email",
  "contact": "resident@example.com",
  "audience": "citizen",
  "areas": { "h3_cells": ["8928308280fffff"] },
  "language": "en",
  "severity_floor": "WATCH",
  "consent": { "granted": true, "purpose": "urban_flood_alerts_for_selected_cells" }
}
```
```json
// 201 Created
{
  "subscription_id": "sub_3a91",
  "status": "active",
  "consent_recorded_at": "2026-09-21T09:40:00Z",
  "withdraw": "/v1/subscriptions/sub_3a91"
}
```
Consent is recorded server-side with purpose and timestamp (dossier §8.1, NFR-PRV-01), and the response deliberately surfaces the withdrawal URL — a subscription flow without a visible exit is exactly what a data-protection reviewer looks for.

### 3.9 `GET /v1/predict` — point prediction with enrichment
```
GET /v1/predict?lat=19.0760&lon=72.8777&enrich=true&explain=true
```
```json
{
  "h3": "8928308280fffff",
  "resolution": 8,
  "latitude": 19.0760, "longitude": 72.8777,
  "flood_probability": 0.87,
  "flood_risk_level": "CRITICAL",
  "severity_band": "WARNING",
  "estimated_inundation_depth_m": 0.42,
  "confidence": 0.92,
  "drivers": [
    { "factor": "rainfall_24h",     "value": 118.4, "unit": "mm",    "contribution": 0.31 },
    { "factor": "drainage_deficit", "value": 0.55,  "unit": "ratio", "contribution": 0.24 },
    { "factor": "soil_saturation",  "value": 0.78,  "unit": "ratio", "contribution": 0.19 },
    { "factor": "low_elevation",    "value": 6.2,   "unit": "m",     "contribution": 0.12 }
  ],
  "enriched_fields": ["elevation_m", "slope_degrees", "soil_type_code", "drainage_capacity_pct", "rainfall_24h_mm"],
  "instruction": "Move to higher ground now; avoid the northern underpass.",
  "recommendation": "WARNING: deploy pumps, open shelters, monitor the priority queue.",
  "provenance": { "...": "§1.1 block" }
}
```
Notes: `drivers` supersedes the previous `contributing_factors` map, because a bare map of 0–1 weights could not be audited or explained. When `enrich=false` and required covariates are absent, the system returns `missing_covariates` rather than silently defaulting (REQ-ING-02, AC-04).

---

## 4. Error model

One shape, everywhere:
```json
{
  "error": {
    "code": "budget_exceeded",
    "message": "Requested 41200 cells; the limit is 6000.",
    "details": { "requested_cells": 41200, "cell_budget": 6000, "suggested": "reduce radius_km or increase resolution" }
  },
  "request_id": "req_01J8..."
}
```

| HTTP | `error.code` | Meaning |
|---|---|---|
| 400 | `validation_error` | Field-level validation failure (details lists the fields) |
| 400 | `budget_exceeded` | Scan exceeds the cell budget |
| 400 | `bbox_required` | Layer needs a bbox |
| 400 | `bbox_too_large` | Bbox exceeds the allowed area for GeoJSON (use tiles) |
| 401 | `unauthenticated` | Missing or invalid key |
| 403 | `insufficient_scope` | Key lacks the required scope |
| 404 | `run_not_found` | Unknown run id (details includes the latest run id) |
| 404 | `cell_not_found` | Unknown H3 index, or no score in the requested run |
| 409 | `idempotency_conflict` | Same idempotency key, different payload |
| 422 | `missing_covariates` | Enrichment disabled and required inputs absent |
| 429 | `rate_limited` | Quota exceeded (`details.retry_after_seconds`) |
| 503 | `upstream_unavailable` | A required source failed while enrichment is strict |
| 503 | `model_unavailable` | No verified model artefact |
| 500 | `internal_error` | Unexpected; `request_id` is the support handle |

---

## 5. Webhook contract

Subscribing agencies receive signed POSTs.

```http
POST https://agency.example.org/floodshield
Content-Type: application/json
X-FloodShield-Event: alert.created
X-FloodShield-Delivery: 8f31c0a5-...
X-FloodShield-Timestamp: 2026-09-21T09:16:21Z
X-FloodShield-Signature: sha256=<hmac of timestamp + "." + raw body>
```

```json
{
  "event": "alert.created",
  "delivered_at": "2026-09-21T09:16:21Z",
  "alert": { "...": "the alert object from §3.7" },
  "cap_url": "https://api.example.org/v1/alerts/alr_7d31c0/cap"
}
```

Events: `alert.created`, `alert.escalated`, `alert.acknowledged`, `run.completed`, `run.failed`, `source.degraded`.

Receiver contract: return `2xx` within 10 s. A non-2xx response or a timeout triggers the retry/backoff policy (REQ-ALT-08) and eventually the dead-letter state. Signatures let the receiver reject forged or replayed deliveries — which is what makes this integration credible to a municipal security review.

---

## 6. Versioning and deprecation policy

1. **Additive changes** (new fields, new endpoints) ship without a version bump; clients must ignore unknown fields.
2. **Breaking changes** require `/v2`, with `/v1` supported for at least one full release cycle and `Deprecation` plus `Sunset` headers on affected responses.
3. **Legacy unversioned paths** are treated as `/v1` aliases and removed only after the deprecation window; removal is announced with the mapping table (§2.1).
4. **Field removals** require an ADR justifying why the field cannot be retained.
5. The release note for the first version of this programme **must** state that hotspot and ward numbers change because synthetic generation was removed (`05 §8`, M6). Without that sentence the change looks like a regression to anyone comparing old and new outputs. This is engineering honesty *and* pitch material — it demonstrates that the team found and fixed its own weakness.

---

## 7. Contract tests

Each `M` requirement in `04` maps to at least one test below. Contract tests run against the app in-process (FastAPI `TestClient`) and, for the demo path, against the deployed instance.

| Test | Covers | Asserts |
|---|---|---|
| `test_openapi_complete` | REQ-API-04 | Every route has a response model; no unresolved `$ref` in the schema |
| `test_versioned_and_alias_paths` | REQ-API-01 | `/v1/x` and legacy `/x` both respond; legacy carries a deprecation marker |
| `test_error_shape_uniform` | REQ-API-03 | All errors match §4, including `request_id` |
| `test_scan_bounds_rejected` | REQ-SCN-06/07, AC-03 | Out-of-range parameters rejected before computation |
| `test_prediction_enrichment` | REQ-ING-01, AC-04 | Enrichment fills and reports fields; strict mode errors instead of defaulting |
| `test_hotspot_identity_stable` | REQ-SCN-02, AC-02 | Two scans with different centres yield identical H3 ids for the same ground |
| `test_live_inputs_change_output` | REQ-SCN-01, AC-01 | Modified rainfall changes the hotspot set; per-source timestamps present |
| `test_ward_geometry_and_provenance` | REQ-WRD-01/02, AC-05 | Provenance recorded; no official-sounding invented names |
| `test_ward_hotspot_join` | REQ-WRD-08, AC-06 | Hotspot counts match a spatial-intersection recomputation |
| `test_layer_geojson_valid` | REQ-MAP-01/02, AC-07 | Valid FeatureCollection; run id and `as_of` echoed |
| `test_tile_headers_and_immutability` | REQ-MAP-03/04 | MVT content type; stable ETag per run; `204` for empty tiles |
| `test_alert_not_open_relay` | REQ-ALT-05, AC-09 | Arbitrary recipient from an unauthenticated call rejected and logged |
| `test_suppression_window` | REQ-ALT-06, AC-10 | Duplicate suppressed; suppression recorded |
| `test_delivery_audit_and_retry` | REQ-ALT-07/08 | Attempts recorded; failures retried then dead-lettered |
| `test_cap_conformance` | REQ-ALT-03, AC-11 | CAP XML validates against the CAP 1.2 element structure |
| `test_no_event_loop_block` | REQ-ALT-10, AC-13 | A hanging SMTP stub does not delay concurrent reads |
| `test_claims_discipline` | REQ-QLT-01/04/05, AC-14 | No accuracy claim in any response; `hotspots_mapped` equals the DB count; `validation_scope` present |
| `test_health_and_ready_degrade` | REQ-DAT-05, AC-15 | Health reports dependency failures; `/ready` fails when the model is unverified |




