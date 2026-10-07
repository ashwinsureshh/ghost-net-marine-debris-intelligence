import { AlertTriangle, CheckCircle2, Ship } from "lucide-react";
import React from "react";
import { motion, useReducedMotion } from "motion/react";
import type { DispatchPlan, PriorityScore } from "@/lib/types";
import { formatDelta, rankDeltas } from "@/lib/ranking";
import { DURATION, EASE_OUT, staggerStyle, useAnimatedNumber } from "@/lib/motion";
import { cn, humanise } from "@/lib/utils";
import { Button, EmptyState, Skeleton } from "@/components/ui/primitives";

interface DispatchPanelProps {
  plan: DispatchPlan | null;
  scores: PriorityScore[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onApprove: () => void;
  approved: boolean;
  approvedBy: string | null;
  prioritisationAblated: boolean;
}

/** The ranked, capacity-bounded answer (FR-6.2) with its rationale (FR-6.3). */
export function DispatchPanel({
  plan,
  scores,
  loading,
  selectedId,
  onSelect,
  onApprove,
  approved,
  approvedBy,
  prioritisationAblated,
}: DispatchPanelProps) {
  // The OS setting is already honoured in CSS; motion/react needs telling
  // separately, and an operator console is exactly the kind of tool where
  // someone who asked for no motion meant it.
  const reduceMotion = useReducedMotion();
  // The previous plan for the SAME region, so each row can say how it moved
  // when capacity, horizon or an ablation changed. A plan for another region
  // is not a "previous" plan: every row there would be meaningless NEW.
  const history = React.useRef<{ plan: DispatchPlan | null; prev: DispatchPlan | null }>({ plan: null, prev: null });
  if (plan && plan !== history.current.plan) {
    const last = history.current.plan;
    history.current = { plan, prev: last && last.region_id === plan.region_id ? last : null };
  }
  const deltas = React.useMemo(
    () => rankDeltas(history.current.prev?.assignments ?? null, plan?.assignments ?? []),
    [plan],
  );
  if (loading) {
    return (
      <div className="space-y-3 p-3.5">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }

  if (prioritisationAblated) {
    return (
      <EmptyState icon={AlertTriangle} title="Prioritisation agent is switched off">
        With FR-6 ablated there is no ranked, capacity-bounded plan — the operator
        gets an unordered pile of verified detections and must decide unaided.
        That is the pre-existing state of the art this project exists to improve
        on (PRD §2), and it is what the ablation is meant to show.
      </EmptyState>
    );
  }

  if (!plan || plan.assignments.length === 0) {
    return (
      <EmptyState icon={Ship} title="No sites meet the bar for dispatch">
        Either every candidate was disqualified by the Verification Agent, or
        vessel capacity is set to zero. Use the Rejected filter in Explore to see what was
        thrown away and why.
      </EmptyState>
    );
  }

  const scoreById = new Map(scores.map((s) => [s.detection_id, s]));

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <ol className="divide-y divide-border">
          {plan.assignments.map((assignment, index) => {
            const score = scoreById.get(assignment.detection_id);
            const isSelected = assignment.detection_id === selectedId;
            // Both read off the existing PriorityScore; nothing new computed.
            const confidence = score?.components?.detection_confidence;
            const topSignals = Object.entries(score?.components ?? {})
              .filter(([key]) => key !== "detection_confidence")
              .sort((a, b) => b[1] - a[1])
              .slice(0, 2);
            return (
              // Reordering is motion's layout animation, so a site visibly
              // travels to its new rank. Entering rows use a CSS entrance and
              // leaving rows go at once: content never waits on an animation
              // frame to appear or to disappear.
              <motion.li
                key={assignment.detection_id}
                layout={reduceMotion ? false : "position"}
                transition={{ duration: DURATION.normal, ease: EASE_OUT }}
                className="gn-enter"
                style={staggerStyle(index, 6)}
              >
                <button
                  type="button"
                  onClick={() => onSelect(assignment.detection_id)}
                  aria-current={isSelected ? "true" : undefined}
                  className={cn(
                    "w-full cursor-pointer px-4 py-3 text-left transition-colors duration-150",
                    isSelected
                      ? "row-rule bg-accent/55"
                      : "hover:bg-accent/25",
                  )}
                >
                  {/* Compact by default; the rationale — the longest thing
                      here — appears only for the selected row. Showing every
                      row's full reasoning at once is what made the queue
                      unreadable, not the amount of information in it. */}
                  <div className="flex items-baseline gap-2.5">
                    <span
                      className={cn(
                        "w-5 shrink-0 font-mono text-[11px] tabular-nums",
                        isSelected ? "text-primary" : "text-muted-foreground",
                      )}
                    >
                      {String(assignment.rank).padStart(2, "0")}
                    </span>
                    <p className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground">
                      {assignment.detection_id}
                    </p>
                    <DeltaChip delta={deltas.get(assignment.detection_id)} />
                    <span className="tabular shrink-0 font-mono text-[13px] font-medium">
                      <AnimatedScore value={assignment.score} />
                    </span>
                  </div>

                  <p className="mt-1 pl-[1.875rem] text-[12px] text-muted-foreground">
                    <span className="text-success">Verified</span>
                    {confidence !== undefined && (
                      <>
                        {" · confidence "}
                        <span className="tabular font-mono text-foreground">
                          {confidence.toFixed(2)}
                        </span>
                      </>
                    )}
                  </p>

                  {topSignals.length > 0 && (
                    <p className="mt-0.5 flex flex-wrap gap-x-2 pl-[1.875rem] text-[11px] text-muted-foreground">
                      {topSignals.map(([key, value], i) => (
                        <React.Fragment key={key}>
                          {i > 0 && <span aria-hidden="true">·</span>}
                          <span>
                            {humanise(key)}{" "}
                            <span className="tabular font-mono text-foreground">
                              {value.toFixed(2)}
                            </span>
                          </span>
                        </React.Fragment>
                      ))}
                    </p>
                  )}

                  {isSelected && (
                    <p className="mt-2 pl-[1.875rem] text-[12px] leading-relaxed text-foreground">
                      {assignment.rationale}
                      <span className="mt-1 block text-[11px] text-muted-foreground">
                        {assignment.vessel_id} ·{" "}
                        {assignment.rationale_source === "llm" ? "Claude" : "Template"}
                      </span>
                    </p>
                  )}
                </button>
              </motion.li>
            );
          })}
        </ol>

        {plan.deferred.length > 0 && (
          <div className="border-t border-border px-3 py-2.5">
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{plan.deferred.length} deferred</span> —
              scored but beyond the {plan.vessel_capacity}-vessel capacity for this{" "}
              {plan.planning_horizon_days}-day cycle.
            </p>
          </div>
        )}
      </div>

      <div className="border-t border-border bg-card/60 p-3">
        {approved ? (
          <div className="flex items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2">
            <CheckCircle2 className="size-4 shrink-0 text-success" />
            <p className="text-xs">
              Reviewed and approved by{" "}
              <span className="font-medium">{approvedBy}</span>. Approval is recorded
              against this run.
            </p>
          </div>
        ) : (
          <>
            <div className="mb-2 flex items-start gap-2 rounded-md border border-warning/30 bg-warning/10 px-3 py-2">
              <AlertTriangle className="size-4 shrink-0 text-warning" />
              <p className="text-xs text-foreground">
                Not final. FR-6.4 requires a named human to review this plan before
                it is treated as a recommendation.
              </p>
            </div>
            <Button variant="warning" className="w-full" onClick={onApprove}>
              Review and approve plan
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function AnimatedScore({ value }: { value: number }) {
  return <>{useAnimatedNumber(value).toFixed(3)}</>;
}

/** How this site moved since the previous plan. Silent on the first plan. */
function DeltaChip({ delta }: { delta: number | null | undefined }) {
  if (delta === undefined || delta === 0) return null;
  const { label, tone } = formatDelta(delta);
  const words = delta === null ? "new in this plan" : delta > 0 ? `up ${delta}` : `down ${-delta}`;
  return (
    <span key={label} className={`gn-delta gn-delta--${tone} gn-enter`} aria-label={words}>
      {label}
    </span>
  );
}
