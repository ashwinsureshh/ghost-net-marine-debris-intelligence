import type { RunArtefact, RunSummary } from './types';

export type Bounds = [number, number, number, number];
export interface RunCoverage {
  runId: string;
  name: string;
  bounds: Bounds | null;
  scope: 'requested-aoi' | 'region' | 'unknown';
  start: string | null;
  end: string | null;
  detections: number;
  synthetic: boolean;
  partial: boolean;
}

function validBounds(value: unknown): value is Bounds {
  if (!Array.isArray(value) || value.length !== 4 || !value.every(v => typeof v === 'number' && Number.isFinite(v))) return false;
  const [w, s, e, n] = value;
  return w >= -180 && e <= 180 && s >= -90 && n <= 90 && w < e && s < n;
}

/** Existing exports record the actual requested AOI in provenance, whereas
 * region.bbox can describe a much larger study region. Neither guarantees
 * cloud-free observation of every pixel. Never infer coverage from detections.
 */
export function runCoverage(run: RunArtefact): RunCoverage {
  let bounds: Bounds | null = null;
  let scope: RunCoverage['scope'] = 'unknown';
  for (const note of run.provenance.notes) {
    const match = note.match(/^Imagery covers AOI (\[[^\]]+\])/);
    if (!match) continue;
    try {
      const value: unknown = JSON.parse(match[1]);
      if (validBounds(value)) { bounds = value; scope = 'requested-aoi'; break; }
    } catch { /* Older/unrecognised metadata must not invent an imagery footprint. */ }
  }
  if (!bounds && validBounds(run.region.bbox)) { bounds = run.region.bbox; scope = 'region'; }
  return { runId: run.run_id, name: run.region.name, bounds, scope,
    start: run.region.window_start, end: run.region.window_end,
    detections: run.detections.length, synthetic: run.provenance.inputs_are_synthetic,
    partial: run.degradations.length > 0 };
}

/** No transport here: reopening coverage reuses the boot-time summaries. */
export function coverageFromSummaries(runs: RunSummary[]) {
  const real = runs.filter(r => !r.unreadable && r.inputs_are_synthetic === false);
  return {
    coverage: real.flatMap(r => r.coverage ? [r.coverage] : []),
    failed: real.filter(r => !r.coverage).length,
  };
}
