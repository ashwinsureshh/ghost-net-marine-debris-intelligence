import * as React from "react";
import type { AppMeta, BenchmarkReport, ReadyReport, RunArtefact, RunSummary } from "@/lib/types";
import { api } from "@/lib/api";
import { staggerStyle } from "@/lib/motion";
import { Skeleton } from "@/components/ui/primitives";

type Tone = "ok" | "warn" | "off" | "muted";
interface Row { label: string; value: string; tone?: Tone; note?: string }

/**
 * What this instance is running and what it can reach, from /api/meta,
 * /api/ready and the loaded artefacts. No secrets: the LLM row says whether a
 * rationale writer is configured, never with what key.
 */
export function SystemView({ meta, benchmark, runs, artefact, staticMode }: {
  meta: AppMeta | null; benchmark: BenchmarkReport | null; runs: RunSummary[];
  artefact: RunArtefact | null; staticMode: boolean;
}) {
  const [ready, setReady] = React.useState<ReadyReport | null | undefined>(undefined);
  const [readyError, setReadyError] = React.useState<string | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    api.ready().then(r => { if (!cancelled) setReady(r); })
      .catch(e => { if (!cancelled) { setReady(null); setReadyError(String(e.message ?? e)); } });
    return () => { cancelled = true; };
  }, []);

  const real = runs.filter(r => !r.unreadable && !r.inputs_are_synthetic);
  const withoutGfw = real.filter(r => r.degradation_notes?.some(n => n.startsWith("vessels:")));
  const checkpoints = new Set(artefact?.provenance.notes.flatMap(n => [...n.matchAll(/Checkpoint (\S+\.pt)/g)].map(m => m[1])) ?? []);
  const anyTrack = artefact ? Object.values(artefact.forward)[0] : undefined;

  const services: Row[] = [
    { label: "API", value: staticMode ? "Not used" : ready === undefined ? "Checking…" : ready ? "Reachable" : "Unreachable",
      tone: staticMode ? "muted" : ready ? "ok" : ready === undefined ? "muted" : "off", note: staticMode ? "Offline export: reads are served from the bundle." : readyError ?? undefined },
    { label: "Run artefacts", value: staticMode ? `${runs.length} bundled` : ready?.checks.artefacts ? `${ready.checks.artefacts.readable} readable` : "—",
      tone: ready?.checks.artefacts?.ok === false ? "off" : "ok",
      note: ready?.checks.artefacts?.unreadable.length ? `Unreadable: ${ready.checks.artefacts.unreadable.join(", ")}` : undefined },
    { label: "Approval store", value: staticMode ? "Read-only" : ready?.checks.approvals ? `${ready.checks.approvals.backend ?? "unknown"} · ${ready.checks.approvals.durable ? "durable" : "not durable"}` : "—",
      tone: staticMode ? "muted" : ready?.checks.approvals?.ok ? (ready.checks.approvals.durable ? "ok" : "warn") : "muted",
      note: !staticMode && ready?.checks.approvals && !ready.checks.approvals.durable ? "Approvals may not survive a restart of this instance." : undefined },
    { label: "LLM rationale service", value: staticMode ? "Template (offline)" : meta?.rationale_source === "llm" ? "Claude, configured" : "Template",
      tone: meta?.rationale_source === "llm" && !staticMode ? "ok" : "muted", note: meta?.rationale_note },
    { label: "Global Fishing Watch", value: `${real.length - withoutGfw.length} of ${real.length} regions`, tone: withoutGfw.length ? "warn" : "ok",
      note: "Fetched on the workstation at export time; this server never calls GFW." + (withoutGfw.length ? ` Missing: ${withoutGfw.map(r => (r.region_name ?? r.run_id).split(" — ")[0]).join(", ")}.` : "") },
    { label: "Satellite catalogue", value: "Not queried here", tone: "muted",
      note: "Sentinel-2 scenes were streamed from Planetary Computer on the workstation. Nothing on this page is live imagery." },
  ];

  const models: Row[] = [
    { label: "Detector checkpoint", value: checkpoints.size ? [...checkpoints].join(", ") : "Not recorded", note: "For the open region." },
    { label: "Detector", value: artefact ? [...new Set(artefact.detections.map(d => d.detector.toUpperCase()))].join(", ") : "—" },
    { label: "Verification thresholds", value: artefact ? `${Object.keys(artefact.provenance.verification_thresholds).length} fitted on MARIDA train` : "—" },
    { label: "Drift model", value: anyTrack ? `RK4 ensemble · ${anyTrack.ensemble_size} members · seed ${anyTrack.seed}` : "—" },
    { label: "Benchmark", value: benchmark?.available ? `${benchmark.dataset} ${benchmark.dataset_version}` : "Unavailable",
      tone: benchmark?.available ? "ok" : "warn", note: benchmark?.available ? benchmark.dataset_doi : benchmark?.unavailable_reason ?? undefined },
  ];

  const data: Row[] = [
    { label: "Ocean currents", value: anyTrack?.current_field ?? "—" },
    { label: "Sentinel-2", value: artefact ? sceneSummary(artefact.provenance.tile_ids, artefact.provenance.tile_count) : "—",
      note: "Acquisitions used by the open region's run." },
    { label: "River dataset", value: "Meijer et al. 2021 (The Ocean Cleanup)" },
    { label: "Protected areas", value: artefact ? `${artefact.protected_areas.length} in the open region` : "—" },
    ...Object.entries(artefact?.provenance.dataset_sources ?? {}).map(([k, v]) => ({ label: `Source · ${k}`, value: v })),
  ];

  const system: Row[] = [
    { label: "Application version", value: meta?.version ?? "—" },
    { label: "Artefact schema", value: meta?.artefact_schema ?? "—" },
    { label: "Environment", value: staticMode ? "Offline static export" : "Live server", tone: staticMode ? "warn" : "ok" },
    { label: "Open region exported", value: artefact ? `${artefact.provenance.generated_at.slice(0, 10)} · ${artefact.provenance.git_commit?.slice(0, 10) ?? "no commit"}` : "—" },
  ];

  return (
    <div className="gn-page">
      <header className="gn-page-head">
        <span className="atlas-eyebrow">Instance</span>
        <h1>System</h1>
        <p>What this console is running and what it can reach. Everything here is read from the server's own endpoints and
          the loaded run; secrets are never shown.</p>
      </header>
      <div className="gn-system-grid">
        <Group title="Services" rows={services} loading={ready === undefined && !staticMode} />
        <Group title="Models" rows={models} />
        <Group title="Data" rows={data} />
        <Group title="System" rows={system} />
      </div>
    </div>
  );
}

function Group({ title, rows, loading }: { title: string; rows: Row[]; loading?: boolean }) {
  return (
    <section className="gn-system-group" aria-label={title}>
      <h2>{title}</h2>
      <dl>
        {rows.map((row, i) => (
          <div key={row.label} className="gn-enter" style={staggerStyle(i)}>
            <dt><span className={`gn-dot gn-dot--${row.tone ?? "muted"}`} aria-hidden="true" />{row.label}</dt>
            <dd>{loading && row.value === "Checking…" ? <Skeleton className="h-3 w-24" /> : row.value}
              {row.note && <small>{row.note}</small>}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** "23 scenes · S2-18QYF-20201010 … S2-18QYF-20210131": the span, not every id. */
function sceneSummary(ids: string[], count: number): string {
  if (!ids.length) return `${count} scene(s)`;
  return ids.length === 1 ? `1 scene · ${ids[0]}` : `${count} scenes · ${ids[0]} … ${ids[ids.length - 1]}`;
}
