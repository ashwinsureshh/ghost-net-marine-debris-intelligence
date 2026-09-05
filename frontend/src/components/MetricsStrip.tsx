import { AlertTriangle, ChevronDown, FlaskConical, Info } from "lucide-react";
import type { ReactNode } from "react";
import type { BenchmarkReport, RunArtefact, RunSummary } from "@/lib/types";
import { Badge } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/**
 * The run-level metrics strip.
 *
 * Two groups of numbers sit side by side, and the whole point of the component
 * is that they never blur into each other:
 *
 * 1. **This run** — counts read straight off the loaded artefact.
 * 2. **Measured on MARIDA** — the Verification Agent's precision gain and the
 *    detector's region recall, from `eval/results.md`. These describe the
 *    *system*, on a held-out benchmark, not the region on screen.
 *
 * Region recall is here because of a specific way the precision gain misleads
 * on its own: precision and recall are conditioned on candidates the detector
 * emitted, so baseline recall reads 1.0 by construction. Show only the gain and
 * a reader concludes the system finds nearly all the debris; it lands on 96 of
 * 236 annotated regions. `eval/results.md` requires the two to be quoted
 * together, so the strip shows the weak number at the same size as the strong
 * one and colours it as the warning it is.
 */

interface MetricsStripProps {
  benchmark: BenchmarkReport | null;
  artefact: RunArtefact | null;
  summary: RunSummary | undefined;
  loading: boolean;
}

/**
 * Three decimals, rounded half-up.
 *
 * Not `toFixed(3)`: the verified F1 is 0.7525, which the nearest double
 * represents just *below* the true value, so `toFixed` renders 0.752 while
 * eval/results.md — the authority — quotes 0.753. A console that disagrees with
 * the report in its third decimal invites exactly the question this strip is
 * meant to answer. Scaling before rounding puts them back in step.
 */
const f3 = (v: number) => (Math.round(v * 1000) / 1000).toFixed(3);
const pct = (v: number) => `${Math.round(v * 100)}%`;

function Metric({
  label,
  children,
  hint,
  tone = "default",
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  tone?: "default" | "warning";
}) {
  return (
    <div className="metric-cell" title={hint}>
      <span className="metric-label">{label}</span>
      <span
        className={cn(
          "metric-value",
          tone === "warning" ? "text-warning" : "text-foreground",
        )}
      >
        {children}
      </span>
    </div>
  );
}

const Divider = () => (
  <div aria-hidden="true" className="h-9 w-px shrink-0 bg-border" />
);

export function MetricsStrip({ benchmark, artefact, summary, loading }: MetricsStripProps) {
  // Prefer the artefact, which is the thing on screen; fall back to the run
  // summary only while it is still loading. A run with nothing rejected must
  // read 0, not fall through to some other source — hence the explicit branch
  // rather than a `||` chain.
  const detections = artefact ? artefact.detections.length : (summary?.detections ?? 0);
  const verified = artefact
    ? artefact.verifications.filter((v) => v.verified).length
    : (summary?.verified ?? 0);
  const rejected = artefact
    ? artefact.verifications.filter((v) => !v.verified).length
    : (summary?.rejected ?? 0);

  // Which detector produced the run on screen? Detections carry it, so no
  // schema field is needed. A run is single-detector in practice; if it ever
  // is not, we decline to pick rather than describe it with one detector's
  // numbers.
  const runDetectors = new Set((artefact?.detections ?? []).map((d) => d.detector));
  const runDetector = runDetectors.size === 1 ? [...runDetectors][0] : null;

  const measured = benchmark?.detectors ?? [];
  // The entry for this run's detector. Falling back to the first measured one
  // would be exactly the bug this selection exists to prevent, so when the run
  // has no match we show nothing rather than the wrong detector's result.
  const active = runDetector ? (measured.find((d) => d.detector === runDetector) ?? null) : null;

  const detector = active ?? benchmark?.detector ?? null;
  const verification = active?.verification ?? benchmark?.verification ?? null;
  const multiTemporal = benchmark?.multi_temporal ?? null;
  const generalisation = benchmark?.generalisation ?? null;
  const detectorLabel = active?.label ?? null;
  const unmatchedDetector = runDetector !== null && active === null && measured.length > 0;

  // Do the benchmark numbers describe the detector settings this run used? If
  // not, saying so is the difference between context and a false claim.
  const runThreshold = artefact?.provenance.fdi_threshold;
  const benchThreshold = benchmark?.fdi_threshold;
  // Only the spectral detector thresholds on FDI, so the parity check is
  // meaningless for a CNN run — provenance still carries an fdi_threshold the
  // network never consulted, and comparing it would warn about a mismatch that
  // cannot affect the numbers shown.
  const thresholdApplies = (active?.detector ?? "fdi") === "fdi";
  const thresholdMismatch =
    thresholdApplies &&
    typeof runThreshold === "number" &&
    typeof benchThreshold === "number" &&
    Math.abs(runThreshold - benchThreshold) > 1e-9;

  if (loading) {
    return (
      <div className="h-[74px] shrink-0 animate-pulse border-b border-border bg-background" />
    );
  }

  return (
    <details className="group shrink-0 border-b border-border bg-background">
      {/* Wraps rather than scrolling horizontally. A scrolling row put the
          detector's region recall — the number PRD §8 is least willing to see
          hidden — off the right edge on a narrow screen, along with the
          expand affordance. Two rows cost a few pixels; a hidden weak number
          costs the honesty the strip exists for. */}
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-7 gap-y-3 px-5 py-3.5">
        <Metric label="This run" hint="Candidates the detector raised in this run">
          {detections} detected
        </Metric>
        <Metric label="Verified" hint="Detections the Verification Agent kept">
          {verified}
        </Metric>
        <Metric label="Rejected" hint="Detections disqualified, with reasons — see the Rejected tab">
          {rejected}
        </Metric>

        <Divider />

        {benchmark?.available && (
          <Badge variant="outline" className="shrink-0 whitespace-nowrap">
            <FlaskConical className="size-3" />
            {benchmark.dataset} {verification?.split ?? "test"}
            {detectorLabel ? ` · ${detectorLabel}` : ""} — not this run
          </Badge>
        )}

        {unmatchedDetector && (
          <Badge variant="warning" className="shrink-0 whitespace-nowrap">
            <AlertTriangle className="size-3" />
            No benchmark for the {runDetector} detector
          </Badge>
        )}

        {verification ? (
          <>
            <Metric
              label="Verification precision"
              hint="FR-2.4: precision before and after the Verification Agent, on the held-out split"
            >
              {f3(verification.baseline_precision)}
              <span className="mx-1 text-muted-foreground">→</span>
              {f3(verification.verified_precision)}
              <span className="ml-1.5 text-success">
                +{f3(verification.precision_gain)}
              </span>
            </Metric>
            <Metric label="F1" hint="Same comparison, F1">
              {f3(verification.baseline_f1)}
              <span className="mx-1 text-muted-foreground">→</span>
              {f3(verification.verified_f1)}
              <span className="ml-1.5 text-success">+{f3(verification.f1_gain)}</span>
            </Metric>
          </>
        ) : null}

        {detector ? (
          <Metric
            label="Detector region recall"
            tone="warning"
            hint="Fraction of annotated debris regions any detection lands on. Unaffected by verification. MARIDA splits by patch rather than by tile, so 91% of test patches sit on tiles the model trained on — see the unseen-region cost beside this."
          >
            <AlertTriangle className="mr-1 inline size-3 align-[-1px]" />
            {f3(detector.region_recall)}
            <span className="ml-1.5 text-muted-foreground">
              misses {detector.regions_missed}/{detector.regions}
            </span>
            {generalisation ? (
              <span className="ml-1.5 text-warning">within-tile</span>
            ) : null}
          </Metric>
        ) : null}

        {generalisation ? (
          <Metric
            label="Unseen region (F1)"
            tone="warning"
            hint="Region recall above is a within-tile number — most test patches sit on tiles the model trained on. This is the paired holdout: what a region the model has never seen actually costs."
          >
            <AlertTriangle className="mr-1 inline size-3 align-[-1px]" />
            {f3(generalisation.trained_f1)}
            <span className="mx-1 text-muted-foreground">→</span>
            {f3(generalisation.unseen_f1)}
            <span className="ml-1.5 text-muted-foreground">
              {generalisation.f1_cost >= 0 ? "+" : ""}
              {f3(generalisation.f1_cost)} on {generalisation.region}
            </span>
          </Metric>
        ) : null}

        {multiTemporal ? (
          <Metric
            label="Multi-temporal (FR-2.2)"
            tone="warning"
            hint="Measured, and it currently costs quality rather than adding it — the coherence test has no current field to work with."
          >
            <AlertTriangle className="mr-1 inline size-3 align-[-1px]" />
            {f3(multiTemporal.baseline_f1)}
            <span className="mx-1 text-muted-foreground">→</span>
            {f3(multiTemporal.with_check_f1)}
            <span className="ml-1.5 text-muted-foreground">blocked on FR-3</span>
          </Metric>
        ) : null}

        {!benchmark?.available && (
          <Metric label="Measured quality" tone="warning">
            <AlertTriangle className="mr-1 inline size-3 align-[-1px]" />
            unavailable
          </Metric>
        )}

        {thresholdMismatch && (
          <Badge variant="warning" className="shrink-0 whitespace-nowrap">
            <AlertTriangle className="size-3" />
            Different detector threshold
          </Badge>
        )}

        <ChevronDown className="ml-auto size-4 shrink-0 text-muted-foreground transition-transform duration-150 group-open:rotate-180" />
      </summary>

      <div className="border-t border-border bg-card px-5 py-4 text-[11.5px] leading-relaxed text-muted-foreground">
        {benchmark?.available ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h2 className="mb-1.5 text-xs font-semibold text-foreground">
                What was measured
              </h2>
              <dl className="space-y-1">
                {verification && (
                  <>
                    <Row
                      term="Precision"
                      value={`${f3(verification.baseline_precision)} → ${f3(
                        verification.verified_precision,
                      )}`}
                    />
                    <Row
                      term="Recall"
                      value={`${f3(verification.baseline_recall)} → ${f3(
                        verification.verified_recall,
                      )}`}
                      note={`${f3(verification.recall_cost)} given up`}
                    />
                    <Row
                      term="F1"
                      value={`${f3(verification.baseline_f1)} → ${f3(verification.verified_f1)}`}
                    />
                    <Row
                      term="False-positive rate"
                      value={`${f3(verification.baseline_false_positive_rate)} → ${f3(
                        verification.verified_false_positive_rate,
                      )}`}
                    />
                    <Row
                      term="Scored candidates"
                      value={`${verification.scored}`}
                      note={`${verification.excluded_unlabelled} unlabelled excluded`}
                    />
                  </>
                )}
                {detector && (
                  <Row
                    term="Debris regions hit"
                    value={`${detector.regions_hit} / ${detector.regions}`}
                    note={`${pct(detector.region_recall)} region recall`}
                  />
                )}
                {active && (
                  <Row
                    term="Candidates emitted"
                    value={`${active.candidates_emitted}`}
                    note={`${f3(active.detector_precision)} detector precision`}
                  />
                )}
              </dl>

              {active && (
                <p className="mt-2">
                  Measured for the{" "}
                  <span className="font-medium text-foreground">{active.label}</span>, which
                  is the detector that produced this run.
                </p>
              )}
              <p className="mt-2">
                Source:{" "}
                <span className="font-mono text-foreground">{benchmark.results_doc}</span>{" "}
                (from{" "}
                <span className="font-mono">{benchmark.source_file}</span>).{" "}
                {benchmark.dataset} {benchmark.dataset_version}
                {benchmark.dataset_doi ? `, DOI ${benchmark.dataset_doi}` : ""}.
                {benchmark.fdi_threshold !== null && (
                  <> Detector threshold FDI &gt; {benchmark.fdi_threshold}.</>
                )}
              </p>
              {thresholdMismatch && (
                <p className="mt-1.5 flex items-start gap-1.5 text-warning">
                  <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                  <span>
                    This run was computed at FDI &gt; {runThreshold}, but the numbers above
                    were measured at {benchThreshold}. They describe the benchmarked
                    configuration, not this one.
                  </span>
                </p>
              )}
            </div>

            <div>
              <h2 className="mb-1.5 text-xs font-semibold text-foreground">
                Read before quoting these
              </h2>

              {benchmark.verification_overlap && (
                <p className="mb-2 flex items-start gap-1.5 rounded-md border border-warning/30 bg-warning/10 p-2 text-warning">
                  <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                  <span>{benchmark.verification_overlap}</span>
                </p>
              )}

              {measured.length > 1 && (
                <dl className="mb-2 space-y-1">
                  {measured.map((entry) => (
                    <Row
                      key={entry.detector}
                      term={entry.label}
                      value={`recall ${f3(entry.region_recall)}`}
                      note={`verification +${f3(entry.verification.precision_gain)} precision`}
                    />
                  ))}
                </dl>
              )}

              <ul className="space-y-1">
                {benchmark.caveats.map((caveat) => (
                  <li key={caveat} className="flex items-start gap-1.5">
                    <Info className="mt-0.5 size-3 shrink-0 opacity-70" />
                    <span>{caveat}</span>
                  </li>
                ))}
              </ul>

              {multiTemporal && (
                <>
                  <h2 className="mb-1.5 mt-3 text-xs font-semibold text-foreground">
                    Multi-temporal consistency (FR-2.2) — no contribution
                  </h2>
                  <dl className="mb-1.5 space-y-1">
                    <Row
                      term="F1"
                      value={`${f3(multiTemporal.baseline_f1)} → ${f3(
                        multiTemporal.with_check_f1,
                      )}`}
                      note={`${f3(multiTemporal.f1_delta)} from the check`}
                    />
                    <Row
                      term="Recall"
                      value={`${f3(multiTemporal.baseline_recall)} → ${f3(
                        multiTemporal.with_check_recall,
                      )}`}
                    />
                    <Row
                      term="Rejected"
                      value={`${multiTemporal.rejections}`}
                      note={`${multiTemporal.true_debris_lost} was real debris`}
                    />
                    <Row
                      term="Transients found"
                      value={`${multiTemporal.transients_found}`}
                      note="the signal the check exists to catch"
                    />
                    <Row
                      term="Pair"
                      value={`${multiTemporal.tile}`}
                      note={`${multiTemporal.date_a} → ${multiTemporal.date_b}, ${multiTemporal.candidates_labelled} labelled`}
                    />
                  </dl>
                  <ul className="space-y-1">
                    {benchmark.multi_temporal_caveats.map((caveat) => (
                      <li key={caveat} className="flex items-start gap-1.5">
                        <Info className="mt-0.5 size-3 shrink-0 opacity-70" />
                        <span>{caveat}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {generalisation && (
                <>
                  <p className="font-medium text-foreground">
                    Geographic generalisation — {generalisation.region} withheld from
                    train and val
                  </p>
                  <p>
                    Both models scored on the identical {generalisation.patches}{" "}
                    patches ({generalisation.debris_px_per_patch} debris px/patch), so
                    the only variable is whether the model had seen that region.
                  </p>
                  <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
                    <Row
                      term="Trained on the region"
                      value={`F1 ${f3(generalisation.trained_f1)}`}
                      note={`P ${f3(generalisation.trained_precision)} · R ${f3(
                        generalisation.trained_recall,
                      )}`}
                    />
                    <Row
                      term="Never saw the region"
                      value={`F1 ${f3(generalisation.unseen_f1)}`}
                      note={`P ${f3(generalisation.unseen_precision)} · R ${f3(
                        generalisation.unseen_recall,
                      )}`}
                    />
                    <Row
                      term="Cost of it being unseen"
                      value={`${f3(generalisation.f1_cost)} F1`}
                    />
                  </dl>
                  <p>
                    Almost all of that is recall ({f3(generalisation.recall_cost)}),
                    not precision ({f3(generalisation.precision_cost)}). On unseen
                    water the detector finds less, but what it flags stays
                    trustworthy — the better of the two failure directions for a
                    screening stage feeding verification.
                  </p>
                  <ul className="space-y-1">
                    {benchmark.generalisation_caveats.map((caveat) => (
                      <li key={caveat} className="flex items-start gap-1.5">
                        <Info className="mt-0.5 size-3 shrink-0 opacity-70" />
                        <span>{caveat}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        ) : (
          <p className="flex items-start gap-1.5">
            <AlertTriangle className="mt-0.5 size-3 shrink-0 text-warning" />
            <span>
              {benchmark?.unavailable_reason ??
                "No measured results are available to this server, so the console cannot " +
                  "show the system's precision or recall. eval/results.md is the authority."}
            </span>
          </p>
        )}
      </div>
    </details>
  );
}

function Row({ term, value, note }: { term: string; value: string; note?: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="w-36 shrink-0">{term}</dt>
      <dd className="font-mono tabular-nums text-foreground">{value}</dd>
      {note && <span className="truncate">({note})</span>}
    </div>
  );
}
