# Report completion outline — 21 September 2026

The updated [report draft](report-draft.md) replaces the old pre-release outline.
Use [guide progress summary](guide-progress-summary.md) for a brief update and
[viva pack](viva-pack.md) for questions and claim boundaries.

**[E]** committed evidence · **[W]** team writing/review · **[B]** external
validation outstanding. A completed implementation does not close an accuracy claim.

| Chapter | Status | Action |
|---|---|---|
| Introduction and scope | **[W]** | Review drafted objective and prototype framing |
| Related work | **[W]** | Add verified primary citations; no unsupported literature-count claim |
| Architecture and implementation | **[E]** | Draft covers six agents, artifact/API split and human review |
| Evaluation methodology | **[E]** | Retain sparse-label, within-tile and held-out selection limits |
| Measured results | **[E]** | Read JSON-backed findings in draft and eval/results.md |
| Regional demonstrations | **[E]** | Three real runs plus synthetic; Puducherry partial |
| Discussion and conclusion | **[W]** | Team reviews argument; preserve negative findings |
| External validation | **[B]** | Local labels, river-ranking comparison and vessel reference checks |
| Presentation and demo | **[W]** | Screenshots, final slides and manual direct-file offline check |

The outline does not draft a literature review or invent external validation.
The report draft supplies a technical narrative for team revision. GPU training
and large processing remain workstation tasks; document preparation needs neither.

Do not reuse the superseded claims that no real run exists, drift/latency are
unmeasured, GFW integration is unimplemented, or FR-2.2 awaits currents. Real
runs exist; a limited other-year drift check and degraded-run latency are measured;
GFW integration works for two regions; FR-2.2 is still inert after remeasurement.
The existing system ablation predates GFW and must retain that qualification.
