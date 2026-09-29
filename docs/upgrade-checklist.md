# Upgrade delivery checklist — September 29

Target: October 10 research prototype and evidence package. This tracks the
original production-upgrade specification; experiment completion is not proof
of improved accuracy or production readiness.

## Completed and merged

- [x] Full-input ablation and end-to-end latency measurement.
- [x] Priority-weight sensitivity on three regional runs (research artifact).
- [x] Six strict geographic holdouts, excluding evaluation data from training,
      validation, class weights and normalization; precision/recall/F1, IoU/counts.
- [x] Time-varying current implementation and paired comparison: no consistent
      gain, so production remains unchanged.
- [x] Internal post-hoc radius calibration experiment, explicitly not a fitted
      physical uncertainty ensemble or independent validation.
- [x] River-prior ranking consistency comparison; explicitly not source accuracy.
- [x] Coverage navigation, clustered markers, lightweight run summaries, evidence
      panels, real/synthetic/partial labeling and human approval workflow.
- [x] Cross-platform evidence hashing and standalone CLI regressions.

## Active workstation work

- [x] Experimental temporal association using predicted location, uncertainty,
      spectral shape and size, compared on all four pairs (eval/temporal_matching.json).
      Baseline reproduced; experimental arm changed 0 rows. NULL result: the
      30-40 km drift envelope admits the whole scene. Not promoted.
- [x] Observational coverage recorded per row; absence is `inconclusive` unless
      the whole disk is clear water (none of 187 disks was, so no absence claimed).
- [ ] Backend reliability: request IDs/structured logs, bounded requests,
      consistent failures, readiness, safe approval writes and storage abstraction.
- [ ] CI for CPU-only Python checks, frontend tests/build, provenance and Docker.

## Remaining product and delivery work

- [ ] Review and commit local navy palette/logo/sidebar motion separately.
- [ ] Targeted accessibility, keyboard, contrast, reduced-motion and tablet QA.
- [ ] Approval durability/corruption/restart acceptance; document storage limits.
- [ ] Simplified priority robustness view and current measured/partial status in
      the console; do not manufacture runtimes or present offline activity as live.
- [ ] Review requested agent/evaluation views against existing Research and Plan
      surfaces; extend those instead of rebuilding navigation unnecessarily.
- [ ] README screenshots and architecture, citations, final report and slides.
- [ ] Docker build, fresh static export, manual file opening, deployed acceptance
      with authorization, and October 7–9 freeze/rehearsal.

## Research requirements still partial or unfulfilled

- [ ] PR-AUC and candidate-level counts for strict holdouts (current counts are
      pixel confusion counts; do not relabel them as detected objects).
- [ ] Physically justified uncertainty-ensemble calibration, not just widening.
- [ ] Independent dated river-source labels and external GFW case-study validation.
- [ ] Additional ranking correlations/MRR only where the reference constitutes
      a meaningful comparison; shared-prior agreement cannot establish accuracy.
- [ ] Independent local labels for exported regions, including Puducherry.

External validation may remain a stated limitation at delivery. A requirement
that lacks evidence is not marked complete merely because its code exists.
Optional roles/PostgreSQL and global monitoring are not deadline commitments.
