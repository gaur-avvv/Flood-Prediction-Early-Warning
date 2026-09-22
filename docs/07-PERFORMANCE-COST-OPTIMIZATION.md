# 07 — Performance, Optimization and Cost Model

## 1. Capacity model (the arithmetic that drives every optimisation)

Assumptions: a metropolitan area of ~700 km², res-8 cells (0.737 km² average), 15-minute refresh, one scan run per interval.

| Quantity | Calculation | Result |
|---|---|---|
| Cells per city scan | 700 ÷ 0.737 | **≈ 950 cells** |
| Cells per large/dense city | 1,200 km² ÷ 0.737 | ≈ 1,630 cells |
| Micro-resolution cells for one hotspot cluster | 10 km² ÷ 0.105 | ≈ 95 cells |
| Scans per day | 24 h × 4 | 96 |
| Cell-scores stored per day | 950 × 96 | **≈ 91,000 rows/day** |
| Cell-scores per 30-day retention | 91,000 × 30 | ≈ 2.7 M rows |
| Row size (scores + small driver JSON) | ~250 B | ≈ 690 MB/month if fully retained |
| Static cell cache rows | one per cell ever seen | ~12k rows for 10 cities — trivially small |
| External live calls per scan | 1 weather + 1 discharge (+1 reverse geocode, cached) | **≈ 2–3 per scan**, not per cell |
| External static calls per cell | 4 (DEM / soil / drainage / water) | one-time per cell, then cached forever |
| Model inferences per scan | 950 | one batched call |
| Client payload per city view | vector tiles for the viewport | tens of KB vs ~2 MB of cell JSON |

**The two numbers that matter.** The current design makes *(cells × 5+)* external requests and *(cells)* synthesised feature vectors per scan. The target design makes **2–3 live requests per scan** and reuses a static cache filled once. That is a two-orders-of-magnitude reduction in upstream pressure — and it is what makes a 15-minute city sweep on a small container realistic.

**Storage policy:** keep per-cell scores for 7 days at full resolution, hotspot objects for 90 days, run metadata indefinitely; older cell scores roll up into an hourly hotspot-severity series. This bounds growth while preserving the trend curves the product displays.

---

## 2. Latency budgets

### 2.1 Single-point prediction (warm cache)
| Stage | Budget |
|---|---|
| Auth + validation | 5 ms |
| H3 lookup + static cache read | 5 ms |
| Live cache read | 5 ms |
| Feature vector assembly | 10 ms |
| Batched model inference (n=1) | 120 ms |
| Driver computation | 20 ms |
| Serialisation + provenance | 10 ms |
| **Total p95 target** | **≤ 400 ms** (REQ-NFR-PERF-01) |

### 2.2 City scan (950 cells)
| Stage | Budget | Note |
|---|---|---|
| Cell enumeration | 0.2 s | pure CPU via the H3 library |
| Static cache reads | 1.0 s | one indexed query returning ~950 rows |
| Live attach | 3.0 s | 2 external calls; network-dominated |
| Feature frame assembly | 1.0 s | single vectorised construction |
| Model inference | 8–20 s | batched; the dominant cost |
| Clustering + lifecycle | 0.5 s | in-memory graph over H3 neighbours |
| Persistence (bulk) | 2.0 s | one bulk insert, not row-by-row |
| **Total** | **≈ 16–28 s** | meets REQ-NFR-PERF-03/04 with headroom |

### 2.3 Where the current implementation loses time
| Current behaviour | Cost | Fix |
|---|---|---|
| `build_feature_vector` builds a `pandas.DataFrame` **per row**, concatenated for bulk (`feature_engineering.py:42–134`) | DataFrame construction dominates at thousands of rows | Build one dict-of-lists for the whole batch, then a single DataFrame; keep the single-row path for n=1 only |
| Grid features synthesised per cell in Python | `sin`/`cos` per cell per scan | Remove entirely; read from the static cache |
| Model predicts in chunks of 100 (`predictor.py:236–239`) | ~10 inference calls for 950 cells, each with fixed overhead | Chunk at 500–1000 |
| Reverse geocode on every ward call (`predictor.py:399–409`) | 0.3–5 s plus rate-limit risk | Cache by rounded H3 cell with a long TTL; move off the critical path |
| `_save_observations` writes row-by-row | N round trips | Bulk upsert |
| Depth mask recomputed after prediction | minor but free to remove | Reuse the mask array |

---

## 3. Optimisation strategy, ranked by benefit ÷ effort

| Rank | Optimisation | Benefit | Effort | Risk |
|---|---|---|---|---|
| 1 | **Static feature cache** keyed by H3 | Eliminates nearly all upstream calls and all synthesis | M | Low |
| 2 | **One live fetch per area, applied to all cells** | Turns per-cell network cost into per-scan | S | Low |
| 3 | **Single batched feature frame + batched inference** | Largest CPU win; removes pandas-per-row overhead | S | Low |
| 4 | **Immutable runs + aggressive caching** | Makes layer and tile reads O(1) and CDN-able | S | Low |
| 5 | **Vector tiles instead of cell JSON at city scale** | Payload reduced ~50–100×; the difference between usable and unusable on mobile | M | Medium |
| 6 | **Quantised tile properties** | Further payload reduction with no loss of decision value | S | Low |
| 7 | **Spatial indexes (GiST) + bbox queries** | Ward joins and layer queries stop being full scans | S | Low |
| 8 | **Bulk persistence per run in one transaction** | Faster runs and atomic runs (no half-written state) | S | Low |
| 9 | **Connection-pool tuning / read scaling** | Headroom for concurrent console + API users | M | Medium |
| 10 | **Precomputed hourly hotspot series** | Instant trend views; bounds storage | M | Low |
| 11 | **Response compression + `fields=` projection** | Mobile bandwidth win | S | Low |
| 12 | **Tile pre-warm for the demo city** | Guarantees fast first paint on stage | S | Low |

### 3.1 Deliberately rejected optimisations
- **Caching the whole city hazard score as one blob.** Tempting, but it makes partial invalidation and per-cell queries impossible and destroys the ability to answer "what changed in *this* cell?".
- **Aggressive cross-process in-memory caching.** With more than one worker this silently produces divergent views of the same run. Persisted runs remove the need entirely.
- **Micro-batching with artificial latency.** Adding queue delay to "improve throughput" is the wrong trade for a system whose value is measured in lead time.
- **Precomputing every city at every resolution.** Combinatorial storage cost with no user demand — runs are on demand and cached.

---

## 4. Cost model

### 4.1 Demonstration path (the number that matters for the hackathon)
| Item | Cost |
|---|---|
| Open-Meteo (weather, archive, forecast) | Free |
| Open-Meteo Flood API / GloFAS | Free |
| OpenTopoData (public SRTM) | Free (rate-limited; cached) |
| SoilGrids REST (ISRIC) | Free |
| OSM Overpass | Free (rate-limited; cached) |
| Administrative boundaries (OSM-derived / vendored) | Free with attribution |
| Basemap (self-hosted vector) | Free |
| Hosting (existing service) | Existing subscription |
| Database (existing Postgres) | Existing subscription |
| **Recurring third-party cost for the demo** | **≈ 0** (REQ-NFR-CST-01) |

This is a genuine competitive position and should be stated plainly: *the product runs a city-scale flood-nowcast loop every 15 minutes on open data with no licence fees.*

### 4.2 Scale-out cost drivers (for the municipal business case)
| Driver | Unit | Notes |
|---|---|---|
| Compute | container hours | Scales with cities × frequency × cells; the static cache keeps each additional city cheap |
| Database | GB-month | Dominated by per-cell scores; the §1 retention policy is the control lever |
| SMS | per message | Domestic termination fees; DLT-style sender registration required in India |
| WhatsApp | per delivered template | Utility templates free inside an open customer-service window; volume tiers lower utility/auth rates (dossier §6) |
| Email | effectively free | Deliverability, not cost, is the constraint |
| Translation (if enabled) | per character or project | Bhashini's public APIs are documented as PoC-only with a paid production tier (dossier §9) |
| LLM briefings (if enabled) | per token | Bound it: one briefing per alert, short prompts, cached template reuse |

**Cost-per-alert formula — implement, do not estimate.** Every delivery row records `channel` and a `unit_cost` snapshot, so the monthly cost report is simply `SUM(unit_cost) GROUP BY channel`. The business case is then computed from real traffic rather than from a static assumption (REQ-NFR-CST-02).

**Cost-control rules:** (1) one briefing per alert, never per recipient; (2) translate once per (alert, language) and reuse for all recipients; (3) digest low severity instead of instant delivery; (4) suppress duplicates *before* they reach a paid channel.

---

## 5. Load and performance test plan

| Scenario | Setup | Pass criteria |
|---|---|---|
| PT-01 Point latency | 200 sequential `/v1/predict` with warm cache | p95 ≤ 400 ms |
| PT-02 Point cold | 20 `/v1/predict` with enrichment on fresh cells | p95 ≤ 6 s; no >15 s outliers recorded as errors |
| PT-03 City scan | 5 consecutive scans at 950 cells, cache warm | each ≤ 30 s; zero duplicated external calls across scans (measured) |
| PT-04 Concurrent reads during a scan | 20 req/s on layer endpoints while a scan runs | read p95 ≤ 250 ms, no starved request (proves the scan is off the event loop) |
| PT-05 Tile burst | 300 tile requests across a viewport | p95 ≤ 250 ms; bounded cache warm-up |
| PT-06 Alert fan-out | 1 alert → 250 recipients across email + webhook | all recorded; completion ≤ 120 s; zero duplicates |
| PT-07 Hang simulation | SMTP stub that never returns | read endpoints unaffected (AC-13) |
| PT-08 Abuse | Unauthenticated bulk dispatch attempt; oversized scan request | both rejected, no email sent, no CPU spike (AC-03, AC-09) |
| PT-09 Retention | Purge job against a synthetic 90-day dataset | completes inside the maintenance window; storage back within budget |
| PT-10 Cold start | Fresh container, empty disk cache | read endpoints healthy ≤ 60 s while training runs (REQ-NFR-REL-05) |

**Instrumentation requirement:** every test publishes the distribution (p50/p95/p99) **and** the count of external calls, because a latency win bought with extra upstream calls is not a win.

---

## 6. Optimisation backlog for the post-hackathon phase

| Item | Why it is deferred |
|---|---|
| Read replicas and query caching at the DB layer | Not needed below ~50 concurrent users; adds moving parts before the demo |
| Asynchronous tile pre-generation for all zooms | Only the demo city needs pre-warming now |
| Columnar archival (Parquet) for historical runs | Row-store retention is sufficient at current volume |
| GPU/ONNX inference path | The tree ensemble is fast enough on CPU; revisit only if model complexity grows |
| CDN in front of tiles | The run-scoped `Cache-Control` already gives browser and proxy caching |
| Client-side hex aggregation for very wide views | Server-side roll-up to res 7 handles this more predictably |


