import { AlertTriangle, RefreshCw } from "lucide-react";
import * as React from "react";

/**
 * The map is a third-party widget drawing on a canvas we do not control. If it
 * throws, the failure stays inside this box: the queue, plan, evidence and
 * approval keep working, and the operator can redraw the map in place.
 */
export class MapErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null; attempt: number }
> {
  state = { error: null as Error | null, attempt: 0 };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error("Map failed and was contained:", error);
  }

  render() {
    if (!this.state.error) {
      return <React.Fragment key={this.state.attempt}>{this.props.children}</React.Fragment>;
    }
    return (
      <div className="flex size-full flex-col items-center justify-center gap-3 p-6 text-center">
        <AlertTriangle className="size-7 text-warning" aria-hidden="true" />
        <p className="text-sm font-medium">The map could not be drawn.</p>
        <p className="max-w-sm text-xs text-muted-foreground">
          Detections, the plan, evidence and approval still work from the panels.
        </p>
        <button
          type="button"
          className="mt-1 inline-flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent"
          onClick={() => this.setState(s => ({ error: null, attempt: s.attempt + 1 }))}
        >
          <RefreshCw className="size-3.5" aria-hidden="true" /> Redraw map
        </button>
      </div>
    );
  }
}
