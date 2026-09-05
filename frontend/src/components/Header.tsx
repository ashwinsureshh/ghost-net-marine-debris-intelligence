import { FlaskConical, Moon, Sun, WifiOff } from "lucide-react";
import type { AppMeta, RunSummary } from "@/lib/types";
import { formatDateShort } from "@/lib/utils";
import { Badge, Button } from "@/components/ui/primitives";

interface HeaderProps {
  meta: AppMeta | null;
  runs: RunSummary[];
  activeRunId: string | null;
  onRunChange: (runId: string) => void;
  isDark: boolean;
  onToggleTheme: () => void;
  staticMode: boolean;
}

export function Header({
  meta,
  runs,
  activeRunId,
  onRunChange,
  isDark,
  onToggleTheme,
  staticMode,
}: HeaderProps) {
  const active = runs.find((r) => r.run_id === activeRunId);

  return (
    <header className="elev-1 relative z-10 overflow-hidden border-b border-border bg-card">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5 px-5 py-3.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <div
            aria-hidden="true"
            className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15"
          >
            {/* Net-and-wave mark: drawn, not an emoji. */}
            <svg viewBox="0 0 24 24" className="size-5 text-primary" fill="none" strokeWidth="1.6">
              <path
                d="M2 17c2.2 0 2.2 2 4.4 2s2.2-2 4.4-2 2.2 2 4.4 2 2.2-2 4.4-2"
                stroke="currentColor"
                strokeLinecap="round"
              />
              <path
                d="M4 4l6 6m4 4l6 6M10 4l-6 6m16 4l-6 6"
                stroke="currentColor"
                strokeLinecap="round"
                opacity=".65"
              />
            </svg>
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold leading-tight">
              Ghost Net &amp; Marine Debris Intelligence
            </h1>
            <p className="truncate text-[11px] text-muted-foreground">Operator console</p>
          </div>
        </div>

        <div className="flex min-w-0 flex-1 basis-full items-center gap-2 sm:basis-auto">
          <label htmlFor="run-select" className="sr-only">
            Pipeline run
          </label>
          <select
            id="run-select"
            value={activeRunId ?? ""}
            onChange={(e) => onRunChange(e.target.value)}
            disabled={runs.length === 0}
            className="h-9 w-full min-w-0 flex-1 cursor-pointer truncate rounded-md border border-input bg-background px-2.5 text-xs disabled:cursor-not-allowed disabled:opacity-50 sm:max-w-xs"
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
            <Badge variant="warning" title="This run was computed from generated inputs">
              <FlaskConical className="size-3" />
              Synthetic run
            </Badge>
          )}
          {staticMode && (
            <Badge variant="outline" title="Offline static export — read only">
              <WifiOff className="size-3" />
              Offline export
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {meta && (
            <Badge variant="outline" className="hidden sm:inline-flex">
              v{meta.version}
            </Badge>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleTheme}
            aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
            title={isDark ? "Switch to light theme" : "Switch to dark theme"}
          >
            {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
        </div>
      </div>

      {/* PRD 8: the prototype framing has to survive contact with the UI. */}
      <p className="border-t border-border bg-muted/60 px-5 py-2.5 text-[11.5px] leading-relaxed text-muted-foreground">
        <span className="font-medium text-foreground">Research prototype.</span>{" "}
        {meta?.prototype_notice ??
          "Decision-support only; every output stops at a recommendation for human review."}
      </p>
    </header>
  );
}
