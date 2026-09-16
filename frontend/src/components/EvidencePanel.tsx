import {
  Check,
  ChevronDown,
  Compass,
  Droplets,
  MousePointerClick,
  Radar,
  Satellite,
  Waves,
  X,
} from "lucide-react";
import * as React from "react";
import type { Evidence, PriorityScore, RunArtefact } from "@/lib/types";
import { cn, formatCoord, formatDate, humanise } from "@/lib/utils";
import { EmptyState } from "@/components/ui/primitives";

/**
 * The evidence trail for one detection — PRD 8's explainability requirement.
 *
 * Deliberately exhaustive rather than summarised: every check the Verification
 * Agent ran (including the ones that passed), the drift envelope, the full
 * ranked river distribution, the dark-vessel contacts with their disclaimer,
 * and the score decomposition with its weights. A researcher auditing why a
 * site was flagged should not have to leave this panel.
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

interface EvidencePanelProps {
  artefact: RunArtefact;
  detectionId: string | null;
  score: PriorityScore | undefined;
  onClose: () => void;
}

export function EvidencePanel({ artefact, detectionId, score, onClose }: EvidencePanelProps) {
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

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <header className="sticky top-0 z-10 flex items-start justify-between gap-2 border-b border-border bg-card/95 px-3 py-2.5 backdrop-blur">
        <div className="min-w-0">
          <p className="truncate font-mono text-xs text-muted-foreground">{detection.id}</p>
          <p className="tabular mt-0.5 text-sm font-medium">
            {formatCoord(detection.lat, detection.lon)}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close evidence panel"
          className="cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </header>

      {/* The answer before the working. An analyst opening this panel wants
          three things immediately — how urgent, did it survive verification,
          how confident — and everything below is the evidence for them. All
          three are read off the existing artefact and score; nothing here is
          computed a second way. */}
      <div className="border-b border-border px-3 py-3">
        <div className="flex items-baseline gap-3">
          <span className="tabular font-mono text-[26px] font-medium leading-none tracking-tight">
            {score ? score.score.toFixed(3) : "—"}
          </span>
          <span className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
            Priority
          </span>
          <span className="ml-auto shrink-0 text-[11px] font-medium">
            {verification ? (
              verification.verified ? (
                <span className="text-success">Verified</span>
              ) : (
                <span className="text-destructive">Rejected</span>
              )
            ) : (
              <span className="text-muted-foreground">Unverified</span>
            )}
          </span>
        </div>
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Confidence{" "}
          <span className="tabular font-mono text-foreground">
            {detection.confidence.toFixed(2)}
          </span>
          {" · "}
          {detection.detector.toUpperCase()}
        </p>
      </div>

      <div className="space-y-7 px-4 py-5">
        <Section title="Detection" fr="FR-1" stage="1 · What was found">
          <dl className="kv">
            <Field label="Acquired" value={formatDate(detection.acquired_at)} />
            <Field label="Tile" value={detection.tile_id} mono />
            <Field label="Detector" value={detection.detector.toUpperCase()} />
            <Field label="Raw confidence" value={detection.confidence.toFixed(3)} />
            <Field label="Mean FDI" value={detection.fdi_mean.toFixed(4)} />
            <Field label="Mean NDVI" value={detection.ndvi_mean.toFixed(4)} />
            <Field label="Area" value={`${detection.area_km2.toFixed(4)} km² (${detection.area_px} px)`} />
          </dl>
        </Section>

        {verification && (
          <Section
            stage="2 · Checks and uncertainty"
            title="Verification"
            fr="FR-2"
            badge={
              verification.verified ? (
                <span className="text-[11px] font-medium text-success">Verified</span>
              ) : (
                <span className="text-[11px] font-medium text-destructive">Rejected</span>
              )
            }
          >
            <p className="mb-2 text-xs text-muted-foreground">
              Every documented false-positive mode is tested and reported —
              passes included, so a verified site shows what it survived.
            </p>
            <ul className="space-y-2">
              {verification.checks.map((check) => (
                <li
                  key={check.name}
                  className={cn(
                    "border-l-2 py-1.5 pl-2.5 text-xs",
                    check.disqualified
                      ? "border-l-destructive/70"
                      : "border-l-success/45",
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    {check.disqualified ? (
                      <X className="size-3.5 shrink-0 text-destructive" />
                    ) : (
                      <Check className="size-3.5 shrink-0 text-success" />
                    )}
                    <span className="font-medium">{humanise(check.name)}</span>
                  </div>
                  <p className="mt-1 leading-snug text-muted-foreground">{check.reason}</p>
                  {Object.keys(check.detail).length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {Object.entries(check.detail).map(([key, value]) => (
                        <span
                          key={key}
                          className="tabular rounded bg-background px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                        >
                          {key}={value}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">
              Verified confidence:{" "}
              <span className="tabular font-medium text-foreground">
                {verification.confidence.toFixed(3)}
              </span>
            </p>
          </Section>
        )}

        {(backward || forward) && (
          <Section title="Drift" fr="FR-3" stage="3 · Where it moves">
            <div className="space-y-2 text-xs">
              {forward && <TrackRow label="Forward" track={forward} />}
              {backward && <TrackRow label="Backward" track={backward} />}
              <p className="text-muted-foreground">
                Ensemble of {(forward ?? backward)!.ensemble_size} members, seed{" "}
                <span className="font-mono">{(forward ?? backward)!.seed}</span> — the same
                seed reproduces the same envelope.
              </p>
            </div>
          </Section>
        )}

        {attribution && (
          <Section title="Probable source" fr="FR-4">
            {attribution.candidates.length === 0 ? (
              <p className="text-xs text-muted-foreground">{attribution.note}</p>
            ) : (
              <>
                <ul className="space-y-1.5">
                  {attribution.candidates.map((river) => (
                    <li key={river.name} className="text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-medium">{river.name}</span>
                        <span className="tabular shrink-0 text-muted-foreground">
                          {(river.probability * 100).toFixed(0)}%
                        </span>
                      </div>
                      <div
                        className="mt-1 h-1 overflow-hidden bg-muted"
                        role="img"
                        aria-label={`${river.name}: ${(river.probability * 100).toFixed(0)} percent probability`}
                      >
                        <div
                          className="h-full bg-primary transition-all duration-300"
                          style={{ width: `${Math.max(river.probability * 100, 2)}%` }}
                        />
                      </div>
                      <p className="tabular mt-0.5 text-[11px] text-muted-foreground">
                        {river.distance_km.toFixed(1)} km from the backtrack ·{" "}
                        {river.emission_tonnes_yr.toLocaleString()} t/yr emitted
                      </p>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
                  {attribution.note}
                </p>
              </>
            )}
          </Section>
        )}

        {correlation && (
          <Section title="Dark vessel correlation" fr="FR-5" stage="4 · Risk and attribution">
            {correlation.dark_vessels.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No AIS-unmatched SAR observations in the available records for this window.
                {correlation.matched_vessels > 0 &&
                  ` ${correlation.matched_vessels} AIS-matched observation(s) in this window.`}
              </p>
            ) : (
              <>
                <p className="text-xs">
                  <span className="font-medium">{correlation.dark_vessels.length}</span> SAR
                  observation(s) with no matching AIS record. Correlation strength{" "}
                  <span className="tabular font-medium">
                    {correlation.correlation_strength.toFixed(2)}
                  </span>
                  .
                </p>
                <ul className="mt-1.5 space-y-1">
                  {correlation.dark_vessels.map((vessel) => (
                    <li key={vessel.id} className="tabular font-mono text-[11px] text-muted-foreground">
                      {vessel.id} · {formatCoord(vessel.lat, vessel.lon)}
                      {vessel.length_m ? ` · ${vessel.length_m} m` : ""}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="mt-2 border-l-2 border-l-warning/70 py-1 pl-2.5 text-[11px] leading-snug text-muted-foreground">
              {correlation.disclaimer}
            </p>
          </Section>
        )}

        {score && (
          <Section title="Priority score" fr="FR-6.1">
            <p className="tabular mb-2 text-2xl font-semibold">{score.score.toFixed(3)}</p>
            <ul className="space-y-1.5">
              {Object.entries(score.components).map(([key, value]) => {
                const weight = score.weights[key];
                return (
                  <li key={key} className="text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span>{humanise(key)}</span>
                      <span className="tabular text-muted-foreground">
                        {value.toFixed(2)}
                        {weight !== undefined && ` × ${weight.toFixed(2)}`}
                      </span>
                    </div>
                    <div className="mt-1 h-1 overflow-hidden bg-muted">
                      <div
                        className="h-full bg-chart-verified transition-all duration-300"
                        style={{ width: `${Math.max(value * 100, 2)}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
            {Object.keys(score.weights).length < 4 && (
              <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
                Fewer than four components carry weight here. A signal that could
                not be measured is dropped and its weight redistributed — never
                scored zero, which would read as "no risk" rather than "unknown".
              </p>
            )}
          </Section>
        )}

        <Section title="Evidence trail" fr="PRD §8" stage="5 · Decision record">
          <EvidenceList
            evidence={[
              ...detection.evidence,
              ...(verification?.evidence ?? []),
              ...(forward?.evidence ?? []),
              ...(attribution?.evidence ?? []),
              ...(correlation?.evidence ?? []),
              ...(score?.evidence ?? []),
            ]}
          />
        </Section>
      </div>
    </div>
  );
}

function TrackRow({ label, track }: { label: string; track: { horizon_days: number; points: { uncertainty_km: number; lat: number; lon: number }[] } }) {
  const end = track.points[track.points.length - 1];
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="font-medium">
        {label} · {track.horizon_days} d
      </span>
      <span className="tabular text-muted-foreground">
        {formatCoord(end.lat, end.lon)} ± {end.uncertainty_km.toFixed(0)} km
      </span>
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

  if (unique.length === 0) {
    return <p className="text-xs text-muted-foreground">No evidence recorded.</p>;
  }

  const shown = open ? unique : unique.slice(0, 4);

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
      {unique.length > 4 && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="mt-2 flex cursor-pointer items-center gap-1 text-[11px] text-primary hover:underline"
          aria-expanded={open}
        >
          <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} />
          {open ? "Show less" : `Show all ${unique.length} records`}
        </button>
      )}
    </>
  );
}

/**
 * One stage of the investigation, rendered as a section of a single document
 * rather than as its own panel.
 *
 * `stage` is the analyst's question at this point — detection, evidence,
 * movement, risk, decision — and `fr` is the requirement that answers it. Both
 * are shown: the stage is what an operator is reading for, the FR is what makes
 * every figure on screen traceable back to the agent that produced it, which is
 * the PRD §12 evidence bullet.
 */
function Section({
  title,
  fr,
  stage,
  badge,
  children,
}: {
  title: string;
  fr: string;
  stage?: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <details className="atlas-evidence-section" open={fr === "FR-2"}>
      <summary>
        <span className="atlas-evidence-number" title={fr}>{fr.startsWith("FR-") ? fr.replace("FR-", "0") : "↗"}</span>
        <span><span className="atlas-evidence-title">{title}</span>
          {stage && <small>{stage.replace(/^\d · /, "")}</small>}</span>
        {badge}<ChevronDown size={14} className="ml-auto shrink-0" />
      </summary>
      <div className="atlas-evidence-content">{children}</div>
    </details>
  );
}

/**
 * A labelled value. Label quiet and proportional, value the thing you read.
 *
 * `mono` is for technical values only — ids, tiles, coordinates, detector
 * codes. Measurements stay proportional with tabular figures, which aligns
 * them in a column without dressing prose up as machine output.
 */
function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <>
      <dt className="kv-key">{label}</dt>
      <dd
        className={cn(
          "tabular truncate text-right text-[12.5px]",
          mono && "font-mono text-[11.5px]",
        )}
      >
        {value}
      </dd>
    </>
  );
}
