# 02 — Current-State Audit (evidence-based)

Every finding was read directly out of this repository. Line references match this working copy. Severity: **S1** blocks demonstration/credibility · **S2** correctness or security defect · **S3** quality/scale/ops debt.

Inventory: 11 Python modules (~2,100 lines), no `tests/`, no CI, no migrations, no static/vector assets, no frontend, no spatial output format anywhere, no auth, no rate limiting.

---

## 1. Focus area A — Wards

### A-1 `india_wards.csv` path is unreachable — **S1**
`services/predictor.py:412`
```python
csv_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "india_wards.csv")
```
`__file__` is `<repo>/services/`, so three `..` steps resolve to the **parent of the repository root** (`…\Downloads\india_wards.csv`). That path can never exist. The ward-name enrichment branch is dead code, yet the README presents it as a known mitigation. *Fix:* package the dataset inside `data/wards/` or load boundaries into PostGIS.

### A-2 Ward "geometry" is a 7×7 lattice, not boundaries — **S1**
`services/predictor.py:392–439` — `ward_spacing_km = max(2.0, radius_km / 5)`, then `for i in range(-3, 4): for j in range(-3, 4)` filtered by `dist <= radius_km`. At the documented default `radius_km=15` this yields at most **49 candidate centres**, ~45 passing the radius test. Consequences:
- No ward **polygon** ⇒ no ward area, no population overlay, no hotspot-to-ward spatial join, no per-ward map rendering.
- Ward identity (`WARD-001…`) is an artefact of iteration order, so the same city yields different IDs when the radius changes. Nothing is stable across calls.
- Centres sit on a lat/lon degree lattice, not on settlement patterns, so they can land in rivers or offshore.

### A-3 Ward features are synthetic — **S1**
`services/predictor.py:327–351` builds each ward's `PredictionRequest` from `spatial_pattern = sin(wlat*50)·cos(wlon*50)`:
```python
rain_base = 100 + spatial_pattern * 40
elev      = max(1.0, 12 + spatial_pattern * 8 + dist_from_center * 0.5)
```
Rainfall, elevation, imperviousness, drainage capacity, soil moisture, drain condition and historical flood counts all derive from that pattern. **No ward-level call reaches `DataCollector`**, which already implements `_fetch_dem`, `_fetch_soil_properties`, `_fetch_drainage_infra` and weather retrieval.

### A-4 Sub-scores and hotspot counts are fabricated — **S1**
`services/predictor.py:355–381`: `hotspot_count_in_ward = int(pred.flood_probability * 20)`; `infra_exposure = min(100, population_density/200 + building_density_pct)`. `_estimate_hotspot_count` (`services/trainer.py:180–185`) is `3.14159 * radius_km**2 * 2.5` — pure arithmetic. This is the origin of the "2,500+ hotspots" headline: a **radius-derived constant, not a measurement**.

### A-5 Readiness scorecard is a fixed weight blend — **S2**
`risk_score = 0.45·inundation + 0.35·drainage_health + 0.20·infra_exposure` (predictor.py:361–363), `drainage_health = 100 − drainage_capacity_pct · drain_condition_score`. Both drainage terms come from the synthetic pattern (A-3), so the A–F grade is effectively a function of coordinates. The grade semantics (`models/schemas.py:139–145`) are sound and should be kept; only the inputs need replacing.

### A-6 Ward response omits geometry and provenance — **S2**
`WardReadinessResponse` (`models/schemas.py:191–205`) has no geometry, no `bbox`, no `data_sources`, no `as_of` and no `population`. A consumer cannot render or validate a ward. There is also no endpoint to list a city's wards independently of computing readiness.

---

## 2. Focus area B — Micro-hotspots

### B-1 Grid geometry is correct; grid *contents* are fabricated — **S1**
`services/predictor.py:267–309` — `_build_grid_requests` correctly computes cell centres in metres-aware degrees (`delta_lat = grid_size_km/111.32`, `delta_lon = grid_size_km/(111.32·cos(lat))`) and correctly filters by distance. It then fabricates every feature:
```python
spatial_pattern = math.sin(clat * 100) * math.cos(clon * 100)
micro_pattern   = math.sin(clat * 500) * math.cos(clon * 500)
elev            = 15.0 + spatial_pattern*10.0 + micro_pattern*3.0 - dist*0.5
rainfall_24h_mm = 120.0 * rain_mult + max(0.0, micro_pattern)*20.0
```
Elevation, rainfall, slope, flow accumulation, imperviousness, drainage capacity, soil moisture and flood history are all functions of the cell's own coordinates. The scan therefore cannot respond to a real storm: **the same city scanned in a monsoon and in a dry spell returns identical hotspots.** `min_risk` filters a number never derived from live data. Any question of the form "show it changing with live rainfall" or "why is this cell high risk?" exposes the gap. This is the highest-priority engineering fix in the programme.

### B-2 No hotspot object, only cells — **S2**
`scan_hotspots` (predictor.py:219–265) returns a flat sorted `List[HotspotCell]`: no clustering into named hotspot areas, no severity class beyond the probability band, no lifecycle (`new`/`persisting`/`intensifying`/`clearing`), no first-seen/last-seen, no persistence. `HotspotCell` (`schemas.py:170–178`) carries `area_km2` (the constant `grid_size_km²`) but no identifier that survives a change of grid size or scan centre.

### B-3 Cell identity is unstable — **S2**
`predictor.py:249` — `cell_id=f"{req.latitude:.4f}_{req.longitude:.4f}"`. The ID is a formatting of the query, not a property of the world. Re-scanning from a different centre renames every cell, breaking alert dedupe ("is this the hotspot we alerted 40 minutes ago?") and blocking trend analysis.

### B-4 Unbounded computation — **S2 (availability)**
`main.py:212–217` declares `radius_km` and `grid_size_km` as `Query(..., description=...)` with **no `ge`/`le` bounds**. `_build_grid_requests` sizes its loop as `max_steps = int(radius_km/grid_size_km)+1`, so `grid_size_km=0.001&radius_km=100` requests on the order of 10<sup>10</sup> cells — an unauthenticated denial of service. The README documents 0.25–2 km; the API does not enforce it.

### B-5 Response size is unbounded — **S2**
`MicroHotspotResponse` returns *every* qualifying cell inline (main.py:232–240). A 10 km radius at 250 m resolution is ~5,000 cells and a multi-megabyte JSON — no pagination, no clustering, no coordinate precision reduction, no tiled alternative.

### B-6 Hotspots are not persisted or joined to anything — **S2**
A scan writes nothing to the database. So `/health`'s `hotspots_mapped` cannot be a real count (A-4), and "which wards contain the worst hotspots" — the most useful municipal question — cannot be answered.

---

## 3. Focus area C — Map integration

### C-1 No spatial output format exists — **S1**
The full route inventory (main.py:134–392) contains **zero** GeoJSON, XYZ/WMTS tile, bbox or vector-tile endpoints, and `models/schemas.py` contains no `geometry`, `bbox` or `geojson` field. The product is API-only; nothing can be drawn.

### C-2 No static geospatial assets are vendored — **S1**
No boundary polygons, no road-network extract, no basemap style, no tile package, no raster (DEM / flood-depth) assets. Every rendering capability would depend on live third-party calls — slow, and a terms-of-use exposure (C-3).

### C-3 Base-map strategy is unaddressed, and the obvious default is prohibited at production scale — **S2 (legal/operational)**
`tile.openstreetmap.org` must not be used for anything resembling a production or funding-seeking service. The OSMF Tile Usage Policy requires a contactable `User-Agent`, correct attribution, client caching of ≥7 days, forbids prefetch/offline bulk download, states availability is *best-effort with no SLA*, and reserves the right to block access without notice — singling out commercial and donation-seeking services as especially exposed. The repo has no map yet, so this risk has not been incurred; the decision must be made deliberately rather than by accident.

### C-4 Reverse geocoding hits public Nominatim per request — **S2 (operational)**
`predictor.py:399–409` calls `https://nominatim.openstreetmap.org/reverse` with `User-Agent: "BioSentinelX-App"` (no contact address) and a 5 s timeout, inside the ward path, on **every** call, uncached and unthrottled. OSMF identification requirements expect a UA naming the app *and* giving a contact; the public Nominatim instance additionally requires caching and roughly ≤1 request/second. Repeated city-wide ward computation will breach this.

### C-5 No client application exists — **S1 (for demonstration)**
No `frontend/` or `static/` directory, no build config, and the FastAPI app mounts no static files. With scoring at 10% for *UX & Design* and 5% for *Presentation & Demo* — inside an evaluation where innovation and technical implementation carry 50% — the absence of any visual surface is the largest single scoring exposure.

---

## 4. Focus area D — Email & alerting

### D-1 `/email/*` endpoints are an unauthenticated open relay — **S2 (security, high)**
`main.py:320–392` accepts `recipients: List[str]` straight from the request body and passes it to `send_ward_alert` / `send_hotspot_alert` / `send_nowcast_alert`, which forward it to `_send_email(..., recipients)` where `to_addrs = recipients or ALERT_RECIPIENTS` (`email_service.py:254`). There is no authentication, no per-identity allowlist, no rate limit and no abuse logging. Anyone who can reach the deployed service can send arbitrary HTML email from the project's authenticated sender to arbitrary third parties. `send_ward_alert` also sends even when **no** critical wards exist, provided recipients are supplied (`email_service.py:300–302`) — so the endpoint is a general-purpose mailer, not an alert-only path.

### D-2 Blocking SMTP runs inside the async event loop — **S2**
`email_service.py:262–288` uses blocking `smtplib` + `ssl`, and the route handlers call it **directly** from async functions (`main.py:336`, `364`, `387`). A STARTTLS handshake plus login typically costs 1–3 s and can hang far longer on a slow DNS/TLS retry, during which the whole event loop is stalled: no other request is served, no scheduler job runs, and the Docker healthcheck can begin failing. Dispatch must move off-loop (executor / background task / queue).

### D-3 No delivery record, retry, or acknowledgement — **S2**
`_send_email` returns a plain dict (`sent`/`skipped`/`error`) that is handed back to the HTTP caller and then forgotten. Nothing is persisted: no outbox, no attempt count, no provider message ID, no retry with backoff, no dead-letter state, no recipient acknowledgement (`ack`) — and no way to answer "was the D-grade ward alert actually delivered?".

### D-4 No dedupe, throttle, escalation or quiet hours — **S2**
A repeated or scheduled call re-sends the same alert. There is no state keyed on (ward/cell, severity) to suppress duplicates inside a window, no severity-gated escalation, no quiet-hours/digest policy and no per-recipient hourly cap. These are exactly the mechanisms that prevent *cry-wolf* fatigue — a documented failure mode of flood warning systems.

### D-5 Templates are single-channel and unlocalised — **S3**
The three HTML builders produce inline-styled markup only: no shared template engine, no plain-text alternative, **English only**, no per-role variants (citizen / responder / municipality) and no explicit actionable instruction line. India's warning audience is multilingual, and the EW4All position is that alerts must be timely, accurate and *actionable* on channels people trust and can access.

### D-6 MIME and deliverability hygiene is incomplete — **S3**
`_send_email` builds `MIMEMultipart("alternative")` but attaches **only** a `text/html` part, and sets no `Date`, `Message-ID`, `List-Unsubscribe` or `Auto-Submitted: auto-generated` headers. Gmail's SMTP additionally requires the envelope sender to match the authenticated account; `SMTP_FROM` defaults to `SMTP_USER` (`email_service.py:35`) but nothing enforces that if an operator sets only `SMTP_FROM`.

### D-7 No standards-compliant alert object — **S2 (strategic)**
Nothing produces or models a **CAP (Common Alerting Protocol)** message, and there is no `Alert` domain object at all — alerts exist only as side effects of three HTML builders. CAP 1.2 (`ITU-T X.1303 bis`) is the international standard that lets one alert travel across many channels and platforms, and India's own public warning system (SACHET) is CAP-based. Without a CAP-shaped internal model the platform cannot be aggregated by, or interoperate with, the authorities it wants to serve.

### D-8 Email is the only channel — **S2 (product)**
`requirements.txt` contains no SMS, WhatsApp, push or webhook provider. Email is the weakest channel for field responders, for low-income residents, and during the power/connectivity failures that accompany urban flooding. Meta's per-message model (effective 1 July 2025) makes **utility templates free inside an open customer-service window** with volume-tiered utility rates — a deliberate channel-mix decision is required rather than an email-only default.

---

## 5. Cross-cutting findings

| ID | Finding | Evidence | Sev |
|---|---|---|---|
| X-1 | **No authentication or authorisation on any endpoint.** `/train`, `/data/ingest` and `/email/*` are all open; triggering a 10-year ingestion plus ensemble retraining needs no credential. | main.py (all routes) | S2 |
| X-2 | **No rate limiting, no quotas, no request-size caps** — which is what turns B-4 and D-1 into exploitable issues. | main.py | S2 |
| X-3 | **CORS is `allow_origins=["*"]` with `allow_credentials=True`** — an invalid combination for credentialed browser requests and a needlessly permissive default. | main.py:124–130 | S3 |
| X-4 | **No API versioning.** Every route is unversioned (`/predict`, `/wards/readiness`), so no contract can evolve without breaking integrators. | main.py | S2 |
| X-5 | **Scheduler duplicate-execution risk.** `Procfile` starts `--workers 2` while the `Dockerfile` uses `--workers 1` (and `render.yaml` relies on the image). With 2 workers **both** run APScheduler, so nightly retraining and hourly sync execute twice concurrently and each worker keeps its own model singleton. | Procfile:1, Dockerfile:45 | S2 |
| X-6 | **Model artefacts live on the container filesystem.** `MODEL_DIR = <pkg>/../saved_models` (`models/flood_model.py:59`) and `_save()` writes pickles there. `render.yaml` mounts no disk, so every redeploy retrains from scratch, and startup training competes with health checks. | flood_model.py:59, 344–351; render.yaml | S2 |
| X-7 | **Unverified model loading.** A `pickle.load` failure only logs a warning and substitutes an empty `ModelMetadata()` — no integrity check (hash / feature-count / schema) and no provenance stamp. Pickle is also unsafe to load from any artefact store a third party can write to. | flood_model.py:353–369 | S2 |
| X-8 | **`/health` always reports `"healthy"`** and checks no dependency (DB, scheduler, model age, upstream API reachability), so it cannot serve as a readiness/liveness signal. | main.py:134–145 | S3 |
| X-9 | **No `tests/` directory and no CI**, although the README reports "114 passed, 0 failed". The suite is not in the repository, so it cannot be run, re-verified or shown to a jury. | repo tree | S1 |
| X-10 | **Training metrics are exposed without a held-out split**, and `TrainingStatusResponse` carries no precision/recall/confusion matrix/threshold or calibration information. | trainer.py:107–118; schemas.py:208–218 | S2 |
| X-11 | **`init_db()` creates only two tables.** `database/models.py` also defines `FloodEvent`, but `init_db` imports only `ObservationRecord` and `LocationCache` (`database/db.py:38–42`), so `flood_events` is never created. | db.py:38–42 | S3 |
| X-12 | **No migrations, no spatial indexes, no PostGIS.** Geo lookups are `between(lat±0.1)` range scans; there is no geometry column, no GiST index and no polygon storage. | data_collector.py:87–92 | S2 |
| X-13 | **Default-feature predictions are silently wrong.** `PredictionRequest` defaults every covariate (e.g. `elevation_m=0.0`, `soil_moisture_pct=30.0`, `drainage_capacity_pct=70.0`). A caller sending only `{lat, lon}` — exactly the README example — receives a prediction for *sea level with ideal drainage*, not for that location. Nothing auto-enriches omitted fields from the collector. | schemas.py:39–115; README example | S1 |
| X-14 | **`engineer_training_features` can silently emit zero rows.** `trainer.py:85–88` masks on `feature_df.notna().all(axis=1)` after selecting `FEATURE_COLUMNS`, so any gap in a rare column drops every row and surfaces only as a training exception. | trainer.py:79–100 | S3 |
| X-15 | **Ingestion pulls 10 years of hourly data in one uncached, unpaginated, un-retried call per source** (30 s timeout), then persists row-by-row rather than in a bulk upsert. | data_collector.py:45–82 | S3 |

---

## 6. Priority order (what to fix first, and why)

| Rank | Item | Rationale | Effort |
|---|---|---|---|
| 1 | **B-1** real feature assembly for hotspot cells | The one finding that lets a judge invalidate the product with a single question; also unlocks B-2/B-3 and every map layer | M |
| 2 | **X-13** auto-enrichment of omitted prediction fields | Same root cause as B-1, fixes `/predict` credibility, reuses the same cache | S |
| 3 | **C-1 + C-5** GeoJSON endpoints and a first client map | Largest scoring exposure (UX 10% + demo 5%) and makes spots/wards legible | M |
| 4 | **A-1/A-2** real ward boundaries, or an explicit, labelled H3 fallback | Municipal credibility; unlocks hotspot↔ward joins and per-ward alerts | M |
| 5 | **D-1** close the open relay, **D-2** move SMTP off-loop | Security and stability; a live open mail relay on a public URL is indefensible if discovered | S |
| 6 | **D-7** internal `Alert` object with CAP export | Strategic differentiator: interoperate with national warning systems instead of competing | M |
| 7 | **X-1/X-2/X-4** auth, quotas, `/v1` versioning | Makes the API presentable as a platform rather than a demo script | S |
| 8 | **X-9** bring the test suite into the repo and wire CI | Converts the README claim into a rerunnable artefact and protects everything above | M |
| 9 | **B-4/B-5** bounds and response shaping | Removes a trivially exploitable DoS; makes scans usable over mobile networks | S |
| 10 | **X-5/X-6/X-7** single scheduler, persistent model store, verified load | Deployment correctness in the demo environment | S |

Effort key: **S** ≤ half a day, **M** 1–2 days, **L** > 2 days (one engineer per workstream).

---

## 7. What is genuinely good and must be preserved

A professional audit must state this explicitly, because it determines the build strategy: **do not rewrite the core.**

1. **The ML core is well designed** — RF + XGBoost + LightGBM into a Logistic Regression meta-learner (`StackingClassifier`) with `CalibratedClassifierCV`, a separate depth regressor, and an SCS-based physics blend for depth (`models/flood_model.py:305–339`). Blending ML depth against a physically plausible floor is a genuinely thoughtful touch.
2. **Feature engineering is coherent** — SCS curve numbers by LULC × hydrologic soil group, SCS-CN runoff depth, antecedent precipitation index, drainage stress, terrain vulnerability and a composite risk index, computed consistently for single-row inference and bulk training (`services/feature_engineering.py`).
3. **The data collector is real and async** — five sources fetched concurrently with `asyncio.gather`, synthetic fallbacks on failure, rolling accumulations of 1–72 h and an API index computed at ingest (`services/data_collector.py:59–82, 174–193`). This is the asset that fixes B-1 and X-13.
4. **Operational hygiene many projects lack** — graceful scheduler shutdown, a `_training_lock`, a dedicated single-worker `ThreadPoolExecutor` for training so FastAPI's executor is not starved, capped parallelism to avoid OOM, a multi-stage Docker build running as non-root with a `HEALTHCHECK`, and Render/Railway/Procfile configs.
5. **Schema discipline** — every response is a Pydantic model (except `/nowcast`), so the OpenAPI contract is already largely generated for free.
6. **Honest engineering documentation** — the README's "Important evaluation limitations" section is unusually candid and is a strategic asset, not a liability (see `08-SDLC-DELIVERY-PLAN.md` §Claims).

**Conclusion.** The gap between this repository and a judge-winning product is *not* modelling depth — it is a **four-part wiring and presentation job** (wards, hotspots, map, alerts) plus contract hardening. That is exactly the scope this programme executes.




