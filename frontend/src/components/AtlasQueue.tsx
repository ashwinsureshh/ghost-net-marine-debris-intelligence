import { ArrowUpRight, Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import type { PriorityScore, RunArtefact } from "@/lib/types";
import { formatCoord, formatDateShort } from "@/lib/utils";

/** Presentation-only catalogue. Scores and verification states come from the API. */
export function AtlasQueue({ artefact, scores, selectedId, onSelect }: {
  artefact: RunArtefact; scores: PriorityScore[]; selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [limit, setLimit] = useState(40);
  const checks = useMemo(() => new Map(artefact.verifications.map(v => [v.detection_id, v.verified])), [artefact]);
  const priorities = useMemo(() => new Map(scores.map(s => [s.detection_id, s.score])), [scores]);
  const rows = useMemo(() => artefact.detections.filter(d => {
    const status = checks.get(d.id);
    return (filter === "all" || (filter === "verified" ? status === true : status === false)) &&
      `${d.id} ${d.tile_id} ${d.acquired_at}`.toLowerCase().includes(query.toLowerCase());
  }).sort((a, b) => (priorities.get(b.id) ?? -1) - (priorities.get(a.id) ?? -1)), [artefact, checks, priorities, query, filter]);
  return <>
    <div className="atlas-search">
      <Search size={16} aria-hidden="true" />
      <input aria-label="Search detections" placeholder="Find a detection or date…" value={query}
        onChange={e => { setQuery(e.target.value); setLimit(40); }} />
      {query && <button aria-label="Clear search" onClick={() => setQuery("")}><X size={14} /></button>}
    </div>
    <div className="atlas-filters" aria-label="Filter detections">
      {[['all', 'All'], ['verified', 'Verified'], ['rejected', 'Rejected']].map(([value, label]) =>
        <button key={value} aria-pressed={filter === value} onClick={() => { setFilter(value); setLimit(40); }}>{label}</button>)}
    </div>
    <div className="atlas-queue-caption"><span>{rows.length} observations</span><span>Priority ↓</span></div>
    <div className="atlas-queue-scroll">
      {rows.slice(0, limit).map((d) => {
        const verified = checks.get(d.id);
        const score = priorities.get(d.id);
        return <button key={d.id} className="atlas-observation" aria-current={selectedId === d.id ? 'true' : undefined}
          onClick={() => onSelect(d.id)}>
          <div className="atlas-observation-top"><span className={`atlas-state ${verified === true ? 'verified' : verified === false ? 'rejected' : ''}`}>
            {verified === true ? 'Verified' : verified === false ? 'Rejected' : 'Unverified'}</span>
            <span className="atlas-score">{score === undefined ? '—' : score.toFixed(3)}</span></div>
          <div className="atlas-observation-title">{formatCoord(d.lat, d.lon)}<ArrowUpRight size={16} /></div>
          <div className="atlas-observation-meta">{formatDateShort(d.acquired_at)}<span>{d.detector.toUpperCase()} · raw {d.confidence.toFixed(2)}</span></div>
          <div className="atlas-observation-id" title={d.id}>{d.id}</div>
        </button>;
      })}
      {!rows.length && <div className="atlas-no-results"><h3>No matching detections</h3><p>Try another date or change the filter.</p></div>}
      {rows.length > limit && <button className="atlas-load-more" onClick={() => setLimit(limit + 40)}>Show next {Math.min(40, rows.length - limit)} observations</button>}
    </div>
  </>;
}
