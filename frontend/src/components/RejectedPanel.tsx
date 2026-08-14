import { Filter, ShieldCheck, XCircle } from "lucide-react";
import * as React from "react";
import type { RejectedResponse } from "@/lib/types";
import { cn, humanise } from "@/lib/utils";
import { Badge, Button, EmptyState, Skeleton } from "@/components/ui/primitives";

interface RejectedPanelProps {
  data: RejectedResponse | null;
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/**
 * Rejected detections, with the reason each was disqualified.
 *
 * PRD 8 makes this first-class rather than a filter tucked behind a menu: the
 * Verification Agent's entire measured contribution (precision 0.238 -> 0.623 on
 * MARIDA, eval/results.md) is what it throws away, so an interface that only
 * showed survivors would hide the best result in the project.
 */
export function RejectedPanel({ data, loading, selectedId, onSelect }: RejectedPanelProps) {
  const [checkFilter, setCheckFilter] = React.useState<string | null>(null);

  if (loading) {
    return (
      <div className="space-y-2 p-3">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    );
  }

  if (!data || data.count === 0) {
    return (
      <EmptyState icon={ShieldCheck} title="Nothing was rejected in this run">
        Every candidate the detector emitted survived all five false-positive
        checks. On real imagery that is unusual — on the MARIDA benchmark the
        agent rejects roughly three quarters of raw candidates.
      </EmptyState>
    );
  }

  const counts = new Map<string, number>();
  for (const entry of data.rejected) {
    for (const check of entry.failed_checks) {
      counts.set(check, (counts.get(check) ?? 0) + 1);
    }
  }

  const visible = checkFilter
    ? data.rejected.filter((entry) => entry.failed_checks.includes(checkFilter))
    : data.rejected;

  const rejectionRate = data.detections_total
    ? Math.round((data.count / data.detections_total) * 100)
    : 0;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-3 py-2.5">
        <p className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">
            {data.count} of {data.detections_total}
          </span>{" "}
          raw candidates disqualified ({rejectionRate}%). Each one is kept with its
          reason — nothing is discarded silently.
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <Filter className="size-3 text-muted-foreground" aria-hidden="true" />
          <Button
            size="sm"
            variant={checkFilter === null ? "secondary" : "ghost"}
            onClick={() => setCheckFilter(null)}
            className="h-6 px-2 text-[11px]"
          >
            All
          </Button>
          {[...counts.entries()]
            .sort((a, b) => b[1] - a[1])
            .map(([check, count]) => (
              <Button
                key={check}
                size="sm"
                variant={checkFilter === check ? "secondary" : "ghost"}
                onClick={() => setCheckFilter(checkFilter === check ? null : check)}
                className="h-6 px-2 text-[11px]"
                aria-pressed={checkFilter === check}
              >
                {humanise(check)} <span className="tabular ml-1 opacity-70">{count}</span>
              </Button>
            ))}
        </div>
      </div>

      <ul className="flex-1 divide-y divide-border overflow-y-auto">
        {visible.map((entry) => {
          const id = entry.verification.detection_id;
          const isSelected = id === selectedId;
          return (
            <li key={id}>
              <button
                type="button"
                onClick={() => onSelect(id)}
                aria-current={isSelected ? "true" : undefined}
                className={cn(
                  "w-full cursor-pointer px-3 py-3 text-left transition-colors duration-150 hover:bg-accent/60",
                  isSelected && "bg-accent",
                )}
              >
                <div className="flex items-start gap-2.5">
                  <XCircle className="mt-0.5 size-4 shrink-0 text-chart-rejected" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-muted-foreground">{id}</p>
                    <p className="mt-1 text-sm leading-snug">{entry.reasons[0]}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {entry.failed_checks.map((check) => (
                        <Badge key={check} variant="destructive">
                          {humanise(check)}
                        </Badge>
                      ))}
                      {entry.detection && (
                        <Badge variant="outline">
                          raw confidence {entry.detection.confidence.toFixed(2)}
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
