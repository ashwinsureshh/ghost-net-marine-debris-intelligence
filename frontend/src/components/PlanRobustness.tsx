import type { RobustnessReport } from "@/lib/types";

interface Props {
  report: RobustnessReport | null;
  capacity: number;
  horizonDays: number;
}

/**
 * How much the ranked plan moves when the priority weights are nudged.
 *
 * Reads a measured artefact; it never recomputes. It states the capacity and
 * horizon it was measured at, and says so when the operator's current settings
 * differ, because a sensitivity result for three vessels does not describe a
 * five-vessel plan. Stability is not accuracy, and the panel says that too.
 */
export function PlanRobustness({ report, capacity, horizonDays }: Props) {
  if (!report) return null;

  if (report.status !== "measured") {
    return (
      <details className="atlas-robustness">
        <summary>Plan robustness · {report.status === "stale" ? "out of date" : "not measured"}</summary>
        <p>{report.reason}</p>
      </details>
    );
  }

  const at = report.measured_at!;
  const differs = at.vessel_capacity !== capacity || at.planning_horizon_days !== horizonDays;
  const variants = report.variants ?? 0;

  return (
    <details className="atlas-robustness">
      <summary>Plan robustness · weight sensitivity</summary>
      <p>
        Each of the four priority weights was changed by ±10%, ±25% and ±50%, one at a
        time and renormalised ({variants} variants, {report.candidates} verified sites).
      </p>
      <dl>
        <div><dt>Top site changed</dt><dd>{report.top1_changed} of {variants}</dd></div>
        <div><dt>Dispatched set changed</dt><dd>{report.dispatch_set_changed} of {variants}</dd></div>
        {report.min_spearman != null && (
          <div><dt>Lowest rank correlation</dt><dd>{report.min_spearman.toFixed(3)}</dd></div>
        )}
      </dl>
      <p className={differs ? "atlas-robustness-warn" : undefined}>
        Measured at {at.vessel_capacity} vessels / {at.planning_horizon_days} days
        {differs ? `, not your current ${capacity} / ${horizonDays}; treat as indicative.` : "."}
      </p>
      {report.inputs_degraded && report.inputs_degraded.length > 0 && (
        <p className="atlas-robustness-warn">
          Measured with missing inputs: those signals were unavailable, not zero.
        </p>
      )}
      <p className="atlas-robustness-note">
        Stability under weight changes is not accuracy. Source: {report.source_file}.
      </p>
    </details>
  );
}
