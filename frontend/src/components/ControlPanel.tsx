import { FlaskConical, Ship } from "lucide-react";
import type { AgentMeta } from "@/lib/types";
import { Label, Switch } from "@/components/ui/primitives";

interface ControlPanelProps {
  capacity: number;
  onCapacityChange: (value: number) => void;
  horizonDays: number;
  onHorizonChange: (value: number) => void;
  agents: AgentMeta[];
  ablatable: string[];
  ablated: Set<string>;
  onToggleAgent: (id: string, active: boolean) => void;
  disabled: boolean;
}

/**
 * The operator's two levers, and the evaluator's one.
 *
 * Capacity and horizon are FR-6.2's constraint made adjustable; the agent
 * toggles are PRD 12's ablation study made interactive. Both re-plan on the
 * server, which is what keeps the deployment doing real work rather than
 * serving a frozen page.
 */
export function ControlPanel({
  capacity,
  onCapacityChange,
  horizonDays,
  onHorizonChange,
  agents,
  ablatable,
  ablated,
  onToggleAgent,
  disabled,
}: ControlPanelProps) {
  return (
    <div className="space-y-4 p-3">
      <section>
        <div className="mb-2 flex items-center gap-1.5">
          <Ship className="size-3.5 text-muted-foreground" />
          <h3 className="text-xs font-semibold uppercase tracking-wide">Dispatch constraint</h3>
        </div>

        <div className="space-y-3">
          <div>
            <div className="flex items-center justify-between">
              <Label htmlFor="capacity">Cleanup vessels available</Label>
              <span className="tabular text-sm font-semibold">{capacity}</span>
            </div>
            <input
              id="capacity"
              type="range"
              min={0}
              max={10}
              step={1}
              value={capacity}
              disabled={disabled}
              onChange={(e) => onCapacityChange(Number(e.target.value))}
              className="mt-1.5 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary disabled:cursor-not-allowed disabled:opacity-50"
              aria-describedby="capacity-help"
            />
            <p id="capacity-help" className="mt-1 text-[11px] text-muted-foreground">
              FR-6.2 bounds the plan by the fleet you actually have. Sites beyond
              it are deferred, not dropped.
            </p>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <Label htmlFor="horizon">Planning horizon</Label>
              <span className="tabular text-sm font-semibold">{horizonDays} d</span>
            </div>
            <input
              id="horizon"
              type="range"
              min={1}
              max={21}
              step={1}
              value={horizonDays}
              disabled={disabled}
              onChange={(e) => onHorizonChange(Number(e.target.value))}
              className="mt-1.5 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
        </div>
      </section>

      <section>
        <div className="mb-1 flex items-center gap-1.5">
          <FlaskConical className="size-3.5 text-muted-foreground" />
          <h3 className="text-xs font-semibold uppercase tracking-wide">Ablation study</h3>
        </div>
        <p className="mb-2.5 text-[11px] leading-snug text-muted-foreground">
          Switch an agent off and re-plan. PRD §12 asks whether removing any one
          agent breaks the system rather than merely degrading it — each toggle
          reports the specific capability that goes missing.
        </p>

        <ul className="space-y-2">
          {agents.map((agent) => {
            const canAblate = ablatable.includes(agent.id);
            const active = !ablated.has(agent.id);
            return (
              <li key={agent.id} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <Label
                    htmlFor={`agent-${agent.id}`}
                    className="block cursor-pointer text-xs font-medium text-foreground"
                  >
                    {agent.name}
                  </Label>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {agent.fr}
                    {!canAblate && " · always on"}
                  </span>
                </div>
                <Switch
                  id={`agent-${agent.id}`}
                  checked={active}
                  disabled={!canAblate || disabled}
                  onCheckedChange={(next) => onToggleAgent(agent.id, next)}
                />
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
          Detection stays on: with it off there is no run to serve at all. That
          arm is covered by the offline study in{" "}
          <span className="font-mono">eval/results.md</span>.
        </p>
      </section>
    </div>
  );
}
