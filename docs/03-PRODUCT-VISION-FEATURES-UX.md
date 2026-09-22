# 03 — Product Vision, Feature Catalogue and Experience Design

## 1. Positioning

**One line:** *From "where will it flood?" to "what should happen next, where, and in what order."*

The existing engine answers a **hazard** question. The product built here answers a **response** question, in the same breath and on the same map:

```
Hazard cell (H3, probability, depth)
      +  Who and what is inside it (population, roads, hospitals, schools, shelters)
      +  How reachable it currently is (road status, distance, capacity)
      +  What is already deployed (pumps, teams, barriers)
      =  A ranked, explainable ACTION, per audience, per channel
```

### 1.1 Why this is the right product (and not a re-badged predictor)
- Dossier §1 establishes that the world's leading flood-AI effort is **riverine and multi-day**, and names **urban flooding as future work** — the science gap is real.
- Dossier §5 establishes that warning systems primarily fail at the **response** stage (cry-wolf effects, warning thresholds, trust) — the product gap is real.
- The existing repository is strongest exactly where it is currently bypassed: the data collector, the feature pipeline and the ensemble. **Wiring those into a response surface is the highest-value work available.**

### 1.2 Naming and prior-work discipline
Recommendation: brand the *product* **FloodShield** while retaining the existing engine name for the hazard core, and state the relationship explicitly and early (see `08-SDLC-DELIVERY-PLAN.md` §Originality). This respects the originality rule while honestly declaring prior research — compliant *and* stronger than pretending there is no prior work.

---

## 2. Users

| Persona | Where they work | Core question | Success looks like |
|---|---|---|---|
| **Municipal EOC operator** (primary) | City Integrated Command and Control Centre, wall display | "Across the city, what needs attention in the next two hours, and what have we already dispatched?" | Ranked city list plus resource-gap view, refreshed every few minutes |
| **Ward officer** (primary) | Desk / phone | "What is my ward's status and what do I do first?" | One screen per ward: grade, hotspots, actions, contacts |
| **Field responder / SDRF-NDRF team lead** | Vehicle, phone | "Where exactly do I go, by which route, and is my destination still reachable?" | Route with hazard avoidance, destination card, offline-capable |
| **Citizen** | Phone | "Am I at risk, when, what do I do, where do I go?" | One screen, local language, actionable sentence, shelter map |
| **Facility administrator** (hospital, school, elderly care) | Desk | "Is my facility exposed, and what is my evacuation plan?" | Facility exposure card, plan, drill checklist |
| **NGO / community volunteer** | Phone | "Who in my area needs help first?" | Priority list with vulnerability-weighted ordering |
| **Analyst / researcher** (secondary) | Laptop | "Show me the data, provenance and uncertainty" | API, provenance fields, metrics, exports |

**Explicit non-user for this release:** the general public as an unauthenticated bulk audience. Citizen functionality is scoped to *subscribed cells* so consent, retention and personal-data handling (dossier §8.1) stay tractable.

---

## 3. Jobs to be done

1. **Pre-monsoon readiness (weeks→days):** *"Which wards are structurally vulnerable before any rain falls, so I can clear drains, service pumps and run a drill?"* → Ward A–F grades with component scores and the pre-positioning list that already exists (`services/predictor.py:111–136`).
2. **Active monitoring (hours):** *"The rain has started — which cells crossed my threshold, and what changed in the last ten minutes?"* → Live hotspot list with lifecycle tags and deltas.
3. **Decide and dispatch (minutes):** *"Rank my response targets, tell me why, and show me the route."* → Prioritised action queue with explanation and a reachability check.
4. **Warn (minutes):** *"Get the right message to the right people in the right language, once — and tell me it arrived."* → Alert object → channel fan-out → delivery and acknowledgement trail.
5. **Review (after):** *"What did we call, how did it compare with what happened, and what do we change?"* → Forecast-vs-outcome log feeding the claims policy.

---

## 4. Feature catalogue

Numbered `F-nn`, tagged **[W]** wards, **[H]** hotspots, **[M]** map, **[A]** alerts, **[P]** platform. `MUST` = required for the hackathon demonstration; `SHOULD` = post-hackathon; `COULD` = roadmap.

### 4.1 Hazard ingest and enrichment
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-01 | **Auto-enrichment of omitted inputs** — a request with only `lat`/`lon` fetches real terrain, soil, drainage and live meteorology instead of silently using defaults | MUST **[H][W]** | Fixes audit X-13; reuses the existing `DataCollector` |
| F-02 | Per-H3-cell static feature cache persisted to the database | MUST **[H][W][P]** | Converts rate-limited fetches into one-time work |
| F-03 | Live weather + GloFAS anomaly attached to every scan at run time | MUST **[H]** | The fix that makes hotspots respond to real storms (audit B-1) |
| F-04 | IMD district warning + district rainfall fetched as authoritative context | SHOULD **[H]** | Official framing alongside our output (dossier §4.1) |
| F-05 | Sentinel-1 / GRRR offline validation references | COULD | Validation work, not demo work |
| F-06 | Copernicus GLO-30 / FABDEM terrain upgrade | SHOULD | Highest-value single hazard-engine upgrade; licence review first |

### 4.2 Wards
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-10 | **Ward boundary ingestion into PostGIS** with explicit provenance (`osm` / `municipal` / `h3_agglomerated`) | MUST **[W]** | Fixes audit A-1/A-2 without pretending synthetic equals real |
| F-11 | **H3-cell agglomeration fallback**: a ward is a named cluster of res-8 cells with real geometry and real area | MUST **[W]** | Always available, honest, geometrically valid |
| F-12 | Ward-list endpoint independent of readiness scoring | MUST **[W][M]** | Wards must be drawable before they are scored |
| F-13 | Ward readiness recomputed from **real** per-cell features and the hotspots inside the polygon | MUST **[W]** | Fixes audit A-3/A-5 |
| F-14 | Ward exposure index from real population, building density, facility counts and drainage infrastructure | MUST **[W]** | Replaces `population_density/200 + building_density_pct` |
| F-15 | Hotspot→ward spatial join (`hotspot_count_in_ward`, worst cells, depth statistics) | MUST **[W][H]** | The most-asked municipal question; fixes audit A-4 |
| F-16 | Ward GeoJSON carrying readiness grade as a property | MUST **[W][M]** | Enables the choropleth layer |
| F-17 | Resource pre-positioning driven by grade **plus** ward size and current stock | SHOULD | Today's lists are static per grade |
| F-18 | Ward drill / readiness workflow (tasks, owners, completion, evidence) | COULD | Municipal operations layer |

### 4.3 Micro-hotspots
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-20 | **Real feature assembly per cell** (terrain cached, weather live) | MUST **[H]** | Audit B-1 — the single most important engineering fix |
| F-21 | **H3 identifier as the cell primary key** (res 8 default, res 9 micro mode) | MUST **[H][M]** | Audit B-3; stable across scans and centres |
| F-22 | **Hotspot objects**: contiguous clusters of qualifying cells with centroid, area, worst cell, depth statistics and dominant driver | MUST **[H][M]** | Audit B-2 — a ranked *place*, not a cell dump |
| F-23 | **Lifecycle and delta**: `new` / `persisting` / `intensifying` / `clearing`, with first-seen, last-seen and change since the previous run | MUST **[H][A]** | Makes the system feel alive; powers alert dedupe |
| F-24 | Severity classification combining probability, depth and persistence | MUST **[H][A]** | Depth matters, not probability alone |
| F-25 | Persistence of every scan run (run id, input hash, per-cell score, model version) | MUST **[H][P]** | Enables trend, audit, replay and an honest "hotspots mapped" |
| F-26 | Bounded scans: explicit cell budgets, clamped parameters, clear error when the budget is exceeded | MUST **[H][P]** | Audit B-4 |
| F-27 | Response shaping: bbox / limit / top-N / simplified geometry, plus a summary-only mode | MUST **[H][M][P]** | Audit B-5 |
| F-28 | Historical replay of a past event (choose a date; show the scan as it would have run) | SHOULD | Powerful demo and training asset |
| F-29 | Pluvial–fluvial compound indicator (high urban risk **and** high discharge anomaly) | SHOULD | Reuses the existing discharge features |

### 4.4 Map and visualisation
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-30 | **GeoJSON layer endpoints** for hotspots, clusters, wards, facilities, roads, shelters and pumps | MUST **[M]** | The integration contract for any external map or client |
| F-31 | **Vector-tile endpoint** (`/{layer}/{run}/{z}/{x}/{y}.mvt`) for city-scale rendering | MUST **[M][P]** | Keeps mobile payloads small (dossier §7.4) |
| F-32 | **MapLibre GL web client** with hazard layers, a time scrubber and a legend | MUST **[M]** | No API key; self-hosted basemap |
| F-33 | Cell inspector: click a cell → probability, depth, drivers, exposure, history sparkline | MUST **[M][H]** | The "why is this high risk?" answer on screen |
| F-34 | Layer toggles: probability heat, depth, hotspots, wards, facilities, shelters, roads, pumps, population | MUST **[M]** | Judges explore; operators focus |
| F-35 | **Change view**: show only what changed since the previous run | MUST **[M][H]** | Answers "what's new?" at a glance |
| F-36 | Facility and shelter layers with capacity and status | SHOULD | Requires the facility data model |
| F-37 | Route preview between two points with hazard avoidance | SHOULD | Depends on the routing workstream |
| F-38 | Offline / cached last-known-good view (PWA service worker) | SHOULD | Connectivity often fails during the event |
| F-39 | Scenario slider ("rainfall ×1.5") to show sensitivity | COULD | Excellent for drills and for the pitch |

### 4.5 Alerts and communication
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-40 | **`Alert` domain object** (id, hazard, severity, urgency, certainty, area, validity window, audience, instructions, source data) | MUST **[A]** | Separates *decide* / *compose* / *deliver* (dossier §2.4) |
| F-41 | **CAP 1.2 export** of every alert | MUST **[A]** | Interoperability with ICCC/SACHET-style aggregators (dossier §2.1) |
| F-42 | Audience-specific composition: citizen / responder / ward officer / municipal | MUST **[A]** | Different content, same verified numbers |
| F-43 | Multilingual composition with a deterministic fallback template | SHOULD **[A]** | Bhashini behind an interface (dossier §9) |
| F-44 | Channel dispatcher: email, webhook, SMS, WhatsApp — policy-driven by severity and audience | MUST **[A]** | Fixes the email-only default (audit D-8) |
| F-45 | **Dedupe + suppression windows** keyed on (cell/ward, severity) | MUST **[A]** | Anti-cry-wolf (dossier §5.1); audit D-4 |
| F-46 | **Delivery audit trail**, retry with backoff, dead-letter visibility | MUST **[A]** | Audit D-3 |
| F-47 | **Acknowledgement** ("seen") for responder recipients | MUST **[A]** | Turns a broadcast into a coordination tool |
| F-48 | Escalation: unacknowledged critical alerts escalate a tier after a timeout | SHOULD **[A]** | Municipal SOP-shaped |
| F-49 | Quiet hours / digest policy for low severity | SHOULD **[A]** | Anti-fatigue |
| F-50 | Subscription management with consent capture and unsubscribe | SHOULD **[A]** | DPDP (dossier §8.1) |
| F-51 | "Why this alert" appendix plus a deep link into the map view | MUST **[A][M]** | Closes the loop between map and alert |
| F-52 | Email hardened for deliverability: plain-text alternative, correct headers, aligned sender, allowlisted recipients | MUST **[A]** | Fixes audit D-1/D-6 |

### 4.6 Action intelligence (the differentiating layer)
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-60 | **Priority queue**: exposed population × hazard severity × criticality × accessibility, with a visible weighting breakdown | MUST | The core "so what?" output |
| F-61 | Resource-gap view: required per grade versus recorded as deployed | SHOULD | Municipal operations value |
| F-62 | Reachability check for critical facilities (is the route to the hospital still passable?) | SHOULD | Needs the road + hazard overlay |
| F-63 | Shelter recommendation with remaining capacity and a safe route | SHOULD | Needs the shelter layer |
| F-64 | Optimiser for assigning teams and shelters under capacity constraints | COULD | OR-Tools-class; depth for later judging rounds |
| F-65 | Post-event review: predicted versus reported, per event | COULD | Feeds calibration and credibility |

### 4.7 Platform, security and operability
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-70 | **Authentication + scoped API keys** with role separation (public read / agency read / operator write / admin) | MUST **[P]** | Audit X-1 |
| F-71 | Rate limiting and quotas per key and per endpoint | MUST **[P]** | Audit X-2 |
| F-72 | Parameter validation bounds on every numeric query | MUST **[P]** | Audit B-4 |
| F-73 | `/v1` versioned router with legacy paths retained as deprecated aliases | MUST **[P]** | Audit X-4 |
| F-74 | **Provenance block** (`data_sources[]`, `as_of`, `model_version`, `run_id`) on every hazard response | MUST **[P]** | Dossier §4.3 |
| F-75 | Dependency-aware `/health` and `/ready` | MUST **[P]** | Audit X-8 |
| F-76 | Structured JSON logs with request/trace id | SHOULD **[P]** | `python-json-logger` is already listed but unused |
| F-77 | Source-freshness panel (last successful fetch per input) | SHOULD **[P]** | A visible trust signal |
| F-78 | Persistent model store with a verified load path | SHOULD **[P]** | Audit X-6/X-7 |
| F-79 | Single-scheduler ownership (exactly one process runs cron) | SHOULD **[P]** | Audit X-5 |
| F-80 | Test suite in-repo plus CI on every push | MUST **[P]** | Audit X-9; protects everything above |
| F-81 | Alembic migrations for the surviving schema modules | SHOULD **[P]** | `create_all` will not carry the new schema |
| F-82 | Metrics block on the training response (PR-AUC, Brier, calibration, split strategy) | MUST **[P]** | Dossier §6.1 |

---

## 5. Experience design

### 5.1 Principles
1. **The map is the interface, not a page inside the product.** The landing view is the city with the current hazard run loaded; everything else is a panel.
2. **Never show a number without a meaning.** A probability is always paired with a severity band and an action sentence.
3. **Answer in three clicks or fewer.** Locate → inspect → act; `F-33` (cell inspector) and `F-60` (priority queue) are the two paths that must both be ≤3 interactions.
4. **Show the change.** A static map cannot express urgency; the change view (`F-35`) is what makes a forecast feel like a forecast.
5. **Show the age.** Every layer displays `as_of`, and stale data must look stale.
6. **One screen, one language, one action** for the citizen journey.
7. **Accessibility is a requirement, not polish** (WCAG AA target): colour-blind-safe severity ramp, never colour-only encoding (always icon + label + value), large hit targets, keyboard-navigable panels, text alternatives on the map.

### 5.2 The map screen (specification)
- **Base:** self-hosted vector basemap, muted (roads and water at low contrast) so hazard layers dominate.
- **Layers, in this z-order:** basemap → ward choropleth (readiness grade, ~40% opacity) → cell hazard hexes (probability or depth, quantised to five bands) → hotspot cluster outlines with labels → critical facilities (icons by type) → shelters (with capacity badge) → roads coloured by status where available.
- **Controls:** layer toggles; run selector (latest / previous / chosen historical run); time scrubber over the last 24 h; "changed only" switch; severity filter; search box (place name or lat/lon).
- **Legends:** one per visible quantitative layer with explicit units (probability 0–1; depth in metres; grade A–F).
- **Inspector (right panel, on click):** H3 cell id, probability, depth, severity, drivers with relative-contribution bars, exposure (population and facilities inside), lifecycle, previous-run delta, contributing data with per-source timestamps, and two actions — *Notify* and *Add to priority queue*.
- **Provenance footer:** model version, run id, input-source ages, disclaimer text, and `© OpenStreetMap contributors` where required.

### 5.3 The alert experience
**Severity vocabulary** — fixed, non-overlapping, used identically on the map, in email, SMS and webhooks:

| Band | Example trigger policy | Citizen instruction | Responder action | Suppression window |
|---|---|---|---|---|
| **ADVISORY** | probability ≥ 0.40, or ward grade C | "Be aware; avoid low-lying areas if rain continues." | Monitor; verify pump readiness | 12 h, digest only |
| **WATCH** | probability ≥ 0.65, or a HIGH hotspot with depth ≥ 0.2 m | "Prepare to move; keep vehicles out of underpasses." | Pre-position pumps and teams to the ward | 3 h |
| **WARNING** | probability ≥ 0.85, or depth ≥ 0.5 m, or a critical facility becomes unreachable | "Move to higher ground now; avoid these routes." | Deploy, open shelters, work the priority queue | 1 h |
| **EMERGENCY** | WARNING plus escalation, or multiple WARNINGs in one ward | "Evacuate now as directed." | Full mobilisation; request district support | 30 min; escalate if unacknowledged |

**Message content model (every channel, every audience):** hazard · location (human-readable name **and** cell id) · validity ("until HH:MM") · instruction · reason (top two drivers) · map deep link · confidence qualifier · issuer and disclaimer · alert id (for acknowledgement and dedupe reference).

**SMS constraint:** the instruction line plus a short link must fit in one 160-character segment; full content sits behind the link. **Email constraint:** actionable content visible without scrolling, technical detail below.

### 5.4 Onboarding a new city — the scalability experience
The failure mode that kills municipal products is "six weeks of data cleaning". The target flow is three steps and must be demonstrable: **(1)** pick a city or drop a boundary file; **(2)** confirm the auto-discovered parameter set (cells, wards, facilities, pumps) in one review table; **(3)** run the scan. Everything else — H3 cell generation, static-layer caching, facility discovery from OSM tags, ward agglomeration — is automatic and idempotent.

### 5.5 Explicit non-goals for this release
Stated so nobody builds them by accident: no hydraulic 2D modelling at runtime (dossier §9); no LLM-generated risk numbers; no unauthenticated public mass-broadcast channel; no native mobile app (the PWA covers the demo and the citizen journey); no paid map SDK in the critical path; and no claim of certified life-safety warning status anywhere in the UI.




