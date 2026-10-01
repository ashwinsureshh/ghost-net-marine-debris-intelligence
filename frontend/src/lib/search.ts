/**
 * The command palette's index: navigation over data already loaded, never a
 * query to a model. Regions come from the run summaries; everything else from
 * the open run only, so searching never triggers a download.
 */

export type SearchKind = "region" | "detection" | "river" | "protected_area" | "view";

export interface SearchItem {
  kind: SearchKind;
  id: string;
  label: string;
  detail: string;
  /** Lower-cased haystack, built once. */
  text: string;
  /** Run to open, for regions; detection to select, for the rest. */
  runId?: string;
  detectionId?: string;
  lat?: number;
  lon?: number;
}

interface IndexInput {
  runs: { run_id: string; region_name?: string; inputs_are_synthetic?: boolean; detections?: number; unreadable?: boolean }[];
  artefact: {
    run_id: string;
    detections: { id: string; tile_id: string; acquired_at: string; lat: number; lon: number }[];
    verifications: { detection_id: string; verified: boolean }[];
    attributions: Record<string, { candidates: { name: string; probability: number }[] }>;
    protected_areas: { name: string; designation: string; lat: number; lon: number }[];
  } | null;
  views: { id: string; label: string }[];
}

const item = (value: Omit<SearchItem, "text">): SearchItem =>
  ({ ...value, text: `${value.label} ${value.detail} ${value.id}`.toLowerCase() });

export function buildSearchIndex({ runs, artefact, views }: IndexInput): SearchItem[] {
  const out: SearchItem[] = views.map(v => item({ kind: "view", id: v.id, label: v.label, detail: "Go to view" }));
  for (const run of runs) {
    if (run.unreadable) continue;
    out.push(item({ kind: "region", id: run.run_id, label: run.region_name ?? run.run_id,
      detail: `${run.inputs_are_synthetic ? "Synthetic demo" : "Historical run"} · ${run.detections ?? 0} records`, runId: run.run_id }));
  }
  if (!artefact) return out;
  const verified = new Map(artefact.verifications.map(v => [v.detection_id, v.verified]));
  for (const d of artefact.detections) {
    out.push(item({ kind: "detection", id: d.id, label: d.id,
      detail: `${verified.get(d.id) ? "Verified" : "Rejected"} · ${d.acquired_at.slice(0, 10)} · tile ${d.tile_id}`,
      detectionId: d.id, lat: d.lat, lon: d.lon }));
  }
  // One entry per river: the detection it is most probable for is where it goes.
  const rivers = new Map<string, { detectionId: string; probability: number; count: number }>();
  for (const [detectionId, attribution] of Object.entries(artefact.attributions)) {
    for (const river of attribution.candidates) {
      const seen = rivers.get(river.name);
      if (!seen || river.probability > seen.probability) {
        rivers.set(river.name, { detectionId, probability: river.probability, count: (seen?.count ?? 0) + 1 });
      } else seen.count += 1;
    }
  }
  for (const [name, r] of rivers) {
    out.push(item({ kind: "river", id: `river:${name}`, label: name,
      detail: `Modelled candidate source for ${r.count} site(s) · highest ${(r.probability * 100).toFixed(0)}%`, detectionId: r.detectionId }));
  }
  for (const area of artefact.protected_areas) {
    out.push(item({ kind: "protected_area", id: `mpa:${area.name}`, label: area.name,
      detail: area.designation || "Protected area", lat: area.lat, lon: area.lon }));
  }
  return out;
}

const KIND_RANK: Record<SearchKind, number> = { view: 0, region: 1, river: 2, protected_area: 3, detection: 4 };

/** All terms must match; label-prefix matches first, then by kind. */
export function searchIndex(index: readonly SearchItem[], query: string, limit = 30): SearchItem[] {
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  if (!terms.length) return index.filter(i => i.kind === "view" || i.kind === "region").slice(0, limit);
  const scored: { item: SearchItem; score: number }[] = [];
  for (const entry of index) {
    if (!terms.every(t => entry.text.includes(t))) continue;
    const prefix = entry.label.toLowerCase().startsWith(terms[0]) ? 0 : 1;
    scored.push({ item: entry, score: prefix * 10 + KIND_RANK[entry.kind] });
  }
  return scored.sort((a, b) => a.score - b.score).slice(0, limit).map(s => s.item);
}
