# 01 — Research Dossier

**Purpose:** the complete external evidence base behind every decision in `05`–`09`. Each section ends with an explicit **verdict** — *Adopt*, *Adopt with conditions*, *Reject*, or *Watch* — so later documents can cite a decision instead of re-arguing it. Sources are numbered `[S-n]` and listed in §10 with retrieval dates.

**Method.** Three passes: (1) *state of the art* — what leading operational systems do and what they state they cannot yet do; (2) *standards, platforms and licensing* — the interoperability, terms-of-use and pricing realities that constrain an open-data product; (3) *human, legal and operational* — what makes a warning change behaviour, and what an India-first product must legally respect. Repository-specific findings live in `02-CURRENT-STATE-AUDIT.md`; this document is deliberately world-facing.

---

## 1. Position in the state of the art — and the genuine gap we occupy

### 1.1 What the global leader actually does
Google's flood forecasting is the most visible operational AI flood service in the world. From its own material:

- **Coverage:** 100 countries with verified data, expanding to **up to 150 countries using virtual gauges**, delivered via Flood Hub `[S-1]`.
- **Lead time:** the 2024 model provides **7-day lead-time reliability comparable to the then-best available nowcasts** `[S-1]`.
- **Validation method:** a hydrological event is defined as discharge **above a 10-year return period**, then checked against **SAR-detected inundation events** from Sentinel-1 — wet/dry pixel segmentation by Gaussian mixture model, then a Random Forest classifier deciding whether an image represents an inundation event. Because Sentinel-1 revisit is **12 days**, the ground-truth set is sparse, so a location is also counted as validated when "another nearby and hydrologically similar location" has been validated — a strategy that "allows us to validate 30% more locations" `[S-1]`.
- **Explicitly out of scope, named as future work: "flash floods, urban floods and coastal floods"** `[S-1]`.

The public **Flood Forecasting API** is **riverine-only**. It exposes *Flood Status* ("the current severity of a flood, which could include inundation maps", refreshed several times a day) and *Hydrologic forecast* ("daily hydrologic forecasts up to a 7-day horizon", multiple lead times spaced between one hour and 24 hours), over real **and virtual (HYBAS) gauges**, with a `qualityVerified` flag and an `includeNonQualityVerified` option `[S-2]`. Access requires joining a **waitlist**, being approved, then enabling the API in a Google Cloud project with an **API key**; the data is **free under CC BY 4.0** `[S-3]`. Historical companions are the **Inundation History** dataset (water occurrence 1999–2020) and **GRRR** (Google Runoff Reanalysis & Reforecast, global river discharge 1980–2023) `[S-2]`.

### 1.2 The implication, stated precisely
- The dominant operational AI flood service is **riverine, multi-day, catchment-scale**, and its own authors name **urban floods as an unsolved extension**.
- This system targets **urban pluvial (rainfall-driven) flooding at 250 m–1 km cells and 30–120 minute horizons** — exactly the cell-and-hour regime that neither Flood Hub nor the Flood Forecasting API addresses.
- **The correct posture is complementarity, not competition.** The strongest available technical narrative is: *"the world's leading flood AI solves the river, seven days out. We address the street, within the next two hours — and then we wire that into who acts on it, where, and in what order."*

### 1.3 Second-order consequence: use the riverine layer as an input
GloFAS discharge is already a feature (`river_discharge_m3s`, `discharge_anomaly_ratio` — `models/flood_model.py:77`). A future integration can add Flood Forecasting API gauge forecasts alongside GloFAS for **compound river-plus-rain events** — a case that materially matters in cities such as Chennai, Surat, Guwahati and Patna. Because access is waitlisted, this is a *Watch* item and never on the critical path.

> **Verdicts.** *Adopt:* the complementarity positioning, quoted verbatim in the pitch. *Adopt with conditions:* Flood Forecasting API as an optional riverine input, gated on waitlist approval — apply immediately, because approval timing is outside our control. *Adopt:* GRRR and Inundation History as offline validation references.

---

## 2. Alerting and interoperability standards

### 2.1 CAP — the interoperability surface
CAP is described by WMO/ITU/GSMA/OASIS co-authors as "an open, structured data standard for alerts that allows a single warning message to be distributed simultaneously over multiple media and platforms"; the ITU standard is **ITU-T X.1303 bis (CAP 1.2)** `[S-4]`. CAP "standardizes the content of the message" while delivery channels (cell broadcast, SMS, sirens, apps, websites) handle reach. WMO's October 2025 recommendations include **"Adoption of CAP as a national standard for the routine dissemination of warnings, promoting consistency, interoperability and scalability"**, prioritising mobile dissemination including cell broadcast, and building enabling legal and coordination environments `[S-4]`.

India-specific evidence in the same article: the author list includes the **India Meteorological Department**; the references cite GSMA's **"India's SACHET Public Warning System: A Case Study in Mobile Alerting" (2025)** and GSMA's **Cell Broadcast for Early Warning Systems (2023)** `[S-4]`. Independently, Indian cities are building the receiving end: **Greater Chennai Corporation** is strengthening real-time flood forecasting through its **Integrated Command and Control Centre**, and Gurugram's MCG is standing up an integrated command centre to monitor urban flooding `[S-5]`.

> **Verdict — Adopt.** Model alerts internally as a CAP-shaped object (`identifier`, `sender`, `sent`, `status`, `msgType`, `scope`, plus `info[]` carrying `category`, `event`, `urgency`, `severity`, `certainty`, `effective`/`expires`, `area` polygon and `instruction`), then render that object into every channel. A small data-model decision with an outsized payoff: it converts the project from *another app* into *a feed that ICCC-style command centres and CAP aggregators can consume*.

### 2.2 Cell broadcast — the right "reach" argument, but not our build
Cell broadcast reaches "all mobile phones in a defined area within seconds, even if networks are congested or individual users are not subscribed to any alert service" `[S-4]`. That is exactly what urban flash-flood warning needs. It is also **not buildable by a hackathon team**: it requires an MNO agreement and a regulator-recognised alerting authority. Its value here is architectural and rhetorical — it justifies the *polygon-in-a-CAP-message* design and is the honest answer to "what about people without smartphones?".

> **Verdict — Watch (design for it, do not claim it).**

### 2.3 Messaging channels a small team can actually use, with 2025–2026 cost reality
Meta's WhatsApp Business Platform moved to **per-message pricing on 1 July 2025**, replacing conversation-based pricing. Charging applies only to **delivered template messages**, priced by category (marketing / utility / authentication) and recipient country calling code. Crucially: **"Utility templates delivered within an open customer service window are free"**; non-template messages inside that window are free; all messages are free for 72 hours inside a **free entry point window**; and **volume tiers** lower utility/authentication rates `[S-6]`.

For a flood-alert product this means a citizen who has messaged the service (opening the 24-hour service window) can receive a **free** utility notification during an active event, while opted-in cold outreach costs a small, tiered per-message amount. With SMS and email alongside, that is a three-channel mix whose cost profile is defensible both in a hackathon pitch and in a municipal tender.

> **Verdict — Adopt with conditions.** Email (free, weak urgency) + WhatsApp utility templates (cheap or free in-window, high Indian reach) + SMS (highest reliability; needs DLT-style sender registration and provider fees). Channel selection must be a **code-level policy**, not a hard-coded call.

### 2.4 What this means for the current three-endpoint design
The existing `/email/ward-alert`, `/email/hotspot-alert`, `/email/nowcast-alert` shape conflates three separate concerns — *deciding* there is an alert, *composing* it, and *delivering* it. Standards, cost and reliability all argue for separating them: a decision engine emits `Alert` objects; a composer renders CAP-shaped content per audience and language; a dispatcher fans out per channel with its own retry, dedupe and cost accounting.

---

## 3. Geospatial engineering decisions

### 3.1 Spatial identity — hexagonal indexing
Uber's H3 provides a global discrete hexagonal grid. From the official cell-statistics tables `[S-7]`:

| H3 res | Avg hexagon area | Avg edge length | Fit to our target |
|---|---|---|---|
| 7 | 5.161 km² | 1.406 km | coarse ~2 km city zoning |
| 8 | **0.737 km²** | **0.531 km** | **the "1 km cell" product tier** |
| 9 | **0.105 km²** | **0.201 km** | **the "250 m micro-hotspot" tier** |
| 10 | 0.0150 km² | 0.0759 km | sub-100 m, urban-block scale (later) |

The min/max hexagon-area spread stays ≤1.99× even at fine resolutions, and cell counts follow `2 + 120·7^r`, giving a clean hierarchical roll-up (a res-8 parent contains ~7 res-9 children).

**Why this matters concretely.** It replaces `cell_id=f"{lat:.4f}_{lon:.4f}"` (`services/predictor.py:249`) with an identifier that is a property of the earth rather than of the query. That single change makes hotspot identity stable across scans, enables parent/child aggregation from 250 m to ward scale without geometry libraries, provides a natural primary key for persistence and alert dedupe, and lets one cell carry both the map layer and the suppression key.

> **Verdict — Adopt.** `h3` resolution 8 as the default product cell (~1 km) and resolution 9 for micro-scale analysis (~250 m). The existing metre-aware grid maths can remain an internal sampling detail; the **published identity becomes the H3 index**.

### 3.2 Base maps — why the convenient default is a trap
The OSMF Tile Usage Policy states plainly that OSM's tile servers "are not [free for everyone]: they are funded by donations and sponsorship, and capacity is limited". Mandatory: the exact URL `https://tile.openstreetmap.org/{z}/{x}/{y}.png`; visible licence attribution; a **valid HTTP User-Agent that clearly identifies your application** (the policy's own example includes a contact URL or email) or a web Referer; caching per HTTP headers **or ≥7 days minimum**; and no bulk download, prefetching or "download for offline" features. Availability is "best-effort: there is no SLA or guarantee"; access "may be blocked without prior notice"; and — directly relevant here — **"Commercial services, or those that seek donations, should be especially aware that access may be withdrawn at any point"** `[S-8]`.

> **Verdict — Reject `tile.openstreetmap.org` for the product.** *Adopt* a self-provided or explicitly licensed basemap (see ADR-004), attributing OSM data correctly wherever OSM data is used, and follow the policy's own advice to **not hard-code the tile URL** so the source can be swapped without a client update.

### 3.3 Reverse geocoding and the public Nominatim instance
The audit (`02` §C-4) records a per-request call to `nominatim.openstreetmap.org` with `User-Agent: "BioSentinelX-App"` — no contact address — inside the ward path, uncached. The same identification expectations apply as for tiles, and the public instance additionally expects caching and roughly ≤1 request/second, with self-hosting or a commercial provider for anything heavier.

> **Verdict — Adopt with conditions.** Cache reverse-geocoding results by rounded H3 cell with a long TTL; set a UA naming the app **and** a contact; move geocoding out of the request-critical path; prefer a vendored administrative-boundary dataset for city identification over live geocoding.

### 3.4 Google Maps Platform — the March 2025 pricing reset
Effective **1 March 2025**, Google Maps Platform replaced the recurring **USD $200 monthly credit** with **free usage caps per SKU**, organised into **Essentials / Pro / Enterprise** categories, added expanded volume discounts, and designated **Places API, Directions API and Distance Matrix API as Legacy** (successors: Places API (New), Routes API). The published examples show India-specific price SKUs with large free monthly allowances `[S-9]`.

> **Verdict — Reject for the hackathon demo; Watch for enterprise integration.** A keyed, per-call-billed map stack adds a quota, a billing account and a terms review to a 6-day build, while MapLibre plus self-hosted tiles produces a better-looking result with no key. Google Maps remains a documented *optional* adapter for municipal customers who already hold a Maps Platform agreement.

---

## 4. Public data sources — capability, terms and what to add

The collector already uses Open-Meteo (archive + forecast), the Open-Meteo Flood API (GloFAS), OpenTopoData (SRTM 30 m), SoilGrids REST and OSM Overpass (`services/data_collector.py:28–33`). All are keyless, which is why the product is deployable anywhere at zero licence cost. Two categories of addition are worth evaluating:

### 4.1 National sources — India
IMD publishes a **public API reference** with JSON endpoints covering: city forecasts (7-day, by station id or by lat/lon), **district-wise nowcast**, **station-wise nowcast**, **current weather**, **AWS/ARG** observations, **district-wise warnings** and **subdivision-wise warnings**, **district-wise and state-wise rainfall**, **river-basin QPF**, **highway nowcast/warning**, **radar imagery**, **lightning data**, agromet advisories, and cyclone track/wind/cone-of-uncertainty products `[S-10]`. The reference documents no API key for these public endpoints, but the terms of use and any registration requirement must be confirmed before integration.

Three of these are directly valuable and none are keyed:
- **District-wise warnings** — the official severity/colour-coded context in which our hyper-local output should be framed (and the authoritative voice to defer to).
- **District/station-wise nowcast** — a national nowcast cross-check for the 0–6 h window, allowing an agreement metric rather than a competing claim.
- **Radar imagery** — the honest input for very-short-range rainfall extrapolation, currently absent.

> **Verdict — Adopt with conditions.** Integrate district warnings and district rainfall first (low effort, high credibility, framed as *context*, not replacement). Treat radar and lightning as *Watch* items. Verify terms of use before any production claim, and always display IMD guidance alongside ours.

### 4.2 Global/regional additions already costed by evidence
- **ERA5-Land / Copernicus CDS** — the authoritative historical rainfall reanalysis for training without depending on one commercial archive; requires an account and API key but is free at the point of use. *Watch* (training-time only, not on the runtime path).
- **Copernicus DEM GLO-30 / FABDEM** — better urban terrain than SRTM 30 m (GLO-30 is a global 30 m DSM; FABDEM removes buildings and tree canopy, which is exactly the correction urban drainage modelling needs). Licensing differs from SRTM's public-domain status and must be reviewed. *Watch — highest-value single upgrade to the hazard engine after the work in §5 of the audit.*
- **Google Flood Forecasting API** — riverine, waitlisted, free (`[S-2]`, `[S-3]`). *Adopt with conditions*, apply now.
- **GRRR + Inundation History** — historical river discharge 1980–2023 and water occurrence 1999–2020, both usable as offline reference layers for validation and for historical-event context in the UI `[S-2]`. *Adopt (offline).*

### 4.3 Data-provenance discipline (required by the hackathon rules)
The rules state that "third-party resources used in the project should be appropriately acknowledged". This project already leans on five external services, so every response should carry provenance: a `data_sources[]` array with source name, licence and retrieval timestamp, plus an `as_of` field per hazard layer. This is both a compliance requirement and a trust feature — a municipal user needs to know whether an elevation figure is SRTM 30 m or a local survey.

> **Verdict — Adopt.** Provenance becomes a first-class field in the API contract (`06-API-CONTRACT-SPEC.md`) and a visible element in the UI (a small "data age" indicator per layer).

---

## 5. Human factors — what makes a warning actually work

Technical accuracy is not sufficient; the evidence is that warning systems fail at the *response* stage.

### 5.1 Cry-wolf / false-alarm effects
Hydrology and Earth System Sciences published work modelling **"Impact of cry wolf effects on social preparedness and the efficiency of flood early warning systems"**, and HESS 2024 work on **"Thresholds of issuing flash flood warnings based on people's response process simulation"** — i.e. the question of *when* to warn is itself a modelled decision problem, not an afterthought. Related 2025 work examines the **causal effects of the perceived false-alarm ratio on flood warning response** `[S-11]`. The consistent finding across this literature: over-warning erodes credibility and reduces future protective action, so warning policy must include **suppression, severity gating and honest uncertainty communication**, not merely a probability threshold.

> **Verdict — Adopt.** Implement dedupe windows, severity gating, escalating severity only, quiet hours/digests for low severity, and an explicit acknowledgement mechanism for responders. Publish the false-alarm history in the dashboard. Put a slide in the pitch titled *"Why we suppress alerts"* — it is the opposite of what most hackathon teams show, and it is what practitioners look for.

### 5.2 Design implications for the citizen experience
Combining the WMO/EW4All framing (timely, accurate, **actionable**, on channels people trust and can access `[S-4]`) with the cry-wolf evidence `[S-11]`, the citizen surface must answer, in this order and in the user's language: *what is happening, how bad, when will it affect me, what should I do now, where do I go, and how sure are you.* Concretely: a single severity banner, an explicit action sentence, a shelter/route card, a confidence qualifier, and a timestamp — never a raw probability without an instruction.

---

## 6. Model and validation state of the art — and how to present our metrics honestly

### 6.1 What credible flood-ML validation looks like
Google's validation pattern is instructive precisely because it is *independent of the model* `[S-1]`:
1. Define an event by a physically meaningful threshold (**discharge above the 10-year return period**).
2. Compare against **observed inundation** — SAR imagery, segmented wet/dry by a Gaussian mixture model, then classified by a Random Forest.
3. Accept the sparsity of the reference (Sentinel-1 revisit 12 days) and be explicit that many locations simply cannot be validated ("there are many locations in which we cannot validate the model").
4. Where reference data is absent, use **hydrologically similar nearby locations** — and disclose that this extrapolation added 30% more validated locations.

Four transferable lessons:
- **Name the event definition.** Our binary target is currently an inundation-depth threshold near 10 cm with rule-generated labels. That is a *proxy* label and must be described as one wherever the metric appears.
- **Prefer a held-out, temporally ordered evaluation** over a random split: flood data is strongly autocorrelated, so a random split leaks adjacent hours across train and test.
- **Report calibration, not just ranking.** A calibrated probability is the product's core promise whenever it drives thresholds; publish a reliability diagram and Brier score, not only ROC-AUC.
- **Disclose unvalidatable geography** rather than implying uniform skill.

> **Verdict — Adopt.** Add a `metrics` block to the training response carrying: split strategy, positive-class definition, prevalence, precision/recall/F1, ROC-AUC, **PR-AUC**, **Brier score**, calibration bins, confusion matrix, decision threshold, and a `validation_scope` string stating exactly which data was used. A small schema change that turns the README's candid limitations section into machine-readable honesty.

### 6.2 Why the current headline numbers must not be quoted as performance
The README already states that training metrics are **in-sample**, that the evaluation set is **synthetic**, that labels are **rule-generated** where observations are unavailable, that no real flood-event dataset is included, and that "these results demonstrate that the software pipeline runs successfully" and "do not establish operational life-safety accuracy". The audit adds that `/train/status` exposes no held-out score at all (X-10) and that `hotspots_mapped` is an arithmetic estimate, not a measurement (A-4).

> **Verdict — Adopt a hard claims policy** (enforced in `08-SDLC-DELIVERY-PLAN.md` §Claims): quote *in-sample* and *synthetic-holdout* numbers only with those qualifiers visibly attached; never present them as real-world accuracy; never present `hotspots_mapped` as a count of observed hotspots.

### 6.3 Statistical framing that earns technical credibility
Two framings consistently impress domain-fluent juries:
- **Temporal hold-out across monsoon seasons.** Train on monsoon seasons *k*, test on season *k+1* for the same city — the closest achievable thing to "would this have warned us last year?".
- **Detection-vs-lead-time trade-off.** Report the operating characteristic as a curve (probability of detection against lead time), turning the operator's threshold choice into an explicit policy decision rather than a model artefact.

> **Watch — high value, moderate effort.** Both are achievable with data the collector already downloads (10 years of hourly history) and need no new source.

---

## 7. Platform engineering — queue, cache, tiles, observability

### 7.1 Background work must leave the request path
The audit's D-2 and X-6 findings (blocking SMTP inside async handlers; startup retraining writing to ephemeral disk) share one root cause: **side-effecting work executing inline**. The established pattern for FastAPI services is a small task queue with a separate worker process — practically, an asyncio-native queue (ARQ/TaskIQ-class, Redis-backed) or a managed queue. Requirements that follow:
- **Idempotency keys** on every job (alert id, scan id) so a retry cannot double-send.
- **Visibility/timeout semantics** so a hung SMTP connection cannot hold a worker forever.
- **A dead-letter view** so failed deliveries are visible instead of buried in logs.
- **Single-scheduler ownership** (audit X-5) — a queue also removes the multi-worker duplicate-cron problem by making the scheduler a separate single-instance process.

> **Verdict — Adopt.** One queue, three job families (`scan`, `alert_dispatch`, `retrain`), single scheduler process, idempotency keys on all three.

### 7.2 Cache hierarchy and tiling
| Layer | Content | Suggested TTL | Rationale |
|---|---|---|---|
| Static terrain/soil/OSM | DEM, slope, soil, drainage, pumps per H3 cell | 30–365 days | effectively invariant; also the rate-limited fetches |
| Weather/nowcast | rainfall, forecast, soil moisture | 10–30 min | matches upstream update cadence |
| Hazard score | probability + depth per cell | 5–15 min | derived from the two layers above |
| Rendered vector tile | MVT per (layer, z/x/y, run-id) | per hazard run | turns N cell queries into 1 tile request |

Because H3 cells are a stable key, every layer above is a keyed lookup rather than a recomputation. That is the *performance* argument for §3.1, complementing the identity argument.

### 7.3 Observability — keep it cheap and visible
For an alerting system the cheapest credibility features are the most persuasive on stage: a real `/health` reporting dependency status (audit X-8), structured JSON logs with a request/trace id (the repo already lists `python-json-logger` in `requirements.txt` and never uses it), an alert-delivery audit trail (D-3), and a panel showing *last successful fetch per source* plus *model age*. A reviewer can tell in five seconds whether the system is alive and being fed.

> **Verdict — Adopt.** Structured logs + trace id, dependency-aware health, per-source freshness panel, alert audit table. Explicitly *reject* a full observability stack (Prometheus/Grafana/tracing backends) inside the hackathon window — it consumes time the map and the wiring need. *Watch* for post-hackathon.

### 7.4 Mobile-first delivery
Indian urban users access services predominantly on phones, often on constrained connections, sometimes during the very event that degrades connectivity. Cheap design consequences: keep hazard GeoJSON payloads within a few hundred kilobytes per view (tile- or bbox-scoped, simplified coordinates, quantised values); ship a **PWA that caches the last-known-good hazard view** so the app still shows the most recent state offline; keep the citizen flow to one screen. This is where the 10% *UX & Design* weight is actually won.

---

## 8. Legal, ethical and compliance constraints

### 8.1 Personal data — India's DPDP framework is now operative
India's Digital Personal Data Protection Act, 2023 is in force and its **enforcement Rules were notified in 2025** (MeitY, published in the Gazette as G.S.R. 846(E), November 2025) `[S-12]`. The moment the product collects a phone number, an email address, a location, or a vulnerability characteristic (elderly, disabled, pregnant), it is processing personal data and must respect purpose limitation, consent, storage limitation and the rights of data principals.

Design consequences, all cheap if designed in from the start:
1. **Consent capture at subscription**, stating the exact purpose (hazard alerts for the areas you choose) with an easy withdrawal path.
2. **Minimise and generalise location** — store the H3 cell of interest rather than continuous GPS traces for the citizen layer.
3. **Sensitivity labelling** — vulnerability flags are the most sensitive data in the system: restrict access, log every read, and never expose them in an alert payload or a public map layer.
4. **Retention policy** stated in the UI and enforced in code (e.g. delivery logs 90 days; location-of-interest until unsubscribe).
5. **Processor disclosure** — email/SMS/WhatsApp providers and any LLM provider are data processors and must be named in the privacy notice.

> **Verdict — Adopt.** A two-page privacy notice, a consent-record table, field-level minimisation, and an audited access path to sensitive fields. This is also a differentiator: most hackathon projects cannot answer "where is your consent record?".

### 8.2 Life-safety framing and the disclaimer
The README's existing disclaimer ("decision-support tool… not a certified early-warning system for life-safety use… use alongside official agency guidance") is correct and should be **retained verbatim** in the API description, the UI footer, and every alert footer. It is strategically useful: a system that visibly defers to IMD/NDMA cannot be accused of overclaiming, and the same positioning is what makes the CAP interoperability story credible.

### 8.3 Open-source and third-party acknowledgement
The rules require that third-party resources be appropriately acknowledged and that submitted work be original. Consequences: an explicit attributions surface naming Open-Meteo, GloFAS/Copernicus, SRTM/OpenTopoData, SoilGrids/ISRIC, OpenStreetMap contributors (`© OpenStreetMap contributors`) and any basemap provider; licence files for vendored assets; and a clear statement of which parts are new work versus pre-existing prior research.

---

## 9. Rejected and Watch-listed options, and the durability question

The brief asks which choices *survive*, not which are merely current. This table is the answer.

| Option | Decision | Reasoning that will still hold in three years |
|---|---|---|
| Deep-learning rainfall nowcasting (ConvLSTM / diffusion / transformer) | **Watch** | Strong upside, but needs radar sequences we do not have; the tree-ensemble pipeline already works and is explainable. Add only once radar ingestion exists. |
| Weather-foundation / global neural weather models | **Watch** | They improve the *forcing* input, not the urban inundation logic. Subscribe to better rainfall; do not rebuild around a model we cannot host. |
| Full 2D hydraulic modelling (HEC-RAS-2D class) on every cell | **Reject (runtime)** | Physically stronger but far too slow and too calibration-hungry for a 5-minute refresh. Keep the existing SCS physics blend; reserve 2D modelling for offline scenario libraries. |
| Raster-first architecture (COG + dynamic tiling) | **Watch → Adopt if raster layers arrive** | Excellent for continuous depth surfaces and offline scenario maps; unnecessary complexity while the product is cell/vector-shaped. |
| Vector-tile-first architecture (MVT / PMTiles) | **Adopt** | Cell-shaped data maps naturally to tiles; small mobile payloads; works with MapLibre with no key and no vendor lock-in. |
| Google Maps / Mapbox as the primary map stack | **Reject (primary)** | Keyed, metered, terms-bound. Acceptable as an optional municipal adapter. |
| `tile.openstreetmap.org` as the basemap | **Reject** | Policy permits withdrawal without notice and singles out commercial/donation-seeking services `[S-8]`. |
| Cell broadcast / public siren integration | **Watch** | Requires MNO and regulatory agreements; design CAP output so integration becomes possible later. |
| LLM as the risk engine (predicting flooding) | **Reject** | Non-deterministic, uncalibrated, unauditable. In an emergency system the LLM may only *phrase* verified numbers. |
| LLM as the briefing / composition layer | **Adopt with conditions** | High UX value for role-specific and multilingual advisories; must be number-locked and templated, with a deterministic fallback when the provider is unavailable. |
| Bhashini for Indian-language translation / ASR / TTS | **Adopt with conditions** | Government-backed and purpose-built for Indian languages — ideal for a PoC. Its own documentation states the APIs "shall be for the purposes of PoC only" with a paid version required for production, and the flow is pipeline search → config → compute `[S-13]`. Use it behind a translation interface, never inline in the alert path. |
| Kafka/NATS-class streaming infrastructure | **Reject (now)** | No throughput need at this stage; a queue plus a scheduler suffices. Revisit at multi-city scale. |
| PostGIS as the spatial store | **Adopt** | Boundary polygons, spatial joins, GiST indexes and statistics are unavoidable at municipal scale; a SQLite-only design cannot answer "hotspots in ward X". |
| Full observability stack | **Reject (now)** | Structured logs, health and a freshness panel deliver most of the value at a fraction of the time cost. |
| Serverless deployment | **Reject** | The product needs a scheduler, warm model state and background jobs — the README already reasons this way, and the evidence supports it. |

**The durability principle.** Every *Adopt* above is deliberately boring, standardised, replaceable technology (PostGIS, H3, MVT, CAP, a job queue, HTTP caching). Every *Watch* item is a capability that can be added **behind an interface** without disturbing the core. That is what makes a design survive contact with next year's model or next year's hackathon.

---

## 10. Source ledger

All sources retrieved **21 September 2026**. Type: **P** = primary (vendor / standards body / government), **S** = secondary (press / analysis).

| ID | Type | Source | What was taken from it |
|---|---|---|---|
| S-1 | P | Google Research blog — *An improved flood forecasting AI model, trained and evaluated globally* (11 Nov 2024) | 7-day lead time vs best nowcasts; 100 verified / up to 150 virtual-gauge countries; SAR + 10-year-return-period validation method; 12-day Sentinel-1 revisit and +30% validation via hydrologically similar locations; explicit statement that **flash, urban and coastal floods remain future work** |
| S-2 | P | Google Flood Hub support — *What is the Flood Forecasting API?* | Riverine-only scope; *Flood Status* (may include inundation maps) and *Hydrologic forecast* (7-day horizon, hour-to-day lead spacing); real + virtual HYBAS gauges; `qualityVerified` / `includeNonQualityVerified`; Inundation History and GRRR datasets |
| S-3 | P | Google Developers — *Flood Forecasting API* | Waitlist → approval → API key → enable in Cloud project; free under CC BY 4.0; country coverage list; feedback/meeting channel |
| S-4 | P | WMO Bulletin Vol. 74(2), Oct 2025 — *Leveraging CAP and Cell Broadcast for Early Warnings for All* (ITU, GSMA, OASIS, MeteoAlarm, **IMD**, WMO) | CAP as the multi-channel standard; ITU-T X.1303 bis (CAP 1.2); cell-broadcast reach and congestion resilience; recommendation to adopt CAP as a national standard; India SACHET and GSMA cell-broadcast references; "timely, accurate, actionable… reliable and accessible" framing |
| S-5 | S | Indian press reporting (2025) on municipal flood monitoring | Greater Chennai Corporation real-time flood forecasting through its Integrated Command and Control Centre; Gurugram MCG integrated command centre for urban flooding — evidence that ICCC-style command centres are the realistic municipal integration point |
| S-6 | P | Meta / WhatsApp Business Platform — *Pricing* documentation | Per-message pricing effective 1 July 2025; template categories; utility templates **free inside an open customer-service window**; free non-template messages in-window; 72-hour free-entry-point window; volume tiers; conversation-based pricing deprecated |
| S-7 | P | H3 (Uber) — *Tables of Cell Statistics Across Resolutions* | Res-8 ≈ 0.737 km² / 0.531 km edge; res-9 ≈ 0.105 km² / 0.201 km edge; min-max area spread ≤1.99×; cell count formula `2 + 120·7^r` |
| S-8 | P | OpenStreetMap Foundation — *Tile Usage Policy* | Mandatory UA/Referer, attribution, ≥7-day caching, no prefetch/offline/bulk download; best-effort with no SLA; blocking without notice; explicit warning to commercial and donation-seeking services; guidance to avoid hard-coded tile URLs |
| S-9 | P | Google Maps Platform — *March 2025 changes* | $200 monthly credit replaced by per-SKU free usage caps; Essentials/Pro/Enterprise categories; expanded volume discounts; Places API, Directions API and Distance Matrix API designated Legacy; India price-SKU examples |
| S-10 | P | India Meteorological Department — *API Reference* | Public endpoint inventory: city forecasts, district/station nowcast, current weather, AWS/ARG, district and subdivision warnings, district/state rainfall, river-basin QPF, radar, lightning, agromet, cyclone products; JSON format; no key documented for these endpoints |
| S-11 | P | Hydrology and Earth System Sciences and related literature (2022–2025) | Cry-wolf effects on social preparedness and EWS efficiency; simulation-based thresholds for issuing flash-flood warnings; causal effects of perceived false-alarm ratio on flood-warning response |
| S-12 | P | MeitY / Gazette of India — Digital Personal Data Protection Rules, 2025 (G.S.R. 846(E)) | Rules notified and operative under the DPDP Act 2023: consent, purpose limitation, storage limitation and data-principal rights now have enforcement machinery |
| S-13 | P | Bhashini (Government of India) API documentation | ULCA model repository; pipeline search → config → compute flow; ASR/NMT/TTS/OCR tasks; ISO-639 language codes; PoC-only usage statement with a paid production version |

**Repository-internal evidence** (cited as `[repo]`) is referenced by `file:line` in `02-CURRENT-STATE-AUDIT.md` and is not duplicated here.

### How to extend this ledger
Add a row for every new external dependency **before** it is integrated, with the licence and the specific claim it supports. This keeps the hackathon's acknowledgement requirement satisfied continuously and keeps the pitch deck's technical claims traceable to a source.








