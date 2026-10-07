/**
 * The state of each agent for one run under one ablation setting.
 *
 * This mirrors ghostnet/webapp/planning.py and nothing else: an agent is
 * ABLATED because the operator switched it off, DEGRADED because its own input
 * was missing on the exporting machine (the run's degradation notes say so),
 * and REDUCED INPUT because something upstream of it was removed. The served
 * console never runs the upstream agents live, so RUNNING and FAILED are not
 * states it can truthfully show and are not modelled.
 */
export type AgentState = "complete" | "degraded" | "ablated" | "reduced";

export interface AgentStatus {
  id: string;
  state: AgentState;
  /** Why the state is not COMPLETE, in the planner's own terms. Empty when complete. */
  reasons: string[];
}

export const AGENT_ORDER = ["detection", "verification", "drift", "attribution", "vessels", "prioritisation"] as const;

export const STATE_LABEL: Record<AgentState, string> = {
  complete: "Complete",
  degraded: "Degraded",
  ablated: "Ablated",
  reduced: "Reduced input",
};

/** Degradation notes are written "<agent>: ..." by the exporter. */
function degradedAgents(notes: readonly string[]): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const note of notes) {
    const match = note.match(/^(detection|verification|drift|attribution|vessels|prioritisation):\s*(.*)$/s);
    if (!match) continue;
    out.set(match[1], [...(out.get(match[1]) ?? []), match[2]]);
  }
  return out;
}

export function agentStatuses(
  ablated: ReadonlySet<string>,
  runDegradations: readonly string[],
  hasProtectedAreas: boolean,
): AgentStatus[] {
  const degraded = degradedAgents(runDegradations);
  const reasons = new Map<string, string[]>(AGENT_ORDER.map(id => [id, []]));
  const add = (id: string, why: string) => reasons.get(id)!.push(why);

  if (ablated.has("verification")) {
    for (const id of ["drift", "attribution", "vessels"]) {
      add(id, "Re-admitted raw candidates have no output from this agent: the offline run computed it only for verified detections.");
    }
    add("prioritisation", "Scores raw detector output, false positives included.");
  }
  if (ablated.has("drift")) {
    add("attribution", "No backward trajectory to cross-reference, so no source can be attributed.");
    add("prioritisation", "Loses the drift-urgency component.");
  }
  if (ablated.has("vessels") || degraded.has("vessels")) {
    add("prioritisation", ablated.has("vessels")
      ? "Loses the dark-vessel component."
      : "Dark-vessel signal unavailable in this run; its weight is redistributed, not scored zero.");
  }
  if (!hasProtectedAreas) {
    add("prioritisation", "No protected-area data; ecological risk is dropped and its weight redistributed.");
  }

  return AGENT_ORDER.map(id => {
    if (ablated.has(id)) return { id, state: "ablated", reasons: ["Switched off for this plan."] };
    if (degraded.has(id)) return { id, state: "degraded", reasons: degraded.get(id)! };
    const why = reasons.get(id)!;
    return { id, state: why.length ? "reduced" : "complete", reasons: why };
  });
}
