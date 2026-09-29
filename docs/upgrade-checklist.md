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
- [x] Backend reliability (PR #20): request IDs, JSON access logs, 413 body cap,
      consistent errors, /api/ready, atomic approval writes, file/sqlite backend.
      Fixed: a corrupt approval log used to be silently overwritten.
- [x] CI (PR #20): ruff, pytest, provenance, frontend typecheck/tests/build,
      Docker smoke. Green on GitHub, including the Docker job.

## Remaining product and delivery work

- [x] Navy palette/logo/sidebar motion reviewed (WCAG AA, finite motion) and
      committed separately (PR #23).
- [x] Accessibility QA (PR #25): 0 axe WCAG 2.1 A/AA violations in 8 states;
      keyboard, dialog focus, tablet pass. Screen readers/other browsers open.
- [x] Approval restart acceptance on real processes, both backends; corrupt log
      refused and untouched; storage limits in DEPLOY.md (PR #20).
- [x] Priority robustness panel in Plan (PR #24): measured artefact only, `stale`
      when the served run changed, states capacity/horizon measured at.
- [ ] Review requested agent/evaluation views against existing Research and Plan
      surfaces; extend those instead of rebuilding navigation unnecessarily.
- [x] README screenshots and architecture diagram (PR #26).
- [ ] Citations, final report and slides (writing; Mac/report owners).
- [x] Docker build and smoke (CI). Fresh static export + file:// opening: FIXED
      a blank page in Chrome/Edge (crossorigin module under null origin) (PR #24).
- [ ] Firefox/Safari and presenter-machine check of the offline copy.
- [ ] Deployed acceptance (needs authorization) and October 7–9 freeze/rehearsal.

## Research requirements still partial or unfulfilled

- [x] PR-AUC and candidate-level counts for strict holdouts (PR #22). Precision
      only boundable (unlabelled = unverifiable); MARIDA label "objects" are
      sparse fragments (101/105 under 3 px on 16PDC), so not object accuracy.
- [ ] Physically justified uncertainty-ensemble calibration, not just widening.
- [ ] Independent dated river-source labels and external GFW case-study validation.
- [ ] Additional ranking correlations/MRR only where the reference constitutes
      a meaningful comparison; shared-prior agreement cannot establish accuracy.
- [ ] Independent local labels for exported regions, including Puducherry.

External validation may remain a stated limitation at delivery. A requirement
that lacks evidence is not marked complete merely because its code exists.
Optional roles/PostgreSQL and global monitoring are not deadline commitments.
