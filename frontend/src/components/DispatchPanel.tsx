import { AlertTriangle, Anchor, Bot, CheckCircle2, FileText, Ship } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { DispatchPlan, PriorityScore } from "@/lib/types";
import { cn, humanise } from "@/lib/utils";
import { Badge, Button, EmptyState, Skeleton } from "@/components/ui/primitives";

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
        vessel capacity is set to zero. Check the Rejected tab to see what was
        thrown away and why.
      </EmptyState>
    );
  }

  const scoreById = new Map(scores.map((s) => [s.detection_id, s]));

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <ol className="flex flex-col gap-1.5 p-2">
          <AnimatePresence initial={false}>
          {plan.assignments.map((assignment, index) => {
            const score = scoreById.get(assignment.detection_id);
            const isSelected = assignment.detection_id === selectedId;
            return (
              <motion.li
                key={assignment.detection_id}
                layout={reduceMotion ? false : "position"}
                initial={reduceMotion ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduceMotion ? undefined : { opacity: 0 }}
                transition={{
                  duration: 0.18,
                  delay: reduceMotion ? 0 : Math.min(index, 6) * 0.025,
                  ease: [0.22, 0.61, 0.36, 1],
                }}
              >
                <button
                  type="button"
                  onClick={() => onSelect(assignment.detection_id)}
                  aria-current={isSelected ? "true" : undefined}
                  className={cn(
                    "glass glass-edge w-full cursor-pointer rounded-xl border px-3.5 py-3.5 text-left",
                    "transition-colors duration-150",
                    isSelected
                      ? "border-primary/60 accent-glow"
                      : "border-transparent hover:border-border hover:bg-accent/50",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cn(
                        "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg text-xs font-semibold",
                        "accent-tile accent-glow text-white",
                      )}
                    >
                      {assignment.rank}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate font-mono text-xs text-muted-foreground">
                          {assignment.detection_id}
                        </p>
                        <span className="tabular shrink-0 text-sm font-semibold">
                          {assignment.score.toFixed(3)}
                        </span>
                      </div>

                      <p className="mt-1.5 text-sm leading-relaxed text-foreground">
                        {assignment.rationale}
                      </p>

                      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                        <Badge variant="outline">
                          <Anchor className="size-3" />
                          {assignment.vessel_id}
                        </Badge>
                        <Badge
                          variant="outline"
                          title={
                            assignment.rationale_source === "llm"
                              ? "Rationale written by Claude from the agents' evidence"
                              : "Rationale from the deterministic offline template"
                          }
                        >
                          {assignment.rationale_source === "llm" ? (
                            <Bot className="size-3" />
                          ) : (
                            <FileText className="size-3" />
                          )}
                          {assignment.rationale_source === "llm" ? "Claude" : "Template"}
                        </Badge>
                        {score &&
                          Object.entries(score.components)
                            .sort((a, b) => b[1] - a[1])
                            .slice(0, 2)
                            .map(([key, value]) => (
                              <Badge key={key} variant="secondary">
                                {humanise(key)} {value.toFixed(2)}
                              </Badge>
                            ))}
                      </div>
                    </div>
                  </div>
                </button>
              </motion.li>
            );
          })}
          </AnimatePresence>
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
