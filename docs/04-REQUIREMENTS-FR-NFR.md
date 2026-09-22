# 04 — Requirements Specification (Functional and Non-Functional)

## 0. How to read this document

- Every requirement has an **ID**, a **priority**, and an explicit **verification method**, so it can be tested rather than debated.
- `SHALL` = mandatory · `SHOULD` = strongly recommended · `MAY` = optional.
- **Verification methods:** `T` automated test · `D` live demonstration · `I` inspection of an artefact (code/schema/config) · `A` analysis or measurement.
- **Priorities:** **M** = Must (required for the hackathon demonstration) · **S** = Should (next release) · **C** = Could (roadmap).
- Every **M** requirement traces to a feature (`F-nn` in `03`) and to a task in `08-SDLC-DELIVERY-PLAN.md`.

### Scope
This specification covers the **integration programme**: hazard-enrichment wiring, wards, micro-hotspots, map/tiles, alerts and the platform contract around them. The ML modelling core, feature definitions and ensemble design are **out of scope for change** (see `02 §7`), except where explicitly noted (REQ-QLT-02/03).

### Assumptions and constraints
- Deployment remains a single long-running container (Render/Railway class), because the scheduler, warm model state and background jobs are architectural requirements — the README already reasons this way and the evidence supports it.
- PostgreSQL is the production store for the new geospatial tables; SQLite remains supported for local development, with spatial features degrading to a documented fallback.
- Public third-party access remains free and keyless (Open-Meteo, Open-Meteo Flood/GloFAS, OpenTopoData, SoilGrids, OSM Overpass). Any new keyed dependency requires an ADR.
- The system is a **decision-support** tool; no requirement may imply certified life-safety authority.

---

## 1. Functional requirements

### 1.1 Ingest and enrichment (ING)
| ID | Requirement | Pri | Verify |
|---|---|---|---|
| REQ-ING-01 | When a request omits covariate fields, the system SHALL fetch the missing values from the data collector for that coordinate before inference, and SHALL mark which fields were enriched. | M | T, I |
| REQ-ING-02 | If a required covariate cannot be fetched and no explicit value was supplied, the system SHALL return an explicit error rather than silently substituting a default. | M | T |
| REQ-ING-03 | Static per-cell features (elevation, slope, curvature, flow accumulation, soil, imperviousness proxy, drainage proximity, pump presence, water-body distance) SHALL be cached persistently, keyed by H3 cell id, with a recorded fetch timestamp and source. | M | T, I |
| REQ-ING-04 | Live fields (rainfall accumulations, soil moisture, temperature, humidity, wind, pressure, river discharge and its anomaly) SHALL refresh at least every 60 minutes and SHALL be reused within a 10-minute window without refetching. | M | T, A |
| REQ-ING-05 | Every response containing hazard values SHALL include a provenance block: `data_sources[]` (name, licence, retrieved_at) plus `as_of`, `model_version` and `run_id`. | M | T, I |
| REQ-ING-06 | The system SHOULD ingest IMD district-wise warnings and district rainfall and expose them as read-only context, visually distinguished from our own output. | S | T, D |
| REQ-ING-07 | Ingestion SHALL be resumable and idempotent: repeating an ingestion for the same coordinate and period SHALL NOT duplicate stored observations. | S | T |
| REQ-ING-08 | Ingestion SHALL apply retry with exponential backoff and record per-source failures in a source-health table. | S | T, I |
| REQ-ING-09 | External HTTP calls SHALL carry an identifying `User-Agent` with an application name and a contact address, and geocoding results SHALL be cached. | M | I |

### 1.2 Scanning and micro-hotspots (SCN)
| ID | Requirement | Pri | Verify |
|---|---|---|---|
| REQ-SCN-01 | A scan SHALL build each cell's feature vector from real cached-plus-live data. Coordinate-derived synthetic feature generation SHALL NOT exist in any production code path. | M | T, I |
| REQ-SCN-02 | Each cell SHALL carry an H3 index as its published identifier — default resolution 8 (≈0.74 km²), resolution 9 (≈0.11 km²) selectable for micro-scale passes. | M | T |
| REQ-SCN-03 | Cells meeting the risk threshold SHALL be grouped into **hotspot objects**: contiguous clusters with centroid, cell count, area, worst cell, mean/max probability, mean/max depth, severity band and dominant driver. | M | T |
| REQ-SCN-04 | Each hotspot SHALL carry a lifecycle status (`new`, `persisting`, `intensifying`, `clearing`) computed against the previous run for the same city, plus `first_seen` and `last_seen`. | M | T |
| REQ-SCN-05 | Each scan SHALL be persisted as a run (run id, parameters, input hash, model version, timestamp) with its per-cell results, so any past run can be retrieved. | M | T, I |
| REQ-SCN-06 | The scan API SHALL enforce an explicit maximum cell budget; requests exceeding it SHALL be rejected with a structured error naming the limit and the requested count. | M | T |
| REQ-SCN-07 | `radius_km` and grid/resolution parameters SHALL be validated against declared bounds and rejected at request validation, not inside the computation. | M | T |
| REQ-SCN-08 | Scan responses SHALL support `bbox`, `limit`/`top_n`, `min_severity`, simplified geometry and a `summary_only` mode; the default response SHALL be bounded regardless of city size. | M | T, A |
| REQ-SCN-09 | The system SHALL record hotspot first-observed and last-observed timestamps and expose a hotspot-history endpoint per cell or cluster. | S | T |
| REQ-SCN-10 | The system SHOULD support replaying a historical run (chosen date/time) from stored inputs, for training and review. | S | D |
| REQ-SCN-11 | The system SHOULD report a compound pluvial–fluvial indicator when both urban risk and river-discharge anomaly are elevated. | S | T |
| REQ-SCN-12 | Cells whose centroid falls inside a water body or outside the land mask SHALL be flagged and excluded from action prioritisation by default. | S | T |

### 1.3 Wards (WRD)
| ID | Requirement | Pri | Verify |
|---|---|---|---|
| REQ-WRD-01 | Ward geometry SHALL come from a real source (administrative boundary dataset or a supplied municipal file) and SHALL be stored with its source recorded. | M | I, D |
| REQ-WRD-02 | Where no boundary source exists for an area, the system SHALL generate wards by agglomerating H3 cells into named clusters with valid geometry, and SHALL label their provenance `h3_agglomerated`. | M | T |
| REQ-WRD-03 | Generated or synthetic ward naming SHALL NEVER be presented as an official administrative name. | M | I |
| REQ-WRD-04 | Ward identifiers SHALL be stable for a given boundary set: the same ward returns the same `ward_id` regardless of scan radius. | M | T |
| REQ-WRD-05 | A ward-list endpoint SHALL return wards (id, name, provenance, geometry, area, bbox, population) independently of any readiness computation. | M | T |
| REQ-WRD-06 | Ward readiness SHALL be computed from real per-cell hazard values inside the polygon, aggregated by area (not by sampling ward centres). | M | T |
| REQ-WRD-07 | Ward component scores SHALL be inundation risk, drainage/exposure stress and infrastructure exposure, each traceable to named inputs. | M | T, I |
| REQ-WRD-08 | Ward readiness SHALL include the hotspot join: hotspot count, worst-cell severity, mean/max depth and the list of member hotspots. | M | T |
| REQ-WRD-09 | Ward responses SHALL include geometry or a geometry reference so they can be rendered directly. | M | T |
| REQ-WRD-10 | Ward scoring SHALL be reproducible: identical inputs and model version produce identical scores. | M | T |
| REQ-WRD-11 | Resource pre-positioning SHOULD derive from grade, ward area and exposure rather than a fixed per-grade list. | S | I |

### 1.4 Map, layers and tiles (MAP)
| ID | Requirement | Pri | Verify |
|---|---|---|---|
| REQ-MAP-01 | The system SHALL expose GeoJSON endpoints per layer: `hotspots`, `hotspot_clusters`, `wards`, `cells`, `facilities`, `shelters`, and (where available) `roads` and `pumps`. | M | T, D |
| REQ-MAP-02 | Every layer endpoint SHALL accept a `bbox` and a run selector, and SHALL return the `run_id` and `as_of` used. | M | T |
| REQ-MAP-03 | The system SHALL expose a vector-tile endpoint serving Mapbox Vector Tiles for hazard layers, cacheable per run. | M | T, A |
| REQ-MAP-04 | Tile and layer responses SHALL carry correct `Cache-Control`/`ETag` headers for the run and SHALL NOT send no-cache directives by default. | M | I |
| REQ-MAP-05 | A web client SHALL render the hazard layers on a self-hosted or provider-licensed basemap requiring no paid API key to run the demo. | M | D |
| REQ-MAP-06 | The client SHALL provide a cell inspector showing probability, depth, severity, drivers, exposure, lifecycle and previous-run delta. | M | D |
| REQ-MAP-07 | The client SHALL provide a "changed since previous run" view. | M | D |
| REQ-MAP-08 | The client SHALL display per-layer data age plus the model version and run id in view. | M | D |
| REQ-MAP-09 | The client SHALL satisfy the accessibility requirements in REQ-NFR-USA-01. | M | D, A |
| REQ-MAP-10 | The client SHOULD cache the last-known-good hazard view for offline display. | S | D |
| REQ-MAP-11 | The basemap URL SHALL be configurable rather than hard-coded, and all required attributions SHALL be displayed. | M | I, D |

### 1.5 Alerts and communication (ALT)
| ID | Requirement | Pri | Verify |
|---|---|---|---|
| REQ-ALT-01 | Alerts SHALL be a first-class domain object, separate from message rendering and from channel delivery. | M | I, T |
| REQ-ALT-02 | The alert object SHALL carry: id, hazard type, severity band, urgency, certainty, area (geometry + human label + cell/ward ids), validity window, audience, instruction text, reason (top drivers), source data references and issuer. | M | T |
| REQ-ALT-03 | The system SHALL render any alert as a **CAP 1.2** conformant message and expose it through a standards-shaped endpoint. | M | T, I |
| REQ-ALT-04 | Severity bands SHALL be the four bands defined in `03 §5.3`, used identically across all channels. | M | T |
| REQ-ALT-05 | Recipients SHALL NOT be freely supplied per request by an unauthenticated caller; dispatch targets SHALL come from registered subscriptions or an allowlisted contact group. | M | T, I |
| REQ-ALT-06 | Duplicate alerts for the same (cell/ward, severity) SHALL be suppressed within the configured window, and the suppression SHALL be recorded. | M | T |
| REQ-ALT-07 | Every dispatch attempt SHALL be recorded with alert id, channel, recipient reference, attempt number, provider reference, status and timestamp. | M | T, I |
| REQ-ALT-08 | Failed dispatches SHALL retry with backoff and, after the configured maximum, SHALL be marked dead-letter rather than dropped silently. | M | T |
| REQ-ALT-09 | Responder alerts SHALL support acknowledgement, retrievable per alert. | M | T, D |
| REQ-ALT-10 | Delivery SHALL NOT execute inside the request-handling event loop; it SHALL be queued. | M | I, A |
| REQ-ALT-11 | Messages SHALL be composed per audience (citizen, responder, ward officer, municipal) from the same verified numbers. | M | T |
| REQ-ALT-12 | Every message SHALL contain a deep link to the corresponding map view and the alert id. | M | T |
| REQ-ALT-13 | Email SHALL include a plain-text alternative, correct `Date`/`Message-ID` headers, an aligned envelope sender and an unsubscribe path. | M | I |
| REQ-ALT-14 | The system SHOULD support multilingual composition with a deterministic fallback template when the translation service is unavailable. | S | T |
| REQ-ALT-15 | The system SHOULD support SMS and WhatsApp behind a channel interface, with per-channel cost accounting. | S | I, T |
| REQ-ALT-16 | The system SHOULD support escalation of unacknowledged critical alerts and quiet-hour digests for low severity. | S | T |
| REQ-ALT-17 | Every alert message SHALL state the decision-support status and defer to official agency guidance. | M | T, I |

### 1.6 Action intelligence (ACT)
| ID | Requirement | Pri | Verify |
|---|---|---|---|
| REQ-ACT-01 | The system SHALL expose a prioritised action list per city or ward, ranked by a documented combination of hazard severity, exposed population, criticality and accessibility. | M | T, D |
| REQ-ACT-02 | Every priority entry SHALL expose its component values and weights so the ranking is explainable. | M | T |
| REQ-ACT-03 | The system SHALL expose a stable machine-readable action list (JSON) for external consumers. | M | T |
| REQ-ACT-04 | Where facility and shelter data exist, the system SHOULD report facility exposure and reachability status. | S | T |
| REQ-ACT-05 | The system SHOULD recommend a shelter for a given origin, subject to capacity and hazard-avoidance constraints. | S | T |
| REQ-ACT-06 | The system COULD solve constrained assignment of teams/shelters (capacitated allocation). | C | T |
| REQ-ACT-07 | The system COULD record predicted-versus-reported outcomes per event for calibration review. | C | I |

### 1.7 Platform, API and security (API/SEC)
| ID | Requirement | Pri | Verify |
|---|---|---|---|
| REQ-API-01 | All endpoints SHALL be served under a versioned prefix (`/v1`), with the legacy unversioned paths retained as deprecated aliases for one release. | M | T, I |
| REQ-API-02 | Every response SHALL be a declared Pydantic model, including `/nowcast` (currently schema-less). | M | T, I |
| REQ-API-03 | Errors SHALL follow one structured shape: `error.code`, `error.message`, `error.details`, `request_id`. | M | T |
| REQ-API-04 | The OpenAPI document SHALL be complete and SHALL include examples for every layer and alert endpoint. | M | I |
| REQ-SEC-01 | Write and cost-incurring endpoints (`/train`, `/data/ingest`, alert dispatch, subscription management) SHALL require authentication. | M | T |
| REQ-SEC-02 | Read endpoints SHALL be reachable with a scoped key; an anonymous public tier MAY exist for coarse, non-sensitive layers only. | M | T |
| REQ-SEC-03 | The system SHALL enforce per-key rate limits and per-day quotas, returning a structured 429 with retry guidance. | M | T |
| REQ-SEC-04 | CORS SHALL be an explicit allowlist; wildcard origin combined with credentials SHALL NOT be used. | M | I |
| REQ-SEC-05 | Secrets SHALL be read only from environment/secret storage, never committed; a startup check SHALL fail fast if required secrets are missing when a feature is enabled. | M | I |
| REQ-SEC-06 | All remote calls SHALL use TLS with verification enabled; no `verify=False` or unverified-context paths. | M | I |
| REQ-SEC-07 | Sensitive fields (vulnerability flags, contact details) SHALL require an explicit scope and SHALL be access-logged. | S | T, I |

### 1.8 Data model and operations (DAT/OPS)
| ID | Requirement | Pri | Verify |
|---|---|---|---|
| REQ-DAT-01 | The system SHALL store: runs, cells, hotspot objects, wards (with geometry), facilities, shelters, pumps, alerts, deliveries, subscriptions, consent records and source-health records. | M | I |
| REQ-DAT-02 | Spatial tables SHALL use PostGIS geometry types with GiST indexes; queries SHALL use spatial operators rather than lat/lon range scans. | M | I, A |
| REQ-DAT-03 | Ward geometry queries SHALL support point-in-polygon and intersection (hotspot→ward joins) in one query. | M | T |
| REQ-DAT-04 | Schema changes SHALL be applied through migrations rather than `create_all` alone, and every existing table SHALL be reachable from the migration history. | S | I |
| REQ-DAT-05 | `/health` SHALL report dependency status (DB reachable, model loaded with version and age, scheduler alive, last successful fetch per source) and `/ready` SHALL gate traffic accordingly. | M | T, D |
| REQ-DAT-06 | The system SHALL maintain a source-freshness record per external source and surface staleness in responses and in the UI. | M | T, D |
| REQ-OPS-01 | Exactly one process SHALL own scheduled jobs; execution SHALL be idempotent and SHALL record start, finish and outcome. | M | I, T |
| REQ-OPS-02 | Model artefacts SHALL be stored on a persistent volume or object store and verified on load (hash, feature count, version); an unverifiable artefact SHALL refuse to load rather than silently degrade. | M | T, I |
| REQ-OPS-03 | Logs SHALL be structured JSON carrying a request/trace id, and SHALL NOT contain secrets, tokens or full personal contact details. | M | I |
| REQ-OPS-04 | Deployment SHALL pin the worker count consistent with scheduler ownership, and the conflicting `Procfile`/`Dockerfile` worker settings SHALL be reconciled. | M | I |

### 1.9 Quality, evaluation and claims (QLT)
| ID | Requirement | Pri | Verify |
|---|---|---|---|
| REQ-QLT-01 | The system SHALL NOT present in-sample or synthetic-test metrics as real-world accuracy in any response field, log line, UI element or alert. | M | I, D |
| REQ-QLT-02 | The training/evaluation response SHALL report split strategy, positive-class definition and prevalence, precision, recall, F1, ROC-AUC, PR-AUC, Brier score, calibration bins, confusion matrix and decision threshold. | M | T, I |
| REQ-QLT-03 | The system SHALL support temporal hold-out evaluation (train on earlier periods, evaluate on a later period) reported separately from in-sample metrics. | S | T |
| REQ-QLT-04 | `hotspots_mapped` and similar counters SHALL be computed from persisted records, never estimated arithmetically. | M | T, I |
| REQ-QLT-05 | Each hazard response SHALL carry a `validation_scope` statement describing which data the underlying model was evaluated on. | M | T |
| REQ-QLT-06 | Every externally visible claim (README, deck, UI, message footer) SHALL be traceable to a measurement or explicitly labelled as a target. | M | I |
| REQ-QLT-07 | The system SHOULD log forecast-versus-outcome comparisons when an outcome is reported, and expose a simple calibration view. | S | I |

---

## 2. Non-functional requirements

### 2.1 Performance (NFR-PERF)
| ID | Requirement | Target | Verify |
|---|---|---|---|
| REQ-NFR-PERF-01 | Single-point prediction (`/v1/predict`) with warm enrichment cache | p95 ≤ 400 ms | A |
| REQ-NFR-PERF-02 | Single-point prediction with cold enrichment (external fetches required) | p95 ≤ 6 s, and the response SHALL indicate that enrichment occurred | A |
| REQ-NFR-PERF-03 | City scan of ~2,000 res-8 cells including live weather attach | ≤ 60 s end-to-end | A |
| REQ-NFR-PERF-04 | Scan with fully cached inputs (no external fetch) | ≤ 15 s for 2,000 cells | A |
| REQ-NFR-PERF-05 | Layer and tile read endpoints served from cache | p95 ≤ 250 ms | A |
| REQ-NFR-PERF-06 | Ward readiness for a 15 km-radius city with cached layer data | ≤ 10 s | A |
| REQ-NFR-PERF-07 | No request handler SHALL perform blocking network or SMTP I/O on the event loop | no event-loop stall > 100 ms under load test | A, I |

### 2.2 Scalability (NFR-SCALE)
| ID | Requirement | Target | Verify |
|---|---|---|---|
| REQ-NFR-SCALE-01 | Inference SHALL be batched so throughput scales without per-cell overhead | ≥ 500 cells/s on a 1 vCPU container | A |
| REQ-NFR-SCALE-02 | Static cell features SHALL be fetched once per cell per TTL, not once per scan | ≤ 5 external calls per repeated scan | A |
| REQ-NFR-SCALE-03 | Adding a city SHALL require no code change — data and configuration only | city onboarded via boundary file and config | D |
| REQ-NFR-SCALE-04 | Storage growth per daily scan run SHALL be bounded and documented | documented budget plus a retention policy | A |
| REQ-NFR-SCALE-05 | The system SHALL remain usable for ≥ 2,500 res-9 cells at 15-minute refresh on one small container | demonstrated under load test | A |

### 2.3 Reliability and availability (NFR-REL)
| ID | Requirement | Target | Verify |
|---|---|---|---|
| REQ-NFR-REL-01 | Failure of any single external source SHALL degrade gracefully and be marked in provenance — never produce a fabricated value | 100% of partial-source responses marked; zero silent defaults | T |
| REQ-NFR-REL-02 | Alert dispatch SHALL be at-least-once with recipient-level idempotency, or exactly-once where the provider supports it | no duplicate message per alert+recipient | T |
| REQ-NFR-REL-03 | Scheduled jobs SHALL be idempotent under retry and duplicate scheduling | repeated execution creates no duplicate records | T |
| REQ-NFR-REL-04 | Availability during the demonstration window | ≥ 99% over the window, with a documented restart path | A |
| REQ-NFR-REL-05 | Cold start SHALL serve read endpoints within 60 s even while initial training runs in the background | read endpoints healthy during training | D |

### 2.4 Security (NFR-SEC)
| ID | Requirement | Target | Verify |
|---|---|---|---|
| REQ-NFR-SEC-01 | Authenticated endpoints SHALL reject requests without a valid scoped key | structured 401/403 with no leakage | T |
| REQ-NFR-SEC-02 | Email dispatch to arbitrary recipients from an unauthenticated request SHALL be impossible | verified by an abuse attempt | T |
| REQ-NFR-SEC-03 | Rate limits SHALL be enforced and observable | structured 429 with retry guidance, recorded per key | T |
| REQ-NFR-SEC-04 | Secrets SHALL never appear in logs, responses or the repository | secret-scanning check passes | I |
| REQ-NFR-SEC-05 | Transport to every third party SHALL use TLS with certificate verification | inspection of all client constructions | I |

### 2.5 Privacy and compliance (NFR-PRV)
| ID | Requirement | Target | Verify |
|---|---|---|---|
| REQ-NFR-PRV-01 | Citizen subscriptions SHALL record explicit consent with purpose, timestamp and withdrawal | consent record present for 100% of subscriptions | T, I |
| REQ-NFR-PRV-02 | Citizen location SHALL be stored at cell granularity, not as continuous traces | inspection of the storage model | I |
| REQ-NFR-PRV-03 | Vulnerability attributes SHALL be documented as sensitive, scope-gated and access-logged | access-log entry for every read | T, I |
| REQ-NFR-PRV-04 | Retention limits SHALL be implemented for delivery logs and similar data | automated purge job recorded | T |
| REQ-NFR-PRV-05 | A privacy notice SHALL be published and reachable from every citizen-facing surface | inspection | D |

### 2.6 Usability and accessibility (NFR-USA)
| ID | Requirement | Target | Verify |
|---|---|---|---|
| REQ-NFR-USA-01 | The web client SHALL meet WCAG 2.2 AA on core flows: contrast, keyboard operation, no colour-only encoding, text alternatives | audit checklist on the three core flows | A, D |
| REQ-NFR-USA-02 | The map SHALL be usable at a 360×640 viewport | demo on a phone-sized viewport | D |
| REQ-NFR-USA-03 | Locate → inspect → act SHALL be achievable in ≤ 3 interactions | recorded walkthrough | D |
| REQ-NFR-USA-04 | The citizen surface SHALL support English plus the primary local language when translation is enabled | demo in two languages | D |
| REQ-NFR-USA-05 | Every severity indication SHALL include an icon, a text label and a numeric value | inspection of palette and components | I |

### 2.7 Maintainability, portability and cost (NFR-MNT/PRT/CST)
| ID | Requirement | Target | Verify |
|---|---|---|---|
| REQ-NFR-MNT-01 | A test suite SHALL exist in-repo and run in CI on every push | every Must requirement covered by ≥1 test; CI green | A, I |
| REQ-NFR-MNT-02 | Public service functions SHALL document inputs, outputs and failure modes | inspection | I |
| REQ-NFR-MNT-03 | External providers SHALL sit behind interfaces, replaceable without touching domain logic | inspection of module boundaries | I |
| REQ-NFR-PRT-01 | The service SHALL run identically under Docker locally and on the deployment target | local container run of the demo path | D |
| REQ-NFR-PRT-02 | The system SHALL start with no optional keys configured, disabling dependent features with a clear log line | startup test with an empty environment | T |
| REQ-NFR-CST-01 | Recurring third-party cost for the demonstration path SHALL be zero | cost inventory of the demo path | I |
| REQ-NFR-CST-02 | Per-alert channel cost SHALL be computable from recorded deliveries | cost report derived from the delivery table | A |

---

## 3. Acceptance criteria for the critical Must requirements

Given/When/Then form, so each can be turned directly into a test. These gate the hackathon demo.

**AC-01 (REQ-SCN-01) — real features, live response.**
Given a configured city and a trained model, when a scan is run twice with a deliberately modified live rainfall input (high vs low), then the hotspot sets SHALL differ and each cell SHALL expose per-source timestamps showing live values were used.
*(This is the test that proves audit finding B-1 is closed.)*

**AC-02 (REQ-SCN-02/03/04) — stable identity and objects.**
Given two scans of the same city with different centres and radii, when both complete, then cells covering the same ground SHALL carry the same H3 ids, and clusters SHALL report `new`/`persisting`/`intensifying`/`clearing` relative to the previous run.

**AC-03 (REQ-SCN-06/07) — bounds.**
Given a request with `grid_size_km=0.001` or `radius_km=100`, when submitted, then the API SHALL return a structured validation error naming the permitted range and SHALL NOT begin computation.

**AC-04 (REQ-ING-01/02) — enrichment and honest failure.**
Given a request containing only `latitude` and `longitude`, when submitted with enrichment enabled, then the response SHALL report which fields were enriched; and when an upstream source is unavailable and no explicit value was supplied, the response SHALL be an error, never a silent default.

**AC-05 (REQ-WRD-01/02/04) — wards are real, or labelled.**
Given a city with a boundary source, when wards are listed, then each ward SHALL carry valid geometry, area, recorded provenance and a stable id; given a city without one, wards SHALL be H3-agglomerated with provenance `h3_agglomerated` and SHALL NOT carry any official-sounding invented name.

**AC-06 (REQ-WRD-08/09) — ward↔hotspot join.**
Given a completed scan, when ward readiness is requested, then each ward SHALL report the hotspots inside its polygon with severities and depth statistics, and SHALL include renderable geometry.

**AC-07 (REQ-MAP-01/02/03) — map layers.**
Given a completed run id, when each layer endpoint is requested with a bbox, then it SHALL return valid GeoJSON carrying the run id and `as_of`, and the vector-tile endpoint SHALL return a valid MVT for the same run.

**AC-08 (REQ-MAP-06/07/08) — inspectable forecast.**
Given the web client open on a city, when a cell is clicked, then the inspector SHALL show probability, depth, severity, drivers, exposure, lifecycle and previous-run delta with data age and model version visible; and when the change view is enabled, only changed cells SHALL remain highlighted.

**AC-09 (REQ-ALT-05) — no open relay.**
Given an unauthenticated request attempting to dispatch an alert to an arbitrary external address, when submitted, then the system SHALL reject it and SHALL record the rejected attempt.

**AC-10 (REQ-ALT-06/07/08) — suppression and audit.**
Given a WARNING already dispatched to a ward inside the suppression window, when the same condition is detected again, then no duplicate SHALL be sent, a suppression record SHALL exist, and the original delivery SHALL be retrievable with its attempt history.

**AC-11 (REQ-ALT-03) — CAP conformance.**
Given any alert object, when the CAP endpoint is requested, then the output SHALL validate against the CAP 1.2 element structure, including `identifier`, `sender`, `sent`, `status`, `msgType`, `scope` and an `info` block with `category`, `event`, `urgency`, `severity`, `certainty` and `area`.

**AC-12 (REQ-ALT-09) — acknowledgement.**
Given a responder alert, when the recipient acknowledges it, then the acknowledgement SHALL be persisted and retrievable per alert and SHALL prevent re-escalation under REQ-ALT-16.

**AC-13 (REQ-ALT-10 / NFR-PERF-07) — no event-loop blocking.**
Given a slow or hanging SMTP provider, when an alert dispatch is triggered, then concurrent read requests SHALL continue to meet their latency targets.

**AC-14 (REQ-QLT-01/04/05) — claims discipline.**
Given any API response, UI element, log line or message, when inspected, then no in-sample or synthetic metric SHALL be presented as real-world accuracy, `hotspots_mapped` SHALL equal a persisted count, and a `validation_scope` field SHALL be present on hazard responses.

**AC-15 (REQ-DAT-05 / OPS-02) — real health and verified model.**
Given the database unreachable or a model artefact whose hash/feature count does not match its metadata, when `/health` and `/ready` are requested, then the service SHALL report the degradation explicitly and `/ready` SHALL fail rather than serve unverified predictions.

---

## 4. Traceability matrix (Must requirements)

| Requirement group | Feature IDs (`03`) | Workstream | Task IDs (`08`) |
|---|---|---|---|
| REQ-ING-01…05, 09 | F-01, F-02, F-03, F-74 | Enrichment / platform | T-02, T-03, T-20 |
| REQ-SCN-01…08 | F-20…F-27 | Hotspots | T-04…T-09 |
| REQ-WRD-01…10 | F-10…F-16 | Wards | T-10…T-14 |
| REQ-MAP-01…09, 11 | F-30…F-35 | Map | T-15…T-19 |
| REQ-ALT-01…13, 17 | F-40…F-42, F-44…F-47, F-51, F-52 | Alerts | T-21…T-27 |
| REQ-ACT-01…03 | F-60 | Action | T-28 |
| REQ-API-01…04, SEC-01…06 | F-70…F-73 | Platform | T-01, T-29, T-30 |
| REQ-DAT-01…06, OPS-01…04 | F-74, F-75, F-78, F-79 | Platform / data | T-29, T-31 |
| REQ-QLT-01, 02, 04, 05, 06 | F-82 | Quality | T-32, T-33 |

Requirements without an assigned task in the six-day window (`S` and `C` priorities) are scheduled in the 90-day roadmap in `08 §Roadmap`.






