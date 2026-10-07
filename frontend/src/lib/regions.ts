/**
 * Region-level context read off lightweight run summaries.
 *
 * DATA QUALITY here means which inputs were AVAILABLE to the run. It is not
 * accuracy, and it must never be read as accuracy: a run with every input can
 * still be wrong everywhere. The explanation lists each factor so the badge
 * can always be opened to show exactly what it counted.
 */

export interface RegionSummaryLike {
  run_id: string;
  region_name?: string;
  inputs_are_synthetic?: boolean;
  detections?: number;
  verified?: number;
  rejected?: number;
  trajectories?: number;
  attributions?: number;
  correlations?: number;
  has_mpa_data?: boolean;
  degradation_notes?: string[];
  geographic_holdout?: boolean;
  candidate_dates?: { date: string; candidates: number }[];
  failed_checks?: Record<string, number>;
  coverage?: { start: string | null; end: string | null } | null;
}

export type FactorState = "available" | "missing" | "unknown";

export interface QualityFactor {
  id: "imagery" | "currents" | "rivers" | "vessels" | "protected_areas" | "ground_truth";
  label: string;
  state: FactorState;
  detail: string;
}

export type QualityLevel = "high" | "partial" | "limited" | "synthetic";

export interface DataQuality {
  level: QualityLevel;
  label: string;
  factors: QualityFactor[];
}

const mentions = (notes: readonly string[], agent: string) =>
  notes.some(n => n.toLowerCase().startsWith(`${agent}:`));

export function dataQuality(summary: RegionSummaryLike): DataQuality {
  const notes = summary.degradation_notes ?? [];
  const known = summary.degradation_notes !== undefined;
  const verified = summary.verified ?? 0;
  const factor = (id: QualityFactor["id"], label: string, present: boolean | undefined,
    detail: { yes: string; no: string; unknown?: string }): QualityFactor => ({
    id, label,
    state: present === undefined ? "unknown" : present ? "available" : "missing",
    detail: present === undefined ? detail.unknown ?? "Not recorded in this summary." : present ? detail.yes : detail.no,
  });

  const factors: QualityFactor[] = [
    factor("imagery", "Sentinel-2 imagery", !summary.inputs_are_synthetic && !mentions(notes, "detection"),
      { yes: "Real Sentinel-2 L2A scenes for the run window.", no: "Generated or missing imagery." }),
    factor("currents", "Ocean currents", verified === 0 ? undefined : !mentions(notes, "drift") && (summary.trajectories ?? 0) > 0,
      { yes: "OSCAR current field drove the drift ensemble.", no: "No current field: drift did not run on real currents.", unknown: "No verified sites, so drift had nothing to run on." }),
    factor("rivers", "River-source data", verified === 0 ? undefined : !mentions(notes, "attribution") && (summary.attributions ?? 0) > 0,
      { yes: "Meijer et al. 2021 river-mouth emissions.", no: "No river table: attribution did not run.", unknown: "No verified sites to attribute." }),
    factor("vessels", "GFW vessel data", !known ? undefined : !mentions(notes, "vessels"),
      { yes: "Global Fishing Watch SAR grid observations.", no: "GFW data unavailable. Unknown vessel context, not zero vessels." }),
    factor("protected_areas", "Protected areas", summary.has_mpa_data,
      { yes: "Protected Planet / WDPA extract.", no: "No protected-area data: ecological risk dropped from scoring." }),
    // Run artefacts carry no local labels for any region. Say so for every
    // region rather than leaving the row out, which would read as fine.
    { id: "ground_truth", label: "Local ground truth", state: "missing",
      detail: "No independent local labels exist for this run, so its detections have no measured local accuracy." },
  ];

  if (summary.inputs_are_synthetic) return { level: "synthetic", label: "Synthetic", factors };
  const missing = factors.filter(f => f.id !== "ground_truth" && f.state === "missing").length;
  const level: QualityLevel = missing === 0 ? "high" : missing === 1 ? "partial" : "limited";
  return { level, label: level === "high" ? "High" : level === "partial" ? "Partial" : "Limited", factors };
}

export type RegionFlag = "FULL DATA" | "PARTIAL DATA" | "NO GFW" | "NO GROUND TRUTH" | "UNSEEN TEST REGION" | "SYNTHETIC";

export function regionFlags(summary: RegionSummaryLike): RegionFlag[] {
  const quality = dataQuality(summary);
  if (quality.level === "synthetic") return ["SYNTHETIC"];
  const flags: RegionFlag[] = [quality.level === "high" ? "FULL DATA" : "PARTIAL DATA"];
  if (quality.factors.find(f => f.id === "vessels")?.state === "missing") flags.push("NO GFW");
  flags.push("NO GROUND TRUTH");
  if (summary.geographic_holdout) flags.push("UNSEEN TEST REGION");
  return flags;
}

export function verificationRate(summary: RegionSummaryLike): number | null {
  const total = summary.detections ?? 0;
  return total > 0 ? (summary.verified ?? 0) / total : null;
}

export function topRejection(summary: RegionSummaryLike): [string, number] | null {
  const entries = Object.entries(summary.failed_checks ?? {});
  if (!entries.length) return null;
  return entries.reduce((best, entry) => entry[1] > best[1] ? entry : best);
}

export function latestCandidateDate(summary: RegionSummaryLike): string | null {
  const dates = summary.candidate_dates ?? [];
  return dates.length ? dates[dates.length - 1].date : null;
}
