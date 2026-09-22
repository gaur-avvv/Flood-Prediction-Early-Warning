# FloodShield Integration Programme — Document Index

**Status:** Planning baseline (research + audit + design + delivery plan)
**Subject repository:** `Flood-Prediction-Early-Warning` (currently branded *Bio-SentinelX*)
**Scope of this programme:** Complete the *integration layer* — **wards, micro-hotspots, map, alerts/email** — and harden the platform to a demonstrable, judge-defensible product for the Global Innovation Hackathon 2026 (*Innovate Without Borders*, theme: real-world problem + technology solution).

> This document set is **planning and design only**. No production code is modified by this programme's planning phase. Every recommendation is traceable to either (a) evidence read directly out of this repository, or (b) an external primary source listed in the dossier's source ledger (`01 §10`).

---

## Reading order

| # | Document | Purpose | Primary audience |
|---|---|---|---|
| 00 | `00-INDEX.md` | This file — navigation, scope, decisions in one page | Everyone |
| 01 | `01-RESEARCH-DOSSIER.md` | All research: state of the art, standards, licensing, behavioural science, compliance, with adopt/reject verdicts | Architect, product, pitch author |
| 02 | `02-CURRENT-STATE-AUDIT.md` | Evidence-based audit of the existing code (`file:line`), severity, and the four focus areas + cross-cutting risks | Engineer, architect |
| 03 | `03-PRODUCT-VISION-FEATURES-UX.md` | Product definition, personas, journeys, feature catalogue (F-IDs), map + alert UX | Product, design, pitch |
| 04 | `04-REQUIREMENTS-FR-NFR.md` | Functional & non-functional requirements with acceptance criteria + traceability matrix | Engineer, QA, judge appendix |
| 05 | `05-INTEGRATION-ARCHITECTURE.md` | Target architecture, data model, spatial model (H3), workstream decomposition | Architect, engineer |
| 06 | `06-API-CONTRACT-SPEC.md` | Endpoint-by-endpoint contract: new, changed, deprecated; errors, auth, caching, versioning | Engineer, integrator |
| 07 | `07-PERFORMANCE-COST-OPTIMIZATION.md` | Compute strategy, caching layers, tiling, batch inference, cost model, capacity numbers | Architect, ops |
| 08 | `08-SDLC-DELIVERY-PLAN.md` | Process model, 6-day critical path, WBS, DoR/DoD, quality gates, risk register, demo script | Delivery lead, whole team |
| 09 | `09-ADR-DECISION-LOG.md` | Architecture Decision Records with alternatives, what survives, migration paths | Architect, technical judge |

---

## One-page executive summary

### The honest current position
The repository contains a genuinely well-built **hazard engine core**: a FastAPI service, an async multi-source data collector over open APIs, 44 engineered features, a stacked RF+XGBoost+LightGBM ensemble with calibrated probabilities and a separate depth regressor, a scheduler, Docker/Render/Railway deployment, and a complete REST surface.

The gap is not the model. The gap is that **the three highest-visibility product surfaces — hotspot scanning, ward readiness, and alerting — do not consume the engine's own data path**. They synthesise their inputs from trigonometric coordinate patterns, and there is **no spatial output format and no map at all**. Measured evidence is in `02-CURRENT-STATE-AUDIT.md`.

### The four focus areas (as requested)
1. **Wards** — no real ward geometry exists; ward "grid" is synthetic; the `india_wards.csv` lookup path resolves *outside* the repository, so it can never succeed. Result: ward names/IDs/areas are invented and cannot be re-identified between runs.
2. **Hotspots** — grid cells are generated correctly as geometry, but each cell's feature vector is fabricated from `sin/cos` coordinate arithmetic rather than fetched from the collector (which already exists and works). Stable identity is a float-formatted lat/lon string.
3. **Map integration** — absent entirely. No GeoJSON, no tiles, no bbox queries, no frontend. Alerts therefore cannot deep-link to a location, which is the single largest UX loss.
4. **Email / alerts** — SMTP-only, synchronous inside async handlers, unauthenticated (an open relay for arbitrary recipients), with no dedupe, escalation, retry, delivery log, acknowledgement, quiet hours, multilingual support, or standards-compliant alert object (CAP).

### What this programme decides
- **Spatial identity standard:** H3 hexagonal indexing (resolution 8 ≈ 1 km cells; resolution 9 ≈ 250 m cells) replacing float-string cell IDs.
- **Wards:** real boundary ingestion (OSM/administrative boundary sources) into PostGIS, with a deterministic fallback (H3-cell agglomeration) when boundaries are unavailable — never invented names.
- **Hotspots:** real feature assembly from cached static layers + live meteorology, plus hotspot *objects* (clusters with lifecycle: new / persisting / intensifying / clearing) instead of a flat cell list.
- **Map:** GeoJSON API endpoints for integration plus a MapLibre + PMTiles frontend (no API keys, no OSM tile-policy exposure).
- **Alerts:** internal `Alert` domain object → fan-out to email / SMS / WhatsApp / CAP / webhook, with dedupe, throttling, escalation, acknowledgement and a delivery audit table. CAP 1.2 as the interoperability surface so the platform can be aggregated by national warning systems rather than competing with them.
- **Claims policy:** the "99.45% accuracy" and "2,500+ hotspots mapped" figures are *not* presentable as operational performance. `08-SDLC-DELIVERY-PLAN.md` §Claims defines exactly what may and may not be said on stage.

### The deadline reality
The published project-submission/jury window is **27 September 2026, 09:30–17:30 IST**. Assuming a 21 September 2026 start, the critical path is **6 calendar days**. `08-SDLC-DELIVERY-PLAN.md` therefore defines a **6-day critical path** (must-ship) and a **post-hackathon 90-day roadmap** (should-ship), with explicit scope-cut lines so that a partially completed programme still demos as a coherent product.
