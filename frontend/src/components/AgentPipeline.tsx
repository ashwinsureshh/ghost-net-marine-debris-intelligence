import { ChevronDown } from "lucide-react";
import * as React from "react";
import type { AgentMeta, PlanResponse, RunArtefact } from "@/lib/types";
import { agentStatuses, STATE_LABEL, type AgentStatus } from "@/lib/pipeline";
import { humanise } from "@/lib/utils";
import { Term } from "@/components/Term";

/**
 * The six agents as one chain, for a COMPLETED run.
 *
 * On opening a run the chain lights once, top to bottom, to show that each
 * agent's output is the next one's input. It is a replay of the order the
 * workstation ran them in, not live progress: the served console never runs
 * the upstream agents. Switching an agent off shows its effect travelling
 * downstream, with the planner's own reason at each step.
 */
export function AgentPipeline({ agents, artefact, plan, ablated, ablatable, onToggleAgent, disabled }: {
  agents: AgentMeta[]; artefact: RunArtefact; plan: PlanResponse | null; ablated: Set<string>;
  ablatable: string[]; onToggleAgent: (id: string, active: boolean) => void; disabled: boolean;
}) {
  const statuses = React.useMemo(
    () => agentStatuses(ablated, artefact.degradations, artefact.protected_areas.length > 0),
    [ablated, artefact],
  );
  const [open, setOpen] = React.useState<string | null>(null);
  const byId = new Map(agents.map(a => [a.id, a]));
  const facts = React.useMemo(() => agentFacts(artefact, plan), [artefact, plan]);

  return (
    <section className="gn-pipeline" aria-label="Agent pipeline">
      <header>
        <span className="atlas-eyebrow">Agent pipeline · completed run</span>
        <p>Each agent's output is the next one's input. Switch one off (<Term term="Ablation">ablation</Term>) to see
          what reaches the plan without it.</p>
      </header>
      <ol key={artefact.run_id}>
        {statuses.map((status, index) => {
          const agent = byId.get(status.id);
          const canAblate = ablatable.includes(status.id);
          const expanded = open === status.id;
          return (
            <li key={status.id} className={`gn-agent gn-agent--${status.state} gn-agent-enter`}
              style={{ animationDelay: `${index * 120}ms` }}>
              {index > 0 && <span className="gn-agent-link" aria-hidden="true"
                style={{ animationDelay: `${index * 120 - 60}ms` }} />}
              <div className="gn-agent-row">
                <button type="button" className="gn-agent-name" aria-expanded={expanded}
                  aria-controls={`agent-detail-${status.id}`} onClick={() => setOpen(expanded ? null : status.id)}>
                  <span className="gn-agent-fr">{agent?.fr ?? ""}</span>
                  <span>{agent?.name ?? humanise(status.id)}</span>
                  <ChevronDown size={13} className="gn-agent-chevron" />
                </button>
                <StateBadge status={status} />
                {canAblate ? (
                  <button type="button" role="switch" aria-checked={!ablated.has(status.id)} disabled={disabled}
                    className="gn-agent-switch" aria-label={`${agent?.name ?? status.id} active`}
                    title={disabled ? "Ablation needs the live server" : undefined}
                    onClick={() => onToggleAgent(status.id, ablated.has(status.id))}><span /></button>
                ) : <span className="gn-agent-fixed" title="Detection cannot be switched off: with it off there is no run.">always on</span>}
              </div>
              {expanded && (
                  <div id={`agent-detail-${status.id}`} className="gn-agent-detail gn-enter">
                    <dl>{facts[status.id]?.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
                    {status.reasons.length > 0 && <ul>{status.reasons.map(r => <li key={r}>{r}</li>)}</ul>}
                  </div>
              )}
              {!expanded && status.reasons.length > 0 && status.state !== "ablated" &&
                <p className="gn-agent-reason">{status.reasons[0]}</p>}
            </li>
          );
        })}
      </ol>
      <p className="gn-pipeline-note">A replay of the order the agents ran in on the workstation, not live processing.
        Only prioritisation is recomputed on this server.</p>
    </section>
  );
}

function StateBadge({ status }: { status: AgentStatus }) {
  return (
    <span key={status.state} className={`gn-state gn-state--${status.state} gn-state-change`}>
      {STATE_LABEL[status.state]}
    </span>
  );
}

function agentFacts(artefact: RunArtefact, plan: PlanResponse | null): Record<string, [string, string][]> {
  const verified = artefact.verifications.filter(v => v.verified).length;
  const failed = new Map<string, number>();
  for (const v of artefact.verifications) for (const c of v.checks) if (c.disqualified) failed.set(c.name, (failed.get(c.name) ?? 0) + 1);
  const top = [...failed].sort((a, b) => b[1] - a[1])[0];
  const anyTrack = Object.values(artefact.forward)[0];
  const topRivers = new Set(Object.values(artefact.attributions).map(a => a.candidates[0]?.name).filter(Boolean));
  const correlations = Object.values(artefact.correlations);
  const withUnmatched = correlations.filter(c => c.dark_vessels.length > 0).length;
  const detectors = new Set(artefact.detections.map(d => d.detector.toUpperCase()));
  return {
    detection: [["Candidates", String(artefact.detections.length)], ["Detector", [...detectors].join(", ") || "—"],
      ["Sentinel-2 tiles", String(artefact.provenance.tile_count)]],
    verification: [["Verified", `${verified} of ${artefact.detections.length}`],
      ["Rejected", String(artefact.detections.length - verified)],
      ["Most common failed check", top ? `${humanise(top[0])} (${top[1]})` : "—"]],
    drift: [["Forward trajectories", String(Object.keys(artefact.forward).length)],
      ["Ensemble", anyTrack ? `${anyTrack.ensemble_size} members · ${anyTrack.horizon_days} d` : "—"],
      ["Current field", anyTrack?.current_field ?? "—"]],
    attribution: [["Sites attributed", String(Object.keys(artefact.attributions).length)],
      ["Distinct top-ranked rivers", String(topRivers.size)], ["Status", "Modelled likely source, not confirmed"]],
    vessels: [["Sites correlated", String(correlations.length)],
      ["Sites with an AIS-unmatched observation", String(withUnmatched)], ["Unit", "0.01° hourly grid observations"]],
    prioritisation: [["Sites considered", String(plan?.considered ?? "—")],
      ["Dispatch sites", String(plan?.plan?.assignments.length ?? 0)], ["Human approval", "Required"]],
  };
}
