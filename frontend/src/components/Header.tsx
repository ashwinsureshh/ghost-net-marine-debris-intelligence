import { FlaskConical, WifiOff } from "lucide-react";
import type { AppMeta, RunSummary } from "@/lib/types";
import { formatDateShort } from "@/lib/utils";

interface HeaderProps {
  meta: AppMeta | null;
  runs: RunSummary[];
  activeRunId: string | null;
  onRunChange: (runId: string) => void;
  staticMode: boolean;
}

/**
 * The top bar: which run is on screen, and what to distrust about it.
 *
 * Identity and the theme control live on the sidebar rail now, so this carries
 * only run context. That is deliberate — the previous version put every
 * headline metric up here, and six competing figures in a 40px band is not a
 * hierarchy.
 *
 * The synthetic-run and offline indicators stay, and stay legible text rather
 * than icons. PRD §8 requires the prototype framing to survive contact with the
 * UI; an operator who cannot tell generated inputs from real ones at a glance is
 * exactly the failure that framing exists to prevent.
 */
export function Header({ meta, runs, activeRunId, onRunChange, staticMode }: HeaderProps) {
  const active = runs.find((r) => r.run_id === activeRunId);

  return (
    <header className="relative z-10 shrink-0 border-b border-border bg-card">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <label htmlFor="run-select" className="sr-only">
            Pipeline run
          </label>
          <select
            id="run-select"
            value={activeRunId ?? ""}
            onChange={(e) => onRunChange(e.target.value)}
            disabled={runs.length === 0}
            className="h-7 min-w-0 max-w-[22rem] flex-1 cursor-pointer truncate rounded-md border border-input bg-background px-2 text-xs disabled:cursor-not-allowed disabled:opacity-50"
          >
            {runs.length === 0 && <option value="">No runs available</option>}
            {runs.map((run) => (
              <option key={run.run_id} value={run.run_id}>
                {run.region_name ?? run.run_id}
                {run.generated_at ? ` — ${formatDateShort(run.generated_at)}` : ""}
              </option>
            ))}
          </select>

          {active?.inputs_are_synthetic && (
            <span
              className="flex shrink-0 items-center gap-1.5 text-[11px] text-warning"
              title="This run was computed from generated inputs"
            >
              <FlaskConical className="size-3" />
              Synthetic run
            </span>
          )}
          {staticMode && (
            <span
              className="flex shrink-0 items-center gap-1.5 text-[11px] text-muted-foreground"
              title="Offline static export — read only"
            >
              <WifiOff className="size-3" />
              Offline export
            </span>
          )}
        </div>

        {meta && (
          <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
            v{meta.version}
          </span>
        )}
      </div>

      {/* PRD §8: the prototype framing has to survive contact with the UI. */}
      <p className="border-t border-border bg-muted/45 px-4 py-1.5 text-[11px] leading-snug text-muted-foreground">
        <span className="font-medium text-foreground">Research prototype.</span>{" "}
        {meta?.prototype_notice ??
          "Decision-support only; every output stops at a recommendation for human review."}
      </p>
    </header>
  );
}
