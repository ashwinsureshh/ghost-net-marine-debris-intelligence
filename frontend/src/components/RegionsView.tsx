import { ArrowUpRight, Info } from "lucide-react";
import * as React from "react";
import type { RunSummary } from "@/lib/types";
import { dataQuality, latestCandidateDate, regionFlags, topRejection, verificationRate, type RegionFlag } from "@/lib/regions";
import { staggerStyle } from "@/lib/motion";
import { formatDateShort, humanise } from "@/lib/utils";
import { Skeleton } from "@/components/ui/primitives";
import { Term } from "@/components/Term";

type Metric = "detections" | "verified" | "rejected" | "rate";
const METRICS: { id: Metric; label: string }[] = [
  { id: "detections", label: "Candidates" },
  { id: "verified", label: "Verified" },
  { id: "rejected", label: "Rejected" },
  { id: "rate", label: "Verification rate" },
];

const FLAG_TONE: Record<RegionFlag, string> = {
  "FULL DATA": "ok", "PARTIAL DATA": "warn", "NO GFW": "warn", "NO GROUND TRUTH": "muted",
  "UNSEEN TEST REGION": "info", SYNTHETIC: "muted",
};

/**
 * Every monitored coastline side by side, from the lightweight run summaries
 * only: no full artefact is loaded until a region is opened.
 *
 * Counts are detection RECORDS across acquisitions, not distinct debris
 * objects, and a higher verification rate is not higher accuracy: it depends
 * on cloud, sea state and which false-positive modes the scene contains.
 */
export function RegionsView({ runs, activeRunId, onOpen, loading }: {
  runs: RunSummary[]; activeRunId: string | null; onOpen: (runId: string) => void; loading: boolean;
}) {
  const [metric, setMetric] = React.useState<Metric>("detections");
  const [explain, setExplain] = React.useState<string | null>(null);
  const readable = runs.filter(r => !r.unreadable);
  const real = readable.filter(r => !r.inputs_are_synthetic);
  const value = (r: RunSummary) => metric === "rate" ? verificationRate(r) ?? 0 : (r[metric] ?? 0);
  const max = metric === "rate" ? 1 : Math.max(1, ...real.map(value));

  return (
    <div className="gn-page">
      <header className="gn-page-head">
        <span className="atlas-eyebrow">Monitored coastlines</span>
        <h1>Regions</h1>
        <p>Historical regional runs, compared on what each one recorded. Records are detections across acquisitions,
          not distinct debris objects. <Term term="Data quality" /> describes available inputs, never accuracy.</p>
      </header>

      <section className="gn-compare" aria-label="Region comparison">
        <div className="gn-compare-head">
          <h2>Compare</h2>
          <div className="gn-segment" role="group" aria-label="Comparison metric">
            {METRICS.map(m => <button key={m.id} type="button" aria-pressed={metric === m.id} onClick={() => setMetric(m.id)}>{m.label}</button>)}
          </div>
        </div>
        <ul>
          {loading && [0, 1, 2].map(i => <li key={i}><Skeleton className="h-4 w-full" /></li>)}
          {real.map(r => {
            const v = value(r);
            return (
              <li key={r.run_id}>
                <span className="gn-compare-name">{shortName(r)}</span>
                <div className="gn-bar gn-bar--thick"><div className="gn-bar-fill gn-bar-in"
                  style={{ transform: `scaleX(${max ? v / max : 0})` }} /></div>
                <span className="gn-compare-value tabular">{metric === "rate" ? (verificationRate(r) === null ? "—" : `${(v * 100).toFixed(1)}%`) : v.toLocaleString()}</span>
              </li>
            );
          })}
        </ul>
        {metric === "rate" && <p className="gn-compare-note">Share of candidates that survived the five false-positive checks.
          Driven by scene conditions as much as by debris; it is not detection accuracy.</p>}
      </section>

      <div className="gn-region-grid">
        {loading && [0, 1, 2].map(i => <Skeleton key={i} className="h-72" />)}
        {readable.map((r, i) => {
          const quality = dataQuality(r);
          const flags = regionFlags(r);
          const rate = verificationRate(r);
          const rejection = topRejection(r);
          const latest = latestCandidateDate(r);
          const open = explain === r.run_id;
          return (
            <article key={r.run_id} className="gn-region-card gn-enter" style={staggerStyle(i)}
              aria-current={r.run_id === activeRunId ? "true" : undefined}>
              <div className="gn-region-top">
                <div>
                  <h3>{shortName(r)}</h3>
                  <p>{placeName(r)}</p>
                </div>
                <button type="button" className={`gn-quality gn-quality--${quality.level}`} aria-expanded={open}
                  onClick={() => setExplain(open ? null : r.run_id)}>
                  <Info size={12} /> Data quality: {quality.label}
                </button>
              </div>
              {open && <ul className="gn-quality-factors gn-enter">
                  {quality.factors.map(f => <li key={f.id} className={`gn-factor gn-factor--${f.state}`}>
                    <strong>{f.label}</strong><span>{f.detail}</span></li>)}
                  <li className="gn-factor-note">Availability only. A region with every input can still have low accuracy.</li>
                </ul>}
              <div className="gn-flags">{flags.map(f => <span key={f} className={`gn-flag gn-flag--${FLAG_TONE[f]}`}>{f}</span>)}</div>
              <dl className="gn-region-stats">
                <div><dt>Candidates</dt><dd>{r.detections ?? "—"}</dd></div>
                <div><dt>Verified</dt><dd>{r.verified ?? "—"}</dd></div>
                <div><dt>Rejected</dt><dd>{r.rejected ?? "—"}</dd></div>
                <div><dt>Verified share</dt><dd>{rate === null ? "—" : `${(rate * 100).toFixed(1)}%`}</dd></div>
              </dl>
              <dl className="gn-region-meta">
                <div><dt>Window</dt><dd>{r.coverage?.start ? formatDateShort(r.coverage.start) : "—"} — {r.coverage?.end ? formatDateShort(r.coverage.end) : "—"}</dd></div>
                <div><dt>Latest candidate</dt><dd>{latest ? formatDateShort(latest) : "—"}</dd></div>
                <div><dt>Most common rejection</dt><dd>{rejection ? `${humanise(rejection[0])} (${rejection[1]})` : "—"}</dd></div>
              </dl>
              {r.candidate_dates && r.candidate_dates.length > 0 && <CandidateTimeline dates={r.candidate_dates} />}
              {(r.degradation_notes?.length ?? 0) > 0 && <ul className="gn-region-caveats">
                {r.degradation_notes!.map(n => <li key={n}>{n}</li>)}</ul>}
              <button type="button" className="gn-open-region" onClick={() => onOpen(r.run_id)}>
                Open on map <ArrowUpRight size={14} />
              </button>
            </article>
          );
        })}
      </div>
      <p className="gn-page-foot">Cloud cover and usable-water area are not recorded in the run summaries, so they are not shown
        rather than estimated. Dates below are dates with at least one candidate, not every acquisition.</p>
    </div>
  );
}

/** One tick per date that produced a candidate; height scales with the count. */
function CandidateTimeline({ dates }: { dates: { date: string; candidates: number }[] }) {
  const first = Date.parse(dates[0].date);
  const last = Date.parse(dates[dates.length - 1].date);
  const span = Math.max(last - first, 1);
  const peak = Math.max(...dates.map(d => d.candidates));
  return (
    <figure className="gn-timeline">
      <figcaption>Dates with candidates ({dates.length})</figcaption>
      <div className="gn-timeline-track" role="img"
        aria-label={`${dates.length} dates with candidates between ${dates[0].date} and ${dates[dates.length - 1].date}`}>
        {dates.map(d => <span key={d.date} title={`${d.date}: ${d.candidates} candidate(s)`}
          style={{ left: `${((Date.parse(d.date) - first) / span) * 100}%`, height: `${20 + 80 * (d.candidates / peak)}%` }} />)}
      </div>
      <div className="gn-timeline-ends"><span>{formatDateShort(dates[0].date)}</span><span>{formatDateShort(dates[dates.length - 1].date)}</span></div>
    </figure>
  );
}

const shortName = (r: RunSummary) => (r.region_name ?? r.run_id).split(" — ")[0];
const placeName = (r: RunSummary) => {
  const parts = (r.region_name ?? "").split(" — ");
  return parts.length > 1 ? parts.slice(1).join(" — ") : r.inputs_are_synthetic ? "Generated inputs" : "";
};
