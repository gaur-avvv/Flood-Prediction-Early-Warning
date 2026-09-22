# 08 — SDLC and Delivery Plan

## 1. The delivery situation, stated plainly

| Fact | Consequence for process |
|---|---|
| Submission/jury window is **27 September 2026, 09:30–17:30 IST**; work starts 21 September | **6 calendar days.** The deadline is fixed, so *scope* must be the flexible variable. |
| Team size 1–6, interdisciplinary, possibly multi-country | Process must work with partial availability and asynchronous handovers, not full-time co-location. |
| Evaluation weighting: Innovation & Originality 25%, Technical Implementation 25%, Real-World Impact 20%, Feasibility & Scalability 15%, UX & Design 10%, Presentation & Demo 5% | The plan must protect *all six* dimensions, not just code. A missed demo costs 5%; an unbuilt map costs 10%; a credibility failure costs 25%. |
| The engine already works; the gap is wiring and presentation | This is an **integration and hardening programme**, not a research programme. The plan is optimised for verified increments. |
| A previously developed project is involved | Process must include an explicit originality/prior-work disclosure step (§11). |
| The repository contains no in-repo test suite or CI (audit X-9) | Verification infrastructure must be created early, or none of the later gates can be evidenced. |

---

## 2. Process model: hybrid Stage-Gate with Scrum mechanics

**Decision:** run a **Stage-Gate backbone** (fixed milestones with entry/exit criteria and evidence) filled with **Scrum-style increments** (short cycles, daily inspection, working software each increment).

**Why this hybrid rather than pure Scrum or pure waterfall:**
- *Why not pure waterfall:* the requirements for the map and alert UX cannot be fully specified before the first render is seen; design must emerge from inspection.
- *Why not pure Scrum:* a six-day horizon with a multi-country, part-time team cannot absorb "we did not finish the sprint"; the gates force a demonstrable, honest state at fixed points.
- *Why gates matter here specifically:* the two biggest risks (a judge discovering synthetic data, and an unauthenticated open mail relay) are *credibility and safety* risks, not feature risks. Gates with explicit exit criteria are how you guarantee they are closed before a public demo.

### 2.1 Cadence
| Ceremony | When | Duration | Output |
|---|---|---|---|
| Sprint 0 planning | D-6 morning | 60 min | Frozen scope for the window, owners, this plan's WBS confirmed |
| Daily standup | 09:30 daily | 15 min | Yesterday / today / blockers; updated board |
| Midday integration check | 13:30 daily | 10 min | Merge integrity: main branch builds and runs |
| **Demo-or-die** | 19:00 daily | 20 min | The increment is demonstrated from a *deployed* instance, not a laptop |
| Gate review | End of D-4, D-2, D-1 | 30 min | Gate pass/fail against explicit exit criteria (§5) |
| Retrospective | After each gate | 15 min | One process change for the next interval |

**Sprint length:** one day. With a six-day horizon, a daily increment is the only cadence that leaves room to recover from a bad day.

### 2.2 Gates and what each protects
| Gate | Timing | Exit criteria (must all hold) |
|---|---|---|
| **G0 — Baseline** | end of D-6 | Repo runs locally; `/health` real; CI executes the test suite; `/v1` aliases respond; no code path blocks the event loop |
| **G1 — Truth** | end of D-4 | AC-01 (live inputs change output) and AC-04 (enrichment + honest failure) pass; synthetic generators are unreachable from production paths |
| **G2 — Place** | end of D-2 | AC-05/AC-06 (wards real-or-labelled + hotspot join) and AC-07/AC-08 (layers + console inspectable) pass |
| **G3 — Signal** | end of D-1 | AC-09 to AC-13 pass (no relay, suppression, audit, CAP, no blocking); AC-14/AC-15 pass; submission artefacts complete |
| **G4 — Show** | D-0 | Rehearsed demo runs end-to-end twice from the deployed instance; fallbacks prepared; Q&A pack reviewed |

### 2.3 Artefacts the process produces
| Artefact | Owner | When |
|---|---|---|
| This plan + requirements + ADR log | Delivery lead | D-6 |
| Test suite in-repo with CI badge | Backend/QC | D-5 onward |
| API contract + OpenAPI examples | Backend | D-4 |
| Console + citizen view | Frontend | D-3 |
| Alert pipeline + CAP sample | Backend/Alerts | D-1 |
| Claims sheet (approved wording) | Comms | D-2 |
| Demo script + fallback plan | Comms/Delivery | D-1 |
| Video, deck, README refresh, attributions | Comms | D-0 |
| Gate evidence bundle (test output, screenshots, request ids) | Delivery lead | Each gate |

---

## 3. Team model and RACI

Roles (one person may hold several; the assignment matters more than the headcount):

| Role | Accountable for |
|---|---|
| **DL — Delivery lead / product owner** | Scope, gates, demo narrative, submission artefacts, stakeholder-facing quality |
| **BE — Backend engineer** | Enrichment, scanning, wards, alert pipeline, API contract, data model |
| **GS — Geospatial engineer** | H3, boundaries, clustering, tiles, spatial queries |
| **FE — Frontend engineer** | Console, citizen PWA, visual design, accessibility |
| **QC — Quality / ML verification** | Tests, metrics block, load tests, claims evidence |
| **CM — Communications** | Deck, video, claims sheet, attributions, demo script, Q&A pack |

RACI for the major decisions: **DL is accountable** for scope and gates; **BE/GS/FE/QC are responsible** for their workstreams; **CM is consulted** on every external-facing string; **all are informed** of gate results. A decision that changes a gate's exit criteria is DL's; a decision that changes a contract is BE+GS jointly, with DL consulted.

---

## 4. Working agreements

**Branching:** `main` is always deployable. Short-lived feature branches named `<task-id>-<slug>` (e.g. `T-04-enrichment`). Merge only via pull request.

**Commit convention:** `<type>(<scope>): <imperative>` with a reference to the requirement or task — e.g. `fix(wards): stop sin/cos synthesis, use enrichment (T-10, REQ-SCN-01)`. This is what makes the final submission's commit history readable as evidence of rigour.

**Pull-request checklist (template):**
- [ ] Linked task and requirement(s)
- [ ] Tests added or updated; CI green
- [ ] Acceptance criteria reproduced in the PR description
- [ ] Contract impact noted (new/changed field, endpoint, header)
- [ ] No secrets, no wildcard CORS regression, no silent defaults
- [ ] Provenance fields preserved

**Definition of Ready:** task has a named owner, an acceptance criterion, a stated effort, and declared dependencies.

**Definition of Done (per task):** code + tests + OpenAPI update + docstring + acceptance evidence recorded in the gate bundle. A task that only "works on my machine" is not done.

**Definition of Done (per increment):** the demo-or-die run from the deployed instance passes; if it fails, the day is red until it is green.

**Environments:** `local` (SQLite, enrichment allowed but stubbable) · `staging` (the Render/Railway service, single scheduler) · `production = staging` for the hackathon window. A separate "production" is deliberately *not* created for six days.

**Communication:** all decisions in writing in the team's single channel, summarised into the ADR log when they cross a module boundary. Time-zone handovers use the board, not memory.

---

## 5. Quality management

### 5.1 Test strategy (the pyramid, sized for six days)
| Layer | Target | Notes |
|---|---|---|
| Unit | Fast, pure logic: H3 helpers, severity bands, clustering, suppression keys, CAP rendering, score weighting | ~60% of tests; must run in < 30 s |
| Service | Enrichment against recorded fixtures (replay, not live calls); alert decision rules; scan assembly | recorded HTTP fixtures so tests are offline and deterministic |
| Contract | The 18 tests in `06 §7` against the running app | the gate evidence |
| Load | PT-01…PT-08 (the demo-path subset) | run on staging before G3 |
| Exploratory | FE/QC manual passes against the console | log defects as tasks |

**Testing rule for the existing engine:** the ML core is *trusted but verified* — the suite adds smoke tests around `predict`, `predict_bulk` and `nowcast` to guard the engine while it is being wrapped, rather than attempting to re-test the ensemble's internals.

### 5.2 Quality gates in code
- CI on every push: lint + type check + unit/service tests + the contract suite for changed areas.
- Coverage gate: 100% of *Must* requirements must have ≥1 test (REQ-NFR-MNT-01); overall line coverage is reported, not gated, because gating on a number invites gaming.
- Every response-model change must update OpenAPI examples, which the contract tests verify.

### 5.3 Release criteria (what "ready to submit" means)
All four gates green **or** an explicit, DL-approved scope cut recorded against the ladder in §8; the demo script rehearsed twice end-to-end; the submission checklist (§12) complete; and the claims sheet (§10) applied to every external string.

---

## 6. Work breakdown structure

Task ids are referenced from `04 §4` (traceability) and §7's calendar. `Effort` is in engineer-days at part-time intensity.

| ID | Task | Owner | Effort | Depends on | Acceptance |
|---|---|---|---|---|---|
| T-01 | `/v1` aliases + deprecation markers; structured error handler; request ids | BE | 0.5 | — | Legacy and `/v1` both respond; errors match `06 §4` |
| T-02 | `services/enrichment.py`: H3 lookup, static cache, live cache, provenance | BE | 1.0 | T-01 | AC-04 passes |
| T-03 | Route `/predict`, `/predict/bulk`, `/nowcast` through enrichment; strict mode | BE | 0.5 | T-02 | `missing_covariates` error path verified |
| T-04 | `services/spatial.py`: H3 helpers, bbox, simplification | GS | 0.5 | — | Unit tests green |
| T-05 | `services/scanner.py`: enumerate → enrich → batch-infer → persist run | BE | 1.0 | T-02, T-04 | AC-01 passes on staging |
| T-06 | `services/hotspots.py`: contiguity clustering, severity, hotspot objects | GS | 1.0 | T-04 | AC-02 (cluster part) passes |
| T-07 | Lifecycle computation against the previous run | GS | 0.5 | T-05, T-06 | AC-02 (lifecycle part) passes |
| T-08 | Scan budget + parameter bounds + response shaping | BE | 0.5 | T-05 | AC-03 passes |
| T-09 | `/v1/runs`, `/v1/cells/{h3}`, `/v1/hotspots` read endpoints | BE | 0.5 | T-05 | Run metadata and inspector payload served |
| T-10 | `services/wards.py`: boundary ingest (vendored dataset) + provenance | GS | 1.0 | T-04 | Real boundaries stored for the demo city |
| T-11 | H3 agglomeration fallback with labelled provenance | GS | 0.5 | T-10 | AC-05 fallback branch passes |
| T-12 | Ward readiness from real cells + hotspot join | BE | 0.5 | T-05, T-10 | AC-06 passes |
| T-13 | `/v1/wards` + `/v1/wards/readiness` with geometry | BE | 0.5 | T-12 | GeoJSON-renderable ward payload |
| T-14 | Stable ward ids across calls | GS | 0.25 | T-10 | REQ-WRD-04 test green |
| T-15 | `services/tiles.py`: MVT encoding + run-scoped caching | GS | 0.5 | T-05, T-10 | Valid MVT served |
| T-16 | Layer endpoints (`cells`, `hotspots`, `wards`) with bbox | BE | 0.5 | T-05, T-13 | AC-07 passes |
| T-17 | MapLibre console: layers, legend, run selector, toggles | FE | 1.5 | T-15, T-16 | City renders on a keyless basemap |
| T-18 | Cell inspector + change view + data-age badge | FE | 0.5 | T-17 | AC-08 passes |
| T-19 | Citizen PWA view: one screen, one language, one action | FE | 0.5 | T-17 | Usable at 360×640 |
| T-20 | Provenance block + source-health recording everywhere | BE | 0.5 | T-02 | REQ-ING-05 / REQ-DAT-06 verified |
| T-21 | `services/alerts.py`: alert object + decision rules | BE | 0.5 | T-05 | Alerts created from a run |
| T-22 | Suppression windows + persisted suppressions | BE | 0.25 | T-21 | AC-10 passes |
| T-23 | `services/compose.py`: audience rendering + CAP 1.2 | BE | 0.5 | T-21 | AC-11 passes |
| T-24 | `services/channels/`: email (off-loop, hardened) + webhook | BE | 0.5 | T-23 | AC-09 / AC-13 pass |
| T-25 | Delivery audit + retry + dead-letter | BE | 0.5 | T-24 | Attempt history retrievable |
| T-26 | Acknowledgement endpoint | BE | 0.25 | T-24 | AC-12 passes |
| T-27 | Subscriptions + consent records | BE | 0.5 | T-24 | Consent stored; withdrawal works |
| T-28 | `services/actions.py`: priority queue with exposed weights | GS | 0.5 | T-12 | REQ-ACT-01/02/03 |
| T-29 | Auth + scopes + rate limits + CORS fix + secret check | BE | 0.5 | T-01 | REQ-SEC-01…06 verified |
| T-30 | Alembic migrations + PostGIS enable + GiST indexes | BE | 0.5 | T-05 | `flood_events` created; joins indexed |
| T-31 | Real `/health` + `/ready`; single-scheduler lock; verified model load | BE | 0.5 | T-30 | AC-15 passes |
| T-32 | Metrics block on the training response (PR-AUC, Brier, calibration, split) | QC | 0.5 | — | REQ-QLT-02 verified |
| T-33 | Test suite + CI + the 18 contract tests | QC | 1.0 | all | Gate evidence generated |

**Critical path:** T-02 → T-05 → (T-12 ∥ T-15) → T-17 → T-18 → demo. A delay on T-02 or T-05 triggers the scope-cut ladder immediately, not silently.

---

## 7. Six-day calendar

### D-6 (21 Sep) — Baseline and wiring start
- Sprint 0 planning (60 min): freeze scope, assign the WBS, confirm accounts and deployments.
- **M0** applied: T-01, T-29 (auth/quota/CORS foundations), T-30, T-31, T-32, and the T-33 scaffold.
- Demo-or-die: current system on staging with a real `/health`.
- **Gate G0 exit.**

### D-5 — Enrichment and real single-point predictions
- T-02 and T-03 complete; T-04 and T-05 start.
- QC builds recorded fixtures; CM drafts the claims sheet.
- Demo-or-die: a `/v1/predict?lat&lon` call that returns real, enriched covariates with provenance.

### D-4 — Real scans; truth gate
- T-05…T-09 complete; FE starts T-15 on stubbed data.
- **Gate G1 (Truth) exit — AC-01 and AC-04 demonstrated live.**
- If G1 fails, the scope-cut ladder is invoked *tonight*, not tomorrow.

### D-3 — Wards and the map
- T-10…T-15 complete; T-17 starts; T-20 and T-21 start.
- Demo-or-die: the console renders wards + hotspots from a real run, with an inspectable cell.

### D-2 — Place gate; alerts begin
- T-16…T-18 complete; T-21…T-26 built; CM writes the deck.
- **Gate G2 (Place) exit — AC-05…AC-08 demonstrated.**

### D-1 — Signal gate; submission artefacts
- T-24…T-28 complete; load tests PT-01…PT-08 run; CM finalises deck, video and README.
- **Gate G3 (Signal) exit — AC-09…AC-15 demonstrated; submission checklist done.**
- Dress rehearsal 1.

### D-0 (27 Sep) — Show
- Dress rehearsal 2 (from the deployed instance, not a laptop).
- Fallback checks: recorded video renders, screenshots cached, a dry-run city pre-scanned, a failed-provider drill rehearsed.
- Submit by 09:00 IST; present in the jury window.
- **Gate G4 exit.**

---

## 8. Scope-cut ladder (pre-agreed, so a bad day does not become a bad product)

Cut from the bottom; every cut is recorded.

| Level | Drop | Demo still shows |
|---|---|---|
| L0 (full scope) | nothing | everything |
| L1 | PWA offline mode (T-19 reduced), scenario slider, IMD context | full map + wards + alerts |
| L2 | SMS/WhatsApp channels (keep email + webhook + CAP) | map + wards + alerts with CAP |
| L3 | Facilities/shelters layers, resource-gap view | map + wards + hotspots + email/CAP alerts |
| L4 | Priority queue (F-60) | real hotspots + wards on a map + hardened alerts |
| L5 | Ward readiness (keep ward geometry + hotspot join) | live hotspot map + alert pipeline |
| L6 (floor) | everything below L6 | **AC-01/AC-04: real single-point predictions + a real scan** — the honesty story |

**Rule:** never ship below L6. L6 is the minimum state in which the central claim — "the engine now answers from real data" — remains true.

---

## 9. Risk register

| ID | Risk | L×I | Mitigation | Trigger → action | Owner |
|---|---|---|---|---|---|
| R-1 | Enrichment is slower than budgeted, delaying the critical path | M×H | T-02/T-05 started D-5 with a second engineer on fixtures | G1 exit at risk → cut to L4 and double-shift BE | DL |
| R-2 | Boundary dataset for the demo city is unusable or unavailable | M×M | H3 agglomeration fallback exists by design (T-11) | Ingest QA fails → switch provenance to `h3_agglomerated` and show it in the UI as a feature | GS |
| R-3 | An upstream service rate-limits during a recorded run | M×M | Static cache + one live call per area + recorded-fixture demo mode | Freshness badge stale → run from the last good run and show the staleness deliberately | BE |
| R-4 | A judge probes the "99.45%" figure or `hotspots_mapped` | M×H | Claims policy (§10) plus the honest metrics block (T-32) | Q&A pack answer 4 used verbatim | CM/DL |
| R-5 | Live demo connectivity fails | M×H | PWA last-known-good view + pre-recorded video + cached screenshots | Wi-Fi check at T-30 min → switch to recording, state it | DL |
| R-6 | Team availability drops (time zones) | M×M | Async board, handover notes, no person is the sole owner of a gate | Standup absence → reassignment at midday check | DL |
| R-7 | Scope creep toward new ML work | M×M | Explicit non-goals (`03 §5.5`); DL blocks model-side work | Any model-side proposal → routed to the 90-day roadmap | DL |
| R-8 | Open relay discovery by a reviewer | L×H | T-29 in the first two days; abuse test PT-08 | Any external report → freeze dispatch, redeploy fix | BE |
| R-9 | H3 library learning curve slows GS | L×M | H3 API needed is five functions; a spike task on D-6 | Spike > 2 h → pair with BE | GS |
| R-10 | PostGIS provisioning fails on the host | L×M | SQLite fallback path with Python spatial joins documented | DB capability probe fails → fallback flagged, demo unaffected | BE |
| R-11 | Tuning thresholds makes the demo empty or noisy | M×M | Thresholds are configuration; a rehearsed scenario with a known outcome | Rehearsal D-1 fails → adjust config, not code | QC/DL |
| R-12 | Submitted claims conflict with the hackathon originality rule | L×H | §11 disclosure written D-1; CM signs off | Any deck/README text flagged → reword before submission | CM |

---

## 10. Claims policy

This policy is *binding* for the deck, the README, the demo script, every email/WhatsApp footer and every API response string.

### 10.1 Approved claims
- "A decision-support platform that connects hyper-local urban flood risk to people, infrastructure and response resources, and turns it into prioritised, explainable actions."
- "Hazard estimates use weather, river discharge, terrain, soil and infrastructure data from open sources; every value carries provenance and a data age."
- "The training metrics currently available are in-sample, with a synthetic holdout and rule-generated labels; they demonstrate the pipeline runs, and the platform makes that scope visible in every response via `validation_scope`."
- "Alerting is delivered over email, webhook and a CAP 1.2 export; SMS, WhatsApp and cell-broadcast distribution are designed for and are the roadmap."
- "The map and hotspot layers are computed from live inputs and persisted per run, so any answer can be traced to a run id and its input timestamps."

### 10.2 Forbidden claims (never appear anywhere)
- "99.45% accuracy" (or any in-sample/synthetic number) presented as real-world performance.
- "2,500+ hotspots mapped" or any number derived from `_estimate_hotspot_count`'s `area × 2.5` arithmetic, unless it equals a persisted database count.
- "Operational early-warning system", "certified", "government-grade", "scientifically validated".
- "Replaces IMD / NDMA / municipal warning systems."
- "Works in every city worldwide" (say instead: "designed to onboard a new city without code changes").
- Any claim that SMS, WhatsApp, cell broadcast or an LLM layer is *delivered* when it is only designed.

### 10.3 The honesty slide (required in the deck)
One slide, titled **"What we verified, and what we deliberately did not claim"**, containing: (1) the four gates and their exit criteria; (2) the in-sample/synthetic nature of the current model metrics with the new `validation_scope` field shown on screen; (3) the synthetic-generation defect found and removed in this programme (audit B-1/A-3, migration M6); (4) the open-relay defect found and fixed (audit D-1). This slide converts the project's two biggest weaknesses into its strongest evidence of engineering maturity — and it is the answer to the two hardest questions a technical jury can ask.

---

## 11. Originality and prior-work disclosure

The hackathon rules prohibit submitting previously developed projects as new work unless permitted. The compliant, and stronger, position:

1. **State the relationship explicitly.** One paragraph in the README, the deck and the submission description: *"FloodShield's hazard engine builds on a previously open-sourced research implementation (Bio-SentinelX). This submission adds an integration and response layer — real feature assembly, ward geometry, hotspot objects, spatial serving and an alerting pipeline — plus a product experience and contract that did not exist in the prior work."*
2. **Distinguish layers.** Mark the hazard engine as *prior research* and the response/UX layer as *new work* on the architecture diagram itself.
3. **Keep the new work materially new.** The four workstreams (wards, hotspots, map, alerts) plus the action queue are new scope, new code and a new API surface; that is what the repository history must show, and it is why this programme does not merely rename the engine.
4. **Be ready to show the diff.** The WBS's commit convention (§4) exists precisely so that "what did you build during the hackathon?" can be answered by `git log` between the baseline and the submission tag.
5. **Never let the deck imply the hazard engine was built in six days.** The compliance question is answerable in one sentence if it is prepared; it is fatal if it is improvised.

---

## 12. Submission checklist

- [ ] Repository: `main` builds and runs from a clean clone; `.env.example` documents every setting; `LICENSE` present (note: the README currently claims none exists while one is present in the tree — reconcile).
- [ ] Docs: `00–09` (this set) committed; README points at them; attributions page lists Open-Meteo, GloFAS/Copernicus, OpenTopoData, SoilGrids/ISRIC and `© OpenStreetMap contributors`.
- [ ] Evidence: the four gate bundles; CI badge green; the 18 contract tests' last passing output.
- [ ] API: `/docs` live on the deployed URL; the new layer and alert endpoints have examples.
- [ ] Product: deployed console URL; deployed citizen view URL; both recorded in the submission.
- [ ] Video: 3-minute demo recorded from the deployed instance (not a screencast of slides), with the change view and an alert acknowledgement visible.
- [ ] Deck: claims policy applied; the honesty slide present; the architecture diagram marks prior research vs new work.
- [ ] Legal: privacy notice published and reachable from the citizen view; consent record visible in a screenshot.
- [ ] Q&A pack (§13) reviewed by every presenter.

---

## 13. Demo script and Q&A preparation

### 13.1 Ten-minute demo, structured around the evaluation criteria

**Act 0 (0:00–0:45) — The problem, on a map.**
Open the console on the demo city. "Every urban flood system you have seen today predicts where it will flood. The operational question nobody answers is *what happens next, where, and in what order*." (Feasibility of the framing is established here, not in slides.)

**Act 1 (0:45–3:00) — The hazard is real.**
Run a scan. Show a hotspot forming. Click a cell → inspector: probability, depth, drivers with per-source timestamps. Toggle "changed since previous run". **Key line:** "Every number here names its source and its age. If a source failed, the map would show you that, not hide it." (Technical Implementation + claims credibility.)

**Act 2 (3:00–5:00) — The place becomes actionable.**
Switch to ward view; show a ward at grade D with its hotspot join (4 hotspots, worst depth 62 cm, 3,120 people exposed). Open the priority queue; expand one item's weights. (Innovation + Real-World Impact: this is the Risk-to-Action layer.)

**Act 3 (5:00–7:30) — The signal reaches people.**
Trigger alert evaluation. Show the alert object → the email that a ward officer receives (with the "why" appendix and the map deep link) → the **CAP 1.2 export** (this is the moment to say: "this is the standard Indian command-and-control centres and national aggregators consume"). Show the suppression record for the duplicate that was correctly *not* sent. Show the delivery audit and one acknowledgement. **Key line:** "We suppress more alerts than we send, and the system can prove it." (This is the slide nobody else has.)

**Act 4 (7:30–9:00) — Trust.**
Show `/v1/health` with real dependency states; the source-freshness panel; the metrics block with `validation_scope` visible; the honesty slide. (Feasibility & Scalability + the originality disclosure.)

**Act 5 (9:00–10:00) — Scale and vision.**
Onboard a second city live (three steps, §5.4 of the product doc) or show the recorded one. Close on: open data, no licence fees, municipal integration via CAP. (Scalability.)

### 13.2 Q&A pack — the twelve questions most likely to be asked, with prepared answers
1. **"Is this different from your existing GitHub project?"** → Yes; the hazard engine is prior research and is declared as such; the integration, response and product layer shown here is new work, and the git history between the baseline and the submission tag demonstrates it.
2. **"Where does the risk number come from?"** → Open a cell inspector; show the drivers with timestamps; then state the validation scope in one sentence, exactly as worded in §10.1.
3. **"What's your accuracy?"** → "Our training metrics are in-sample with a synthetic holdout — we show them with that qualifier, and we built the evaluation surface (split strategy, calibration, Brier) so a real holdout can be reported honestly. We do not claim operational accuracy today."
4. **"How is this different from Google Flood Hub?"** → "Google solves the river, seven days out, and explicitly lists urban floods as future work. We address the street, in the next two hours, and then wire it to who acts. We also consume riverine data as an input." (Dossier §1.)
5. **"What happens when your weather source fails?"** → "It degrades loudly: last-good values with a stale badge, or a refused prediction. We never fabricate a number." Show the degradation matrix row.
6. **"How do you avoid crying wolf?"** → Show the suppression record and the severity bands; cite the cry-wolf evidence (dossier §5.1) in one line.
7. **"Can anyone trigger an email from your API?"** → "No — and we found and fixed exactly that flaw in our own system during this programme." Show the authenticated, allowlisted dispatch and the abuse test.
8. **"How does a government actually consume this?"** → "CAP 1.2 export and signed webhooks — the same standard the Indian public-warning ecosystem is built around." (Dossier §2.)
9. **"What about people without smartphones?"** → "We design the alert geometry for cell broadcast and defer to official channels for mass reach; we do not pretend to be a carrier."
10. **"How does it scale?"** → "A new city needs no code: boundaries, a config, one scan. The six-day path and the 90-day roadmap are both in the docs." Show the onboarding flow.
11. **"Where's the personal data going?"** → "Consent captured at subscription, location stored at cell granularity, vulnerability flags scope-gated and access-logged, with a withdrawal link in every message." (Dossier §8.1.)
12. **"Why should we trust you?"** → "Because the system is built so that every number, every alert and every claim can be traced — and because the first thing we built was the ability to show you what we *cannot* yet claim."

### 13.3 Fallback plan
If connectivity or a provider fails: switch to the pre-recorded video **and say so** — "this is the recorded run; the live system would behave identically" — then show the last-good run on the console's cached view. A rehearsed, honest fallback scores better than a silent failure, and it is itself a demonstration of the product's resilience story.

---

## 14. Post-hackathon 90-day roadmap

The six-day window ships the integration layer. The next ninety days convert it into an operational platform. Each phase has a gate; nothing moves on without evidence.

### Phase 1 — Weeks 1–3 (Harden)
- IMD district warnings and rainfall integrated as context (F-04).
- Sentinel-1/GRRR offline validation references wired into the metrics pipeline (F-05).
- Temporal hold-out evaluation implemented and reported (REQ-QLT-03).
- SMS channel live with DLT registration; WhatsApp utility templates live (F-44 complete, F-50 complete).
- Escalation + quiet hours (F-48, F-49).
- Multi-city configuration; the first non-demo city onboarded.
- Gate: a second city passes AC-01–AC-15 without code change.

### Phase 2 — Weeks 4–7 (Exposure and action)
- Facility and shelter layers (F-36) with OSM-tag discovery plus a municipal upload path.
- Reachability checks (F-62) and shelter recommendation (F-63).
- Compound pluvial–fluvial indicator (F-29) using the discharge features already present.
- Copernicus GLO-30/FABDEM terrain upgrade, after the licence review (F-06).
- Radar-based short-range rainfall extrapolation evaluated as an input, not a promise (dossier §9).
- Gate: a full drill scenario runs end-to-end with two audiences and a recorded post-event review.

### Phase 3 — Weeks 8–13 (Operationalise)
- Constrained resource allocation optimiser (F-64) behind the action API.
- Post-event forecast-vs-outcome review loop feeding calibration (F-65, REQ-QLT-07).
- Bhashini multilingual composition in production behind the translation interface (F-43), with the PoC/production terms handled.
- Drill/readiness workflow for wards (F-18).
- ICCC-style integration pilot with one municipal partner (dossier §2.1).
- Google Flood Forecasting API integration if waitlist approval has landed (dossier §1.3).
- Gate: an external municipal review of the audit trail, the claims discipline and the DPDP posture.

---

## 15. Post-delivery review (run within one week of the deadline)

Record, do not judge in the moment:
- Gate pass/fail history and what caused each failure.
- WBS effort estimates versus actuals (this is how the next hackathon's plan gets better).
- The scope-cut decisions taken and whether they were the right ones.
- Load-test distributions versus targets (`07 §5`).
- Demo outcome: which acts landed, which questions were asked that were *not* in the pack.
- The claims policy's compliance: any string that had to be corrected.
- The roadmap items that should now be re-prioritised based on what the jury actually valued.

The output of this review updates `09-ADR-DECISION-LOG.md` and becomes the baseline for the post-hackathon phase.







---

## Sprint 0 / Gate G0 — Status (2026-09-22)

**G0 PASSED.** All tasks complete:

- **T-01** Structured error envelope + X-Request-ID middleware (`utils/errors.py`, `utils/request_id.py`).
- **T-02** Real-data enrichment (`services/enrichment.py`): TTL caches (static 7d / live 5min / discharge 1h), H3 indexing, field provenance, rainfall window aggregation, batched SRTM grid elevation; synthetic feature generation removed from `predictor.py`; scan budget (`MAX_SCAN_CELLS=6000` → `400 budget_exceeded`).
- **T-29** API-key auth + per-scope sliding-window rate limits (`security/auth.py`); production refuses boot without keys; env-driven CORS.
- **T-30** Alembic migrations scaffold + initial schema revision.
- **T-31** DB leader election for scheduler (`utils/scheduler_lock.py`), model artefact SHA-256 integrity, `/ready` endpoint.
- **T-32** Training metrics: time-ordered holdout, PR-AUC/Brier/ECE + calibration table in `GET /train/status`.
- **T-33** 19-test pytest suite + GitHub Actions CI (`.github/workflows/ci.yml`). All tests green.

Known placeholders: `EnrichedPredictionResponse.instruction` duplicates `recommendation` (pending copy); legacy routes sunset **2026-09-30**.
