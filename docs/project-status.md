# GhostNet — project status

One page, for the team and the supervisor. Updated 2026-09-06 on the
workstation, at commit `e2fa0e9`.

Legend: **✅ done and measured** · **🟡 partial** · **❌ not started / blocked**

---

## 1. Acceptance criteria (PRD §12) — 2½ of 6

| # | Criterion | | Note |
|---|---|---|---|
| 1 | Six-agent pipeline end-to-end on a real region → ranked plan | 🟡 | **Ran on real data for the first time today.** 3 of 6 agents on real inputs, 3 degraded for want of data |
| 2 | Detection + verification benchmarked, documented improvement | ✅ | Precision 0.238 → **0.623**, F1 0.385 → **0.753** on held-out MARIDA |
| 3 | Drift vs NOAA drifter paths, error metric | ❌ | **Unblocked today** — needs a harness script, ~2 h |
| 4 | Attribution vs Ocean Cleanup; dark vessel vs GFW | ❌ | Needs 1 download + 1 unwritten client |
| 5 | Ablation: each agent's removal degrades output | 🟡 | Verification ablation measured on real data; system-level only on synthetic |
| 6 | Every output traceable to its evidence | ✅ | Enforced by `python -m ghostnet.provenance`, not just documented |

---

## 2. Agents

| FR | Agent | | Evidence |
|---|---|---|---|
| FR-1.1 | Sentinel-2 ingestion | ✅ | Streams COGs from a public STAC catalogue, no credential |
| FR-1.2–1.3 | Spectral-index detection | ✅ | Region recall 0.407 on MARIDA test |
| FR-1.4 | CNN detector | ✅ | Region recall **0.703**; 7.6× fewer candidates |
| FR-2.1, 2.3 | False-positive checks + reasons | ✅ | 5 checks, per-detection reason text |
| FR-2.2 | Multi-temporal consistency | ✅ | **Measured negative** — see §4 |
| FR-2.4 | Before/after precision-recall | ✅ | The headline result |
| FR-3.1–3.3 | Drift, backward/forward + envelope | ✅ | Code done; **validation** is criterion 3 |
| FR-4.1–4.2 | Source attribution | 🟡 | Code + tests done, no river table |
| FR-5.1–5.3 | Dark-vessel correlation | ❌ | `vessels.py:232` is `NotImplementedError` |
| FR-6.1 | Priority score | 🟡 | Runs; ecological-risk component dropped without MPA data |
| FR-6.2–6.4 | Capacity plan, rationale, human approval | ✅ | Including the FR-6.4 named-reviewer gate |

---

## 3. What is left, in priority order

| | Task | Owner | Blocked on | Effort |
|---|---|---|---|---|
| 1 | Download **Protected Planet** (WDPA marine) + run `build_region_extracts.py mpa` | Ashwin | a web form | 30 min |
| 2 | Download the **Meijer 2021 river table** + run `build_region_extracts.py rivers` | Ashwin | a download | 30 min |
| 3 | Write `scripts/eval_drift.py` — closes criterion 3 | A | nothing | ~2 h |
| 4 | Implement `vessels.sar_detections()` — closes FR-5 | B | nothing (token exists) | ~4 h |
| 5 | Re-export a full real run once 1–4 land | Ashwin | 1, 2, 4 | 1 h |
| 6 | System-level ablation on real inputs | Ashwin | 5 | 1 h |
| 7 | **Write the report** | all | outline exists, prose does not | days |
| 8 | Deploy the console to a URL | Ashwin | a Render account | 30 min |

**Both API tokens now exist and are verified.** Credentials are no longer the
bottleneck; items 1, 2, 4 and 7 are.

---

## 4. Three results that must be quoted correctly

1. **Verification gain and region recall are always quoted together.**
   +0.385 precision alone implies the system finds nearly all the debris. It
   lands on 96 of 236 annotated regions. A test enforces this at the API.

2. **Region recall 0.703 is a *within-tile* number.** MARIDA splits by patch,
   so 91% of test patches sit on tiles the model trained on. On a genuinely
   unseen region the cost is **−0.072 F1**, almost all recall.

3. **FR-2.2 is a measured negative, not a contribution.** With a real current
   field its harm disappears (6 false rejections → 0) but its contribution is
   still exactly zero, and the cause is now named: nearest-neighbour matching
   means the transient never fires. PRD §12 records it as a measured exception
   to "every agent is load-bearing".

Full detail in `eval/results.md`; the defence of each is in `docs/viva-pack.md`.

---

## 5. Data and machines

| Dataset | | Needed for |
|---|---|---|
| MARIDA | ✅ workstation | benchmarking |
| OSCAR currents | ✅ workstation | drift |
| Drifter tracks | ✅ workstation | drift validation |
| Rivers | ❌ | FR-4 |
| Protected Planet | ❌ | FR-6.1 |
| GFW | ❌ | FR-5 |
| Sentinel-2 | n/a | streamed, no local copy needed |

Workstation = GPU, MARIDA, model training, real exports.
MacBook Air = agents, console, docs. **Never assume the other machine's files
are here** — run `python scripts/fetch_data.py --status`.

Both machines: `git pull` before starting, push before stopping. The Status Log
in `MACHINE-WORKFLOW.md` is the source of truth, not chat history.

---

## 6. The rule that governs the whole project

> No number reaches `eval/results.md` that the person who produced it cannot
> derive and defend.

An examiner asking "why is region recall 0.703?" is asking the person, not the
tool.
