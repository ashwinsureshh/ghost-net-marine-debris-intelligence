# Hand-off prompt — for the next MacBook Air session

Written on the workstation, 2026-08-28. Paste the block below into the Air's
Claude Code session. Delete or overwrite this file once it is consumed — the
Status Log in `MACHINE-WORKFLOW.md` is the durable record, this is just the
paste buffer.

---

```
Continue the Ghost Net project. Read MACHINE-WORKFLOW.md — Status Log, top entries.
This is the MacBook Air (no GPU); verify with python scripts/check_machine.py.
PULL FIRST.

Since your console retheme (890985e), the workstation:
- Pulled it, fast-forward, no conflicts. Confirmed frontend-only; Python suite
  unchanged at 271 passed / 1 skipped after the merge.
- Added two 2026-08-28 Status Log entries (state check + merge check), commit
  8ecacb8. No Python or eval/ changes — nothing that conflicts with frontend work.

There is NO unblocked code work on either machine. FR-2.2, FR-3, FR-4, FR-5 and
FR-6.1 are all blocked on EARTHDATA_TOKEN / GFW_API_TOKEN and the Protected Planet
+ river-table downloads — all Ashwin's account work, none created yet. Do NOT
write speculative --oscar or fetch-script wiring that can't be tested without the
token (see the 2026-08-27 hand-off warning).

Work the credential-free deliverables instead, in this order:

1. CLOSE OUT THE RETHEME. Write its Status Log entry: what changed, tsc +
   frontend lint status, and browser verification (light + dark, down to 375px).
   890985e currently has only a commit message — the next session needs the
   context.

2. PRD §12 ABLATION WRITE-UP (graded, unwritten). The narrative for:
   - FR-2.4 verification ablation: precision 0.238 -> 0.623, F1 0.753, on real
     MARIDA (not synthetic, not a strawman baseline — literature thresholds).
   - FR-1.4 CNN detector: region recall 0.407 -> 0.703 held-out; and the finding
     that the CNN largely SUBSUMES the Verification Agent (+0.385 over FDI drops
     to +0.080 over CNN). Quote both numbers, never +0.385 alone once the CNN is
     the detector.
   - FR-2.2 multi-temporal: the MEASURED NEGATIVE — contributes nothing today,
     blocked on FR-3.1's missing current field. Report as a dependency, not a
     contribution. PRD §12 already records this as a measured exception to the
     "every agent is load-bearing" test; keep that framing.
   All numbers already live in eval/results.md and eval/*.json — this is prose
   over existing results, not new measurement.

3. EVIDENCE-TRACEABILITY DEMO (§12 bullet). Every number the console shows must
   trace back to an artefact or eval file. The console already renders
   provenance; this is scripting / documenting the walk-through an evaluator
   would follow.

4. REPORT + VIVA MATERIALS (graded, unstarted).

Rule from MACHINE-WORKFLOW.md that governs all of the above: no number reaches
eval/results.md that the person writing it cannot derive and defend.
```
