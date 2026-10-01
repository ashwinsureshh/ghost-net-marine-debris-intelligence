import {
  Check,
  ChevronDown,
  Compass,
  Droplets,
  HelpCircle,
  MousePointerClick,
  Radar,
  Satellite,
  Waves,
  X,
} from "lucide-react";
import * as React from "react";
import type { CheckResult, Evidence, PriorityScore, RobustnessReport, RunArtefact } from "@/lib/types";
import { cn, formatCoord, formatDate, humanise } from "@/lib/utils";
import { staggerStyle, useAnimatedNumber } from "@/lib/motion";
import { EmptyState } from "@/components/ui/primitives";
import { TrajectoryPlayer } from "@/components/TrajectoryPlayer";
import { Term } from "@/components/Term";

/**
 * The evidence trail for one detection — PRD 8's explainability requirement.
 *
 * Deliberately exhaustive rather than summarised: every check the Verification
 * Agent ran (including the ones that passed), the drift envelope, the full
 * ranked river distribution, the dark-vessel contacts with their disclaimer,
 * and the score decomposition with its weights. A researcher auditing why a
 * site was flagged should not have to leave this panel.
 *
 * Tabs split it by agent so each question has one place. The summary bars on
 * Overview stay SEPARATE: there is no combined "AI confidence" number, because
 * no measurement supports one.
 */

const EVIDENCE_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  sentinel2_tile: Satellite,
  current_field: Waves,
  drifter_track: Compass,
  river_table: Droplets,
  vessel_record: Radar,
  mpa_boundary: Compass,
  derived: Check,
};

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "evidence", label: "Checks" },
  { id: "drift", label: "Drift" },
  { id: "attribution", label: "Source" },
  { id: "vessels", label: "Vessels" },
  { id: "provenance", label: "Provenance" },
] as const;
type TabId = (typeof TABS)[number]["id"];

interface EvidencePanelProps {
  artefact: RunArtefact;
  detectionId: string | null;
  score: PriorityScore | undefined;
  rank?: number;
  robustness?: RobustnessReport | null;
  onClose: () => void;
}

export function EvidencePanel({ artefact, detectionId, score, rank, robustness, onClose }: EvidencePanelProps) {
  const [tab, setTab] = React.useState<TabId>("overview");
  const tabsId = React.useId();

  if (!detectionId) {
    return (
      <EmptyState icon={MousePointerClick} title="Select a detection">
        Pick a site from the dispatch list, the rejected list, or the map to see
        every piece of evidence behind it — the checks it passed and failed, its
        drift envelope, probable sources, and how its priority score was composed.
      </EmptyState>
    );
  }

  const detection = artefact.detections.find((d) => d.id === detectionId);
  const verification = artefact.verifications.find((v) => v.detection_id === detectionId);
  const backward = artefact.backward[detectionId];
  const forward = artefact.forward[detectionId];
  const attribution = artefact.attributions[detectionId];
  const correlation = artefact.correlations[detectionId];

  if (!detection) {
    return <EmptyState icon={X} title="That detection is not in this run" />;
  }

  const vesselsDegraded = artefact.degradations.some(d => d.startsWith("vessels:"));

  return (
    <div className="flex h-full flex-col">
      <header className="gn-evidence-head">
        <div className="min-w-0">
          <p className="truncate font-mono text-xs text-muted-foreground">{detection.id}</p>
          <p className="tabular mt-0.5 text-sm font-medium">{formatCoord(detection.lat, detection.lon)}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close evidence panel" className="gn-icon-button">
          <X className="size-4" />
        </button>
      </header>

      {/* The answer before the working: urgency, whether it survived
          verification, and which agent says so. */}
      <div className="gn-evidence-answer">
        <div className="flex items-baseline gap-3">
          <AnimatedScore value={score?.score} />
          <span className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">Priority</span>
          {rank !== undefined && <span className="gn-rank-chip">Rank {rank}</span>}
          <span className="ml-auto shrink-0 text-[11px] font-medium">
            {verification ? (verification.verified
              ? <span className="text-success">Verified</span>
              : <span className="text-destructive">Rejected</span>)
              : <span className="text-muted-foreground">Unverified</span>}
          </span>
        </div>
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Candidate debris, not a confirmed ghost net · {detection.detector.toUpperCase()} · {formatDate(detection.acquired_at)}
        </p>
      </div>

      <div className="gn-tabs" role="tablist" aria-label="Evidence by agent">
        {TABS.map(t => (
          <button key={t.id} type="button" role="tab" id={`${tabsId}-${t.id}`} aria-selected={tab === t.id}
            aria-controls={`${tabsId}-panel`} tabIndex={tab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)}
            onKeyDown={e => {
              const i = TABS.findIndex(x => x.id === tab);
              const next = e.key === "ArrowRight" ? TABS[(i + 1) % TABS.length] : e.key === "ArrowLeft" ? TABS[(i - 1 + TABS.length) % TABS.length] : null;
              if (next) { e.preventDefault(); setTab(next.id); document.getElementById(`${tabsId}-${next.id}`)?.focus(); }
            }}>
            {t.label}
            {tab === t.id && <span className="gn-tab-indicator" aria-hidden="true" />}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto" id={`${tabsId}-panel`} role="tabpanel" aria-labelledby={`${tabsId}-${tab}`}>
          <div key={tab} className="gn-enter px-5 py-5">
            {tab === "overview" && <>
              <SignalBars detection={detection} verification={verification} forward={forward}
                attribution={attribution} correlation={correlation} vesselsDegraded={vesselsDegraded} robustness={robustness} />
              <h3 className="gn-subhead">Detection · FR-1</h3>
              <dl className="kv">
                <Field label="Acquired" value={formatDate(detection.acquired_at)} />
                <Field label="Tile" value={detection.tile_id} mono />
                <Field label="Detector" value={detection.detector.toUpperCase()} />
                <Field label="Mean FDI" value={detection.fdi_mean.toFixed(4)} />
                <Field label="Mean NDVI" value={detection.ndvi_mean.toFixed(4)} />
                <Field label="Area" value={`${detection.area_km2.toFixed(4)} km² (${detection.area_px} px)`} />
              </dl>
              {score && <ScoreBreakdown score={score} />}
            </>}

            {tab === "evidence" && (verification
              ? <VerificationChecks checks={verification.checks} verified={verification.verified} confidence={verification.confidence} />
              : <p className="text-xs text-muted-foreground">No verification record for this detection.</p>)}

            {tab === "drift" && (forward || backward ? <>
              <TrajectoryPlayer detectionId={detection.id} forward={forward} backward={backward} />
              <div className="mt-4 space-y-2 text-xs">
                {forward && <TrackRow label="Forward" track={forward} />}
                {backward && <TrackRow label="Backward" track={backward} />}
                <p className="text-muted-foreground">
                  Ensemble of {(forward ?? backward)!.ensemble_size} members, seed{" "}
                  <span className="font-mono">{(forward ?? backward)!.seed}</span>; the same seed reproduces the same envelope.
                  Against 19 real buoys the envelope held the true position only 24.5% of the time.
                </p>
              </div>
            </> : <p className="text-xs text-muted-foreground">No trajectory: drift runs only for verified detections.</p>)}

            {tab === "attribution" && (attribution
              ? <Attribution attribution={attribution} />
              : <p className="text-xs text-muted-foreground">No source attribution for this detection.</p>)}

            {tab === "vessels" && (correlation
              ? <Vessels correlation={correlation} />
              : <p className="text-xs text-muted-foreground">
                  {vesselsDegraded ? "Vessel data unavailable for this run. Unknown vessel context, not zero vessels."
                    : "No vessel correlation for this detection."}
                </p>)}

            {tab === "provenance" && <>
              <dl className="kv mb-5">
                <Field label="Exported" value={formatDate(artefact.provenance.generated_at)} />
                <Field label="Generated on" value={artefact.provenance.generated_on} />
                <Field label="Code" value={artefact.provenance.git_commit?.slice(0, 10) ?? "—"} mono />
                <Field label="GhostNet" value={artefact.provenance.ghostnet_version} mono />
                <Field label="Inputs" value={artefact.provenance.inputs_are_synthetic ? "Synthetic" : "Historical satellite data"} />
              </dl>
              <h3 className="gn-subhead">Evidence records · PRD §8</h3>
              <EvidenceList evidence={[
                ...detection.evidence, ...(verification?.evidence ?? []), ...(forward?.evidence ?? []),
                ...(attribution?.evidence ?? []), ...(correlation?.evidence ?? []), ...(score?.evidence ?? []),
              ]} />
            </>}
          </div>
      </div>
    </div>
  );
}

function AnimatedScore({ value }: { value: number | undefined }) {
  const shown = useAnimatedNumber(value ?? 0);
  return <span className="tabular font-mono text-[26px] font-medium leading-none tracking-tight">
    {value === undefined ? "—" : shown.toFixed(3)}
  </span>;
}

/**
 * Six separate signals, each labelled with what it is. Only values that are
 * genuinely on a 0–1 scale get a bar; the rest are stated in their own units,
 * because a bar would invent a scale no one measured.
 */
function SignalBars({ detection, verification, forward, attribution, correlation, vesselsDegraded, robustness }: {
  detection: RunArtefact["detections"][number];
  verification: RunArtefact["verifications"][number] | undefined;
  forward: RunArtefact["forward"][string] | undefined;
  attribution: RunArtefact["attributions"][string] | undefined;
  correlation: RunArtefact["correlations"][string] | undefined;
  vesselsDegraded: boolean;
  robustness?: RobustnessReport | null;
}) {
  const end = forward?.points[forward.points.length - 1];
  const top = attribution?.candidates[0];
  const measured = robustness?.status === "measured" && robustness.variants;
  return (
    <div className="gn-signals">
      <Bar label={<Term term="Detection confidence" />} value={detection.confidence} />
      <Bar label={<Term term="Verification confidence" />} value={verification?.confidence}
        missing={verification ? undefined : "No verification record"} />
      <Stat label="Drift reliability" value={end ? `± ${end.uncertainty_km.toFixed(0)} km at ${forward!.horizon_days} d` : "No trajectory"}
        note={end ? "Envelope too narrow in buoy tests (24.5% coverage)" : undefined} />
      <Stat label="Source attribution" value={top ? `${top.name} · ${(top.probability * 100).toFixed(0)}%` : "Not attributed"}
        note={top ? "Modelled likely source, not confirmed" : undefined} />
      <Stat label="Vessel data" value={correlation ? `${correlation.dark_vessels.length} AIS-unmatched grid obs.` : vesselsDegraded ? "Unavailable" : "None"}
        note={vesselsDegraded ? "Unknown, not zero" : correlation ? "Investigation signal, not wrongdoing" : undefined} />
      {measured
        ? <Bar label="Priority robustness · run" value={(robustness!.variants! - (robustness!.top1_changed ?? 0)) / robustness!.variants!}
            display={`Top site unchanged in ${robustness!.variants! - (robustness!.top1_changed ?? 0)}/${robustness!.variants}`}
            note="Weight sensitivity for the whole plan; stability is not correctness" />
        : <Stat label="Priority robustness" value="Not measured" />}
    </div>
  );
}

function Bar({ label, value, missing, display, note }: {
  label: React.ReactNode; value: number | undefined; missing?: string; display?: string; note?: string;
}) {
  const pct = value === undefined ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="gn-signal">
      <div className="gn-signal-top"><span>{label}</span>
        <span className="tabular font-mono">{value === undefined ? missing ?? "—" : display ?? value.toFixed(2)}</span></div>
      <div className="gn-bar" role="img" aria-label={`${typeof label === "string" ? label : ""} ${display ?? (value?.toFixed(2) ?? "unavailable")}`}>
        <div className="gn-bar-fill gn-bar-in" style={{ transform: `scaleX(${pct / 100})` }} />
      </div>
      {note && <small>{note}</small>}
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="gn-signal">
      <div className="gn-signal-top"><span>{label}</span><span className="tabular">{value}</span></div>
      {note && <small>{note}</small>}
    </div>
  );
}

/** Checks appear one after another; a failed check is brought forward once. */
function VerificationChecks({ checks, verified, confidence }: { checks: CheckResult[]; verified: boolean; confidence: number }) {
  return <>
    <p className="mb-3 text-xs text-muted-foreground">
      Every documented false-positive mode is tested and reported — passes included, so a verified site shows what it survived.
    </p>
    <ul className="space-y-2">
      {checks.map((check, i) => {
        const unknown = !check.disqualified && /inconclusive|no repeat pass|skipped|not run/i.test(check.reason);
        return (
          <li key={check.name} style={staggerStyle(i * 2, 12)}
            className={cn("gn-check gn-enter-x-left", check.disqualified ? "gn-check--fail" : unknown ? "gn-check--unknown" : "gn-check--pass")}>
            <div className="flex items-center gap-1.5">
              {check.disqualified ? <X className="size-3.5 shrink-0" /> : unknown ? <HelpCircle className="size-3.5 shrink-0" /> : <Check className="size-3.5 shrink-0" />}
              <span className="font-medium">{humanise(check.name)}</span>
              <span className="gn-check-verdict">{check.disqualified ? "FAIL" : unknown ? "UNKNOWN" : "PASS"}</span>
            </div>
            <p className="mt-1 leading-snug text-muted-foreground">{check.reason}</p>
            {Object.keys(check.detail).length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {Object.entries(check.detail).map(([key, value]) => (
                  <span key={key} className="tabular rounded bg-background px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{key}={value}</span>
                ))}
              </div>
            )}
          </li>
        );
      })}
    </ul>
    <p className="mt-3 text-xs text-muted-foreground">
      {verified ? "Survived every check." : "Rejected: the failed check above is the reason."}{" "}
      <Term term="Verification confidence" />:{" "}
      <span className="tabular font-medium text-foreground">{confidence.toFixed(3)}</span>
    </p>
  </>;
}

function Attribution({ attribution }: { attribution: RunArtefact["attributions"][string] }) {
  if (attribution.candidates.length === 0) return <p className="text-xs text-muted-foreground">{attribution.note}</p>;
  const top3 = attribution.candidates.slice(0, 3);
  return <>
    <p className="gn-caution">Modelled likely source. No river is a confirmed source: there is no ground truth for attribution.</p>
    <ul className="space-y-3">
      {top3.map((river, i) => (
        <li key={river.name} className="text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-medium">{i + 1}. {river.name}</span>
            <span className="tabular shrink-0 text-muted-foreground">{(river.probability * 100).toFixed(0)}%</span>
          </div>
          <div className="gn-bar mt-1"><div className="gn-bar-fill" style={{ transform: `scaleX(${Math.max(river.probability, 0.02)})` }} /></div>
          <p className="tabular mt-1 text-[11px] text-muted-foreground">
            {river.distance_km.toFixed(1)} km from the backward trajectory · {river.emission_tonnes_yr.toLocaleString()} t/yr modelled emission (Meijer 2021)
          </p>
        </li>
      ))}
    </ul>
    {attribution.candidates.length > 3 && <p className="mt-2 text-[11px] text-muted-foreground">
      {attribution.candidates.length - 3} further river(s) share the remaining {(attribution.candidates.slice(3).reduce((s, r) => s + r.probability, 0) * 100).toFixed(0)}%.</p>}
    <details className="gn-explain">
      <summary>How this probability is calculated</summary>
      <p>Each river mouth's weight is its modelled plastic emission multiplied by a Gaussian fall-off with its
        closest distance to the backward trajectory, scaled by the drift envelope there. Weights are normalised to sum to 100% and the top rivers are listed. It ranks
        hypotheses; it does not observe which river released this debris.</p>
    </details>
    <p className="mt-3 text-[11px] leading-snug text-muted-foreground">{attribution.note}</p>
  </>;
}

function Vessels({ correlation }: { correlation: RunArtefact["correlations"][string] }) {
  const grid = correlation.dark_vessels.some(v => v.position_resolution_deg !== undefined);
  return <>
    <dl className="kv mb-4">
      <Field label={<Term term="AIS-unmatched" />} value={String(correlation.dark_vessels.length)} />
      <Field label="AIS-matched" value={String(correlation.matched_vessels)} />
      <Field label="Correlation strength" value={correlation.correlation_strength.toFixed(2)} />
      <Field label="Unit" value={grid ? "Grid observation" : "SAR detection"} />
    </dl>
    {correlation.dark_vessels.length === 0
      ? <p className="text-xs text-muted-foreground">No AIS-unmatched <Term term="SAR" /> observations in the available records for this window.</p>
      : <ul className="gn-vessel-list">
          {correlation.dark_vessels.slice(0, 12).map(vessel => (
            <li key={vessel.id}>
              <span className="font-mono">{formatCoord(vessel.lat, vessel.lon)}</span>
              <span>{formatDate(vessel.detected_at)}</span>
              <span>{vessel.detection_count ?? 1} detection(s) · {vessel.position_resolution_deg !== undefined ? `${vessel.position_resolution_deg}° cell` : vessel.length_m ? `${vessel.length_m} m` : "size unknown"}</span>
              <span>Unknown vessel · no AIS match</span>
            </li>
          ))}
          {correlation.dark_vessels.length > 12 && <li className="text-muted-foreground">…and {correlation.dark_vessels.length - 12} more.</li>}
        </ul>}
    {correlation.dark_vessels[0]?.source && <p className="mt-3 text-[11px] text-muted-foreground">Source: {correlation.dark_vessels[0].source}</p>}
    <p className="gn-caution mt-3">{correlation.disclaimer}</p>
  </>;
}

function ScoreBreakdown({ score }: { score: PriorityScore }) {
  return <>
    <h3 className="gn-subhead">Priority score · FR-6.1</h3>
    <ul className="space-y-2">
      {Object.entries(score.components).map(([key, value]) => {
        const weight = score.weights[key];
        return (
          <li key={key} className="text-xs">
            <div className="flex items-center justify-between gap-2">
              <span>{humanise(key)}</span>
              <span className="tabular text-muted-foreground">{value.toFixed(2)}{weight !== undefined && ` × ${weight.toFixed(2)}`}</span>
            </div>
            <div className="gn-bar mt-1"><div className="gn-bar-fill gn-bar-fill--verified" style={{ transform: `scaleX(${Math.max(value, 0.02)})` }} /></div>
          </li>
        );
      })}
    </ul>
    {Object.keys(score.weights).length < 4 && (
      <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
        Fewer than four components carry weight here. A signal that could not be measured is dropped and its weight
        redistributed — never scored zero, which would read as "no risk" rather than "unknown".
      </p>
    )}
  </>;
}

function TrackRow({ label, track }: { label: string; track: { horizon_days: number; points: { uncertainty_km: number; lat: number; lon: number }[] } }) {
  const end = track.points[track.points.length - 1];
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="font-medium">{label} · {track.horizon_days} d</span>
      <span className="tabular text-muted-foreground">{formatCoord(end.lat, end.lon)} ± {end.uncertainty_km.toFixed(0)} km</span>
    </div>
  );
}

function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  const [open, setOpen] = React.useState(false);
  const seen = new Set<string>();
  const unique = evidence.filter((e) => {
    const key = `${e.kind}:${e.ref}:${e.detail}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  if (unique.length === 0) return <p className="text-xs text-muted-foreground">No evidence recorded.</p>;
  const shown = open ? unique : unique.slice(0, 6);
  return (
    <>
      <ul className="space-y-1.5">
        {shown.map((item, index) => {
          const Icon = EVIDENCE_ICON[item.kind] ?? Check;
          return (
            <li key={`${item.ref}-${index}`} className="flex items-start gap-2 text-[11px]">
              <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <p className="truncate font-mono text-foreground">{item.ref}</p>
                {item.detail && <p className="text-muted-foreground">{item.detail}</p>}
              </div>
            </li>
          );
        })}
      </ul>
      {unique.length > 6 && (
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
          className="mt-2 flex cursor-pointer items-center gap-1 text-[11px] text-primary hover:underline">
          <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} />
          {open ? "Show less" : `Show all ${unique.length} records`}
        </button>
      )}
    </>
  );
}

/**
 * A labelled value. `mono` is for technical values only — ids, tiles,
 * coordinates, detector codes.
 */
function Field({ label, value, mono }: { label: React.ReactNode; value: string; mono?: boolean }) {
  return (
    <>
      <dt className="kv-key">{label}</dt>
      <dd className={cn("tabular truncate text-right text-[12.5px]", mono && "font-mono text-[11.5px]")}>{value}</dd>
    </>
  );
}
