# 09 — Architecture Decision Log

Format: **Context → Decision → Alternatives → Consequences → Migration/Reversal.** Status values: *Accepted*, *Watch* (revisit after the hackathon), *Superseded*. Each ADR cites the audit findings (`02`) and dossier sections (`01`) that justify it, and the task ids (`08 §6`) that implement it.

---

### ADR-001 — H3 hexagonal indexes as the spatial identity of cells, hotspots and alert areas — **Accepted**

**Context.** The current hotspot scan identifies cells with `cell_id = f"{lat:.4f}_{lon:.4f}"` (`services/predictor.py:249`), an identifier that changes with the query's centre and radius — breaking history, dedupe and any "same place" question. The product must also claim both ~1 km and ~250 m resolution coherently.

**Decision.** H3 becomes the primary key of every cell and the geometry basis of every hotspot object, alert area and ward fallback. Default resolution 8 (0.737 km², ~531 m edges); resolution 9 (0.105 km², ~201 m edges) for micro-scale passes; hierarchical roll-up between them with no geometry operations.

**Alternatives.** (a) *Lat/lon strings* — simplest, but identity is a formatting artefact and spatial operations stay ad-hoc. (b) *Geohash* — short strings, but square-shaped and non-hierarchical for our aggregation need. (c) *Ward-locked cells* — no stable identity before wards exist. (d) *S2 cells* — valid; H3 wins because a hexagon is a natural alert polygon, its hierarchy is ~7:1, and res 8/9 land exactly on our tiers.

**Consequences.** Stable identity, clustering and roll-up become library calls; the map layer, alert geometry and suppression key are the same object. One new dependency (`h3`); the API needed is five functions. Migration: legacy `cell_id` strings translate once to their containing res-8/9 cells.

**Reversal.** If H3 proves a velocity problem during the D-6 spike (risk R-9), fall back to a stable cell-registry table (one row per cell, id = content hash of centre + resolution), losing only hierarchical roll-up.

---

### ADR-002 — One enrichment service as the single feature-assembly path — **Accepted**

**Context.** Three code paths currently invent covariates: hotspot scans (`sin`/`cos` per cell, audit B-1), ward readiness (same per ward, audit A-3), and default-heavy single-point prediction (audit X-13). The collector that fetches the real values already exists and is the strongest part of the codebase.

**Decision.** All prediction paths — single point, bulk, scan, ward, nowcast — obtain covariates exclusively from `services/enrichment.py`, which reads the H3-keyed static cache plus the live cache and stamps provenance and source health. No caller may construct a covariate from anything other than the request, the caches or the collector. Strict mode fails loudly rather than defaulting (REQ-ING-02).

**Alternatives.** (a) *Keep per-path synthesis as a fallback* — rejected; that is exactly the credibility failure this programme removes. (b) *Fetch everything live per request* — rejected on rate-limit and latency grounds; the cache tier is the answer. (c) *Prefetch the whole city into one JSON* — rejected; unqueryable and un-updatable.

**Consequences.** `predictor.py` loses the synthesis in `_build_grid_requests` and the coordinate-derived features in `_generate_ward_grid` (M6, only after AC-01/AC-05 prove the replacement). One honest, measurable, cacheable path. Implemented by T-02/T-03.

---

### ADR-003 — Persisted, immutable forecast runs as the unit of truth — **Accepted**

**Context.** Nothing is stored for a scan today: no "previous run", no trend, no replay, and `hotspots_mapped` is arithmetic (audit A-4, X-10).

**Decision.** Every scan produces an immutable `scan_run` plus its `cell_score`, `hotspot` and `ward_readiness` rows. Corrections create a new run and never mutate history. Reads are queries over persisted state; nothing recomputes in a request path.

**Alternatives.** (a) *Compute on read* — today's behaviour; rejected on latency, auditability and repeatability. (b) *Append-only event log* — over-engineered for the window; row-per-run achieves the same immutability.

**Consequences.** Lifecycle, change view, replay, honest counters and suppression history all become queries. Retention and roll-up defined in `07 §1`. Implemented by T-05/T-30.

---

### ADR-004 — MapLibre + a self-hosted, keyless vector basemap; no OSM raster tiles, no keyed map SDK in the critical path — **Accepted**

**Context.** No map exists. The convenient default (`tile.openstreetmap.org`) is explicitly unsuitable for production or funding-seeking use: best-effort, no SLA, blockable without notice, with a direct warning to commercial and donation-seeking services (dossier §3.2). Keyed stacks (Google Maps, Mapbox) add a quota, a billing account and a terms review to a six-day build (dossier §3.4).

**Decision.** MapLibre GL for the client; a self-hosted vector basemap as the default style; the basemap URL is configuration, not a constant (REQ-MAP-11); hazard layers are our own GeoJSON/MVT. Google Maps remains an optional, documented adapter for municipal customers holding a Maps Platform agreement.

**Alternatives.** (a) *Google Maps* — excellent, keyed, metered; rejected for the demo critical path. (b) *Mapbox GL* — same objection. (c) *Leaflet + OSM raster tiles* — the policy exposure above; rejected. (d) *MapLibre + MapTiler free tier* — the acceptable fallback if self-hosting proves expensive; still needs a key, so it is second choice.

**Consequences.** Zero map cost and zero policy exposure for the demo; portability to any provider by configuration. Implemented by T-15–T-17.

---

### ADR-005 — Alerts are a decide → compose → deliver pipeline, with CAP 1.2 as the interoperability surface — **Accepted**

**Context.** Alerting today is three endpoints that compute, render and send in one shot, with blocking SMTP inside async handlers and no alert object (audit D-1…D-8). CAP is the standard the Indian public-warning ecosystem (SACHET) and the international EW4All movement are built on (dossier §2.1).

**Decision.** An `Alert` domain object carries the full decision state; composers render per audience and channel; a queued dispatcher delivers with retry, suppression, audit and acknowledgement; a pure function renders any alert as CAP 1.2 XML. Dispatch is never executed inside a request handler.

**Alternatives.** (a) *Keep the three-endpoint shape* — rejected; it conflates decision and delivery and is the open-relay root cause. (b) *Send immediately at scan time from the scheduler* — rejected; the same event-loop problem, minus auditability. (c) *Adopt CAP only at export* — rejected; the object must be CAP-shaped so the area polygon is valid (`05 §6.3`).

**Consequences.** The same verified numbers feed every audience; the suppression history answers "how do you avoid crying wolf?"; the CAP export is the municipal-integration story. Implemented by T-21–T-27.

---

### ADR-006 — No LLM in the risk path; a constrained LLM only as a composition layer, with a deterministic fallback — **Accepted (with conditions)**

**Context.** An LLM that "predicts flooding" would be non-deterministic, uncalibrated and unauditable — fatal to the claims policy. An LLM that *phrases* verified numbers for different audiences and languages is a genuine UX win, provided it cannot invent numbers (dossier §9).

**Decision.** The composer works from the alert object only. An LLM may reword, never recompute: numbers are passed as locked fields with a template fallback when the provider is unavailable. If enabled at all, the LLM sits behind the briefing/translation interface with cost bounds (`07 §4.2`).

**Alternatives.** (a) *LLM end-to-end briefing over raw run data* — rejected: numerical drift and hallucination risk in a safety context. (b) *No LLM at all* — the six-day default; the interface exists so it can be added later without disturbing the pipeline. (c) *Bhashini-only translation* — the accepted shape for the multilingual path, PoC terms noted (dossier §9).

**Consequences.** The product can truthfully say "the model decides; the language model phrases" — the sentence that answers the current jury instinct about LLMs in emergencies.

---

### ADR-007 — Ward geometry from real sources, with an H3-agglomeration fallback; synthetic ward names are never presented as official — **Accepted**

**Context.** `_generate_ward_grid` builds a 7×7 lattice and invents `WARD-001`-style ids (audit A-1/A-2/A-6). The `india_wards.csv` path is unreachable. There is no ward geometry, so there is no ward map, no hotspot join and no defensible population claim.

**Decision.** Wards are ingested from a real boundary source (vendored administrative dataset, a supplied municipal file, or an OSM admin relation) and stored with provenance. Where none exists, wards are agglomerations of res-8 cells — real polygons with real area — labelled `h3_agglomerated` and named `Zone N (H3)` with `name_is_official: false`. Ids are stable per boundary set.

**Alternatives.** (a) *Keep the lattice* — rejected; it is the audit's S1 finding. (b) *Require municipal boundaries* — rejected; that blocks onboarding in exactly the low-data places the product is for. (c) *Use OSM `admin_level=10/11` directly with no fallback* — coverage is inconsistent across India, so it becomes a source, not the source.

**Consequences.** Ward layers render, hotspot joins are one spatial query, and the honesty of the boundary is on screen. Implemented by T-10–T-14.

---

### ADR-008 — PostGIS in production, SQLite with a documented Python fallback in development — **Accepted**

**Context.** Geo lookups today are `between(lat ± 0.1)` range scans with no geometry types, no GiST indexes and no polygon storage (audit X-12), and `flood_events` is never created (audit X-11). Ward polygons, hotspot joins and the action layer all need real spatial queries.

**Decision.** PostgreSQL + PostGIS is the production store, accessed through SQLAlchemy/GeoAlchemy with migrations. SQLite remains the local-dev default, with a capability probe that falls back to a Python point-in-polygon path and logs a warning. `init_db` is replaced by migrations so `flood_events` is actually created.

**Alternatives.** (a) *SpatiaLite for production too* — weaker concurrency and index options; rejected for production, allowed as a dev nicety. (b) *DuckDB + spatial* — excellent for analysis, not a transactional store; rejected as primary. (c) *SQLite-only* — rejected; it cannot answer "hotspots in ward X" at municipal scale.

**Consequences.** One new production infrastructure requirement, additive migrations, and a documented dev-only degradation. Implemented by T-30.

---

### ADR-009 — A single scheduler process plus a job queue; blocking work never runs on the request path — **Accepted**

**Context.** The Procfile runs `--workers 2` while the image runs one worker, so APScheduler would execute cron twice per worker (audit X-5). SMTP runs inline and blocks the event loop (audit D-2). Startup retraining writes to an ephemeral filesystem (audit X-6).

**Decision.** Separate `web` / `scheduler` / `worker` entry points; exactly one scheduler instance guarded by a lock; all side-effecting work (scans, dispatch, retraining) is queued with idempotency keys and retry-with-backoff. The queue backend is Redis-backed and asyncio-native, sized for the three job families in `01 §7.1`.

**Alternatives.** (a) *APScheduler + BackgroundTasks everywhere* — today's shape; rejected: no cross-process dedupe, no restart survival. (b) *Celery* — capable but heavier than the window justifies; the ARQ/TaskIQ-class choice delivers the same guarantees with fewer moving parts. (c) *Serverless functions* — rejected; the product needs a scheduler, warm model state and persistent job state.

**Consequences.** Healthchecks stop timing out during SMTP hangs; cron runs once; retraining no longer fights request traffic. Implemented by T-24/T-31 plus the deployment change that reconciles the Procfile/Dockerfile worker count.

---

### ADR-010 — Versioned API with deprecation, and a structured error model — **Accepted**

**Context.** All routes are unversioned and `/nowcast` returns an untyped dict (audit X-4, REQ-API-02). No contract can evolve without breaking integrators.

**Decision.** All endpoints live under `/v1`; legacy unversioned paths are deprecated aliases for one release; every response is a declared Pydantic model; every error uses the shape in `06 §4`; idempotency keys are supported on writes.

**Alternatives.** (a) *Header-based versioning* — rejected; URL versioning is the pragmatic default for a public geospatial API. (b) *No aliases* — rejected; the deployed service already has consumers.

**Consequences.** The OpenAPI surface is complete and example-rich (REQ-API-04) — itself a scoring and integrability asset. Implemented by T-01.

---

### ADR-011 — Scoped API keys, rate limits, and a fixed CORS posture — **Accepted**

**Context.** No endpoint is authenticated (audit X-1), `/email/*` accepts arbitrary recipients (audit D-1), there are no quotas (audit X-2), and CORS is wildcard-with-credentials (audit X-3).

**Decision.** `X-API-Key` authentication with scopes (`read:public`, `read:agency`, `write:operator`, `admin`, `notify`, `read:sensitive`); per-key rate limits and daily quotas with a structured 429; CORS restricted to an explicit allowlist; a startup secret check fails fast when a feature's required secret is missing.

**Alternatives.** (a) *JWT/OAuth for everything* — rejected for the window; scoped keys are sufficient and far simpler for machine clients. (b) *IP allowlisting only* — rejected; keys provide per-client quotas and audit, which the claims and cost stories need.

**Consequences.** The open-relay finding is closed by construction (REQ-ALT-05, AC-09); abuse of training and scan endpoints is bounded. Implemented by T-29.

---

### ADR-012 — Claims discipline is a build-time feature, not a marketing decision — **Accepted**

**Context.** The README quotes 99.45%/99.17%/99.84% with explicit in-sample/synthetic caveats and calls the outputs "not operational life-safety accuracy", while `/train/status` exposes no held-out metrics and `/health` reports an arithmetic hotspot count (audit X-10, A-4; dossier §6.2).

**Decision.** `validation_scope` becomes a field on hazard responses; the training response gains a full metrics block (REQ-QLT-02); counters are computed from persisted records (REQ-QLT-04); and the claims policy (`08 §10`) is enforced in review.

**Alternatives.** (a) *Silence* — rejected; the numbers will be found. (b) *Remove the metrics* — rejected; honest, qualified metrics are stronger than none.

**Consequences.** The honesty slide becomes the differentiator; the product earns the trust question rather than surviving it. Implemented by T-32/T-33 and the CM checklist.

---

### ADR-013 — Keep the ML core unchanged; migrate by strangler, not rewrite — **Accepted**

**Context.** The engine is well-designed (`02 §7`), and retraining risk inside a six-day window is high. Its real problems are wiring, contract and presentation — not modelling.

**Decision.** No changes to model architecture, feature definitions or training methodology in this programme, except the metrics/reporting surface (T-32). `FloodPredictor`'s public method signatures are preserved while the implementation is rerouted (M1–M6).

**Alternatives.** (a) *Rewrite around a new model* — rejected; it burns the window on the strongest existing asset. (b) *Freeze the codebase entirely* — rejected; it would leave the audit's S1 findings in place.

**Consequences.** Velocity goes to the four focus areas; the engine is protected by smoke tests while it is wrapped. Implemented by T-02–T-09 under M1–M6.

---

### ADR-014 — IMD as context and cross-check; Google Flood Forecasting API as an optional riverine input — **Watch (adopt the interface now)**

**Context.** IMD's public API exposes district warnings, nowcasts, rainfall and radar (dossier §4.1). Google's Flood Forecasting API is riverine, waitlisted and free (dossier §1.1/§1.3).

**Decision.** The enrichment interface gains an optional `imd` provider and an optional `river_forecast` provider from day one, both disabled by default. IMD context is a Phase-1 roadmap item; the Google API application is submitted immediately but its integration is not on the critical path.

**Alternatives.** (a) *Integrate IMD nowcast into scoring during the window* — rejected; it is a cross-check layer, and the six days are spent on the core. (b) *Wait for Google approval before designing the interface* — rejected; the interface is cheap, approval is not.

**Consequences.** The story "we complement, not compete, with IMD and Google" becomes structurally true, not just asserted.

---

### ADR-015 — Email is one channel behind a dispatcher, hardened for deliverability; SMS and WhatsApp are designed, not shipped, in the window — **Accepted**

**Context.** Today email is the only channel, sent synchronously, with a single HTML part, no correct headers, and a default sender that only accidentally aligns with Gmail's authentication requirement (audit D-2/D-6/D-8). WhatsApp's per-message pricing with free in-window utility templates (dossier §2.3) and India's SMS registration reality argue for a multi-channel mix — but not inside six days.

**Decision.** `services/channels/` ships email and webhook; SMS and WhatsApp exist as interfaces with documented pricing and policy notes, shipped in Phase 1 of the roadmap. Email gains the plain-text alternative, correct headers, an aligned sender and an unsubscribe path. Channel choice is policy, not code.

**Alternatives.** (a) *Ship all four channels now* — rejected; provider onboarding (DLT sender registration, WhatsApp Business verification) is externally timed and cannot be forced. (b) *Drop email for SMS* — rejected; email is the zero-cost channel already wired.

**Consequences.** The demo shows the *architecture* of multi-channel delivery with email and webhook working end-to-end, and the claims policy states SMS/WhatsApp are designed, not delivered.

---

### Change-control rule
Any change to an *Accepted* ADR requires a new ADR that *supersedes* (never edits) the original, a note in the risk register, and a check of the traceability matrix in `04 §4`. This keeps the design auditable after the hackathon, when the pace slows and the temptation to edit history grows.



