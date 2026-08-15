import { AlertTriangle, Ban, Info, ListChecks, RefreshCw, SlidersHorizontal, XCircle } from "lucide-react";
import * as React from "react";
import { ControlPanel } from "@/components/ControlPanel";
import { DispatchPanel } from "@/components/DispatchPanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { Header } from "@/components/Header";
import { MapView } from "@/components/MapView";
import { MetricsStrip } from "@/components/MetricsStrip";
import { RejectedPanel } from "@/components/RejectedPanel";
import {
  Badge,
  Button,
  EmptyState,
  Input,
  Label,
  Modal,
  Skeleton,
} from "@/components/ui/primitives";
import { ApiError, api, isStaticMode } from "@/lib/api";
import type {
  AppMeta,
  BenchmarkReport,
  PlanResponse,
  RejectedResponse,
  RunArtefact,
  RunSummary,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type LeftTab = "dispatch" | "rejected" | "controls";

const THEME_KEY = "ghostnet-theme";

export default function App() {
  const [meta, setMeta] = React.useState<AppMeta | null>(null);
  const [benchmark, setBenchmark] = React.useState<BenchmarkReport | null>(null);
  const [runs, setRuns] = React.useState<RunSummary[]>([]);
  const [runId, setRunId] = React.useState<string | null>(null);
  const [artefact, setArtefact] = React.useState<RunArtefact | null>(null);
  const [plan, setPlan] = React.useState<PlanResponse | null>(null);
  const [rejected, setRejected] = React.useState<RejectedResponse | null>(null);

  const [bootError, setBootError] = React.useState<string | null>(null);
  const [runError, setRunError] = React.useState<string | null>(null);
  const [planError, setPlanError] = React.useState<string | null>(null);
  const [booting, setBooting] = React.useState(true);
  const [loadingRun, setLoadingRun] = React.useState(false);
  const [planning, setPlanning] = React.useState(false);

  const [capacity, setCapacity] = React.useState(3);
  const [horizonDays, setHorizonDays] = React.useState(7);
  const [ablated, setAblated] = React.useState<Set<string>>(new Set());
  const [tab, setTab] = React.useState<LeftTab>("dispatch");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [showRejectedOnMap, setShowRejectedOnMap] = React.useState(true);

  const [approveOpen, setApproveOpen] = React.useState(false);
  const [reviewer, setReviewer] = React.useState("");
  const [approveNote, setApproveNote] = React.useState("");
  const [approving, setApproving] = React.useState(false);
  const [approvedBy, setApprovedBy] = React.useState<string | null>(null);
  const [approveError, setApproveError] = React.useState<string | null>(null);
  const [approveWarning, setApproveWarning] = React.useState<string | null>(null);

  const [isDark, setIsDark] = React.useState(
    () => typeof document !== "undefined" && document.documentElement.classList.contains("dark"),
  );

  const staticMode = isStaticMode();

  // -- boot ---------------------------------------------------------------
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [metaResponse, runsResponse, benchmarkResponse] = await Promise.all([
          api.meta(),
          api.runs(),
          // Measured quality is context, not a precondition. If this server
          // cannot produce it the console still runs the pipeline's output;
          // the strip says the numbers are unavailable rather than vanishing.
          api.benchmark().catch(() => null),
        ]);
        if (cancelled) return;
        setMeta(metaResponse);
        setBenchmark(benchmarkResponse);
        setRuns(runsResponse);
        const first = runsResponse.find((r) => !r.unreadable);
        setRunId(first?.run_id ?? null);
        if (!first) {
          setBootError(
            "No run artefacts are available. Export one with `python scripts/export_run.py --synthetic`.",
          );
        }
      } catch (error) {
        if (!cancelled) {
          setBootError(error instanceof ApiError ? error.message : String(error));
        }
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // -- load the selected run ---------------------------------------------
  React.useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    setLoadingRun(true);
    setRunError(null);
    setSelectedId(null);
    setApprovedBy(null);
    (async () => {
      try {
        const [artefactResponse, rejectedResponse] = await Promise.all([
          api.run(runId),
          api.rejected(runId),
        ]);
        if (cancelled) return;
        setArtefact(artefactResponse);
        setRejected(rejectedResponse);
      } catch (error) {
        if (!cancelled) setRunError(error instanceof ApiError ? error.message : String(error));
      } finally {
        if (!cancelled) setLoadingRun(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  // -- re-plan whenever the operator changes a control --------------------
  React.useEffect(() => {
    if (!runId || !artefact) return;
    let cancelled = false;
    setPlanning(true);
    setPlanError(null);
    const timer = setTimeout(async () => {
      try {
        const response = await api.plan(runId, {
          vessel_capacity: capacity,
          planning_horizon_days: horizonDays,
          ablate: [...ablated],
        });
        if (!cancelled) {
          setPlan(response);
          setApprovedBy(null); // a changed plan is a new plan; re-approval required
        }
      } catch (error) {
        if (!cancelled) setPlanError(error instanceof ApiError ? error.message : String(error));
      } finally {
        if (!cancelled) setPlanning(false);
      }
    }, 180); // debounce the sliders
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [runId, artefact, capacity, horizonDays, ablated]);

  const toggleTheme = () => {
    const next = !isDark;
    setIsDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem(THEME_KEY, next ? "dark" : "light");
    } catch {
      /* storage blocked — the toggle still works for this session */
    }
  };

  const toggleAgent = (id: string, active: boolean) => {
    setAblated((current) => {
      const next = new Set(current);
      if (active) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const submitApproval = async () => {
    if (!runId || !plan?.plan) return;
    setApproving(true);
    setApproveError(null);
    try {
      const response = await api.approve(runId, {
        reviewer,
        vessel_capacity: capacity,
        ablate: [...ablated],
        detection_ids: plan.plan.assignments.map((a) => a.detection_id),
        note: approveNote,
      });
      setApprovedBy(response.approval.reviewer);
      setApproveWarning(response.warning);
      setApproveOpen(false);
      setApproveNote("");
    } catch (error) {
      setApproveError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setApproving(false);
    }
  };

  const selectedScore = plan?.scores.find((s) => s.detection_id === selectedId);
  const prioritisationAblated = ablated.has("prioritisation");

  if (booting) {
    return (
      <div className="flex min-h-dvh flex-col">
        <div className="h-[70px] border-b border-border bg-card" />
        <div className="grid flex-1 gap-3 p-3 lg:grid-cols-[minmax(0,22rem)_1fr_minmax(0,20rem)]">
          <Skeleton className="h-full min-h-64" />
          <Skeleton className="h-full min-h-64" />
          <Skeleton className="hidden h-full min-h-64 lg:block" />
        </div>
      </div>
    );
  }

  if (bootError) {
    return (
      <div className="flex min-h-dvh items-center justify-center p-6">
        <div className="max-w-md rounded-lg border border-border bg-card p-6">
          <EmptyState icon={AlertTriangle} title="Cannot start the console">
            <p className="mb-3">{bootError}</p>
            <p className="text-[11px]">
              The console reads precomputed run artefacts. The workstation exports
              them with <span className="font-mono">scripts/export_run.py</span>; a
              synthetic demo run can be generated on any machine.
            </p>
          </EmptyState>
          <Button className="w-full" onClick={() => window.location.reload()}>
            <RefreshCw className="size-4" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[2100] focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <Header
        meta={meta}
        runs={runs}
        activeRunId={runId}
        onRunChange={setRunId}
        isDark={isDark}
        onToggleTheme={toggleTheme}
        staticMode={staticMode}
      />

      {/* The two numbers eval/results.md says must always be quoted together:
          the Verification Agent's precision gain and the detector's region
          recall. Above the fold, before any plan is read. */}
      <MetricsStrip
        benchmark={benchmark}
        artefact={artefact}
        summary={runs.find((r) => r.run_id === runId)}
        loading={loadingRun && !artefact}
      />

      {/* Single scrolling column on small screens; three fixed panes from lg
          up. The explicit min-heights matter on mobile: without them the
          flex-1 lists inside an auto-sized grid row collapse to nothing. */}
      <main
        id="main"
        className="grid min-h-0 flex-1 gap-px overflow-y-auto bg-border lg:grid-cols-[minmax(0,23rem)_minmax(0,1fr)_minmax(0,21rem)] lg:overflow-hidden"
      >
        {/* ---------------------------------------------- left column -- */}
        <section
          aria-label="Dispatch plan, rejected detections and controls"
          className="flex min-h-[28rem] flex-col bg-background lg:min-h-0 lg:overflow-hidden"
        >
          <div role="tablist" aria-label="Panel" className="flex shrink-0 border-b border-border">
            {(
              [
                ["dispatch", ListChecks, "Dispatch", plan?.plan?.assignments.length],
                ["rejected", XCircle, "Rejected", rejected?.count],
                ["controls", SlidersHorizontal, "Controls", undefined],
              ] as const
            ).map(([id, Icon, label, count]) => (
              <button
                key={id}
                role="tab"
                id={`tab-${id}`}
                aria-selected={tab === id}
                aria-controls={`panel-${id}`}
                onClick={() => setTab(id)}
                className={cn(
                  "flex flex-1 cursor-pointer items-center justify-center gap-1.5 border-b-2 px-2 py-2.5 text-xs font-medium transition-colors duration-150",
                  tab === id
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
              >
                <Icon className="size-3.5" />
                {label}
                {count !== undefined && count > 0 && (
                  <Badge variant={id === "rejected" ? "destructive" : "secondary"}>{count}</Badge>
                )}
              </button>
            ))}
          </div>

          <div
            role="tabpanel"
            id={`panel-${tab}`}
            aria-labelledby={`tab-${tab}`}
            className="min-h-0 flex-1 lg:overflow-hidden"
          >
            {planError && tab === "dispatch" && (
              <div className="m-3 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs">
                <AlertTriangle className="size-4 shrink-0 text-destructive" />
                <div>
                  <p className="font-medium">Could not recompute the plan</p>
                  <p className="mt-0.5 text-muted-foreground">{planError}</p>
                </div>
              </div>
            )}

            {tab === "dispatch" && (
              <DispatchPanel
                plan={plan?.plan ?? null}
                scores={plan?.scores ?? []}
                loading={planning && !plan}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onApprove={() => setApproveOpen(true)}
                approved={Boolean(approvedBy)}
                approvedBy={approvedBy}
                prioritisationAblated={prioritisationAblated}
              />
            )}
            {tab === "rejected" && (
              <RejectedPanel
                data={rejected}
                loading={loadingRun}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            )}
            {tab === "controls" && meta && (
              <ControlPanel
                capacity={capacity}
                onCapacityChange={setCapacity}
                horizonDays={horizonDays}
                onHorizonChange={setHorizonDays}
                agents={meta.agents}
                ablatable={meta.ablatable_agents}
                ablated={ablated}
                onToggleAgent={toggleAgent}
                disabled={staticMode}
              />
            )}
          </div>
        </section>

        {/* ------------------------------------------------ map column -- */}
        <section
          aria-label="Map"
          className="relative min-h-[22rem] bg-surface-map lg:min-h-0"
        >
          {loadingRun && (
            <div className="absolute inset-0 z-[600] flex items-center justify-center bg-background/60 backdrop-blur-sm">
              <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs">
                <RefreshCw className="size-3.5 animate-spin text-primary" />
                Loading run…
              </div>
            </div>
          )}
          {runError ? (
            <EmptyState icon={AlertTriangle} title="Could not load this run">
              {runError}
            </EmptyState>
          ) : artefact ? (
            <MapView
              artefact={artefact}
              plan={plan?.plan ?? null}
              selectedId={selectedId}
              onSelect={setSelectedId}
              showRejected={showRejectedOnMap}
              isDark={isDark}
            />
          ) : null}

          {artefact && (
            <div className="absolute left-3 top-3 z-[500] flex flex-wrap items-center gap-1.5">
              <Button
                size="sm"
                variant={showRejectedOnMap ? "secondary" : "outline"}
                onClick={() => setShowRejectedOnMap((v) => !v)}
                aria-pressed={showRejectedOnMap}
                className="bg-card/95 backdrop-blur"
              >
                {showRejectedOnMap ? <XCircle className="size-3.5" /> : <Ban className="size-3.5" />}
                {showRejectedOnMap ? "Rejected shown" : "Rejected hidden"}
              </Button>
              {planning && (
                <Badge variant="outline" className="bg-card/95 backdrop-blur">
                  <RefreshCw className="size-3 animate-spin" />
                  Re-planning
                </Badge>
              )}
            </div>
          )}
        </section>

        {/* -------------------------------------------- evidence column -- */}
        <section
          aria-label="Evidence trail"
          className="flex min-h-[20rem] flex-col bg-background lg:min-h-0 lg:overflow-hidden"
        >
          {artefact && (
            <EvidencePanel
              artefact={artefact}
              detectionId={selectedId}
              score={selectedScore}
              onClose={() => setSelectedId(null)}
            />
          )}
        </section>
      </main>

      {/* ------------------------------------------------- status strip -- */}
      {(plan?.degradations.length || artefact?.provenance.notes.length || approveWarning) && (
        <footer className="shrink-0 border-t border-border bg-card px-4 py-1.5">
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center gap-2 text-[11px] text-muted-foreground">
              <Info className="size-3.5 shrink-0" />
              <span>
                {(plan?.degradations.length ?? 0) + (artefact?.provenance.notes.length ?? 0)} caveat(s)
                on this run
              </span>
              <span className="ml-auto opacity-60 group-open:hidden">show</span>
              <span className="ml-auto hidden opacity-60 group-open:inline">hide</span>
            </summary>
            <ul className="mt-1.5 space-y-1 pb-1 text-[11px] leading-snug text-muted-foreground">
              {approveWarning && <li className="text-warning">{approveWarning}</li>}
              {artefact?.provenance.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
              {plan?.degradations.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </details>
        </footer>
      )}

      {/* ---------------------------------------------- approval modal -- */}
      <Modal
        open={approveOpen}
        onClose={() => setApproveOpen(false)}
        title="Approve dispatch plan"
        description="FR-6.4 — no plan is treated as final without an explicit, named human review."
      >
        <div className="space-y-3">
          <div>
            <Label htmlFor="reviewer">Reviewer name</Label>
            <Input
              id="reviewer"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
              placeholder="e.g. A. Coordinator"
              className="mt-1"
              autoComplete="name"
            />
          </div>
          <div>
            <Label htmlFor="approve-note">Note (optional)</Label>
            <Input
              id="approve-note"
              value={approveNote}
              onChange={(e) => setApproveNote(e.target.value)}
              placeholder="Anything the record should carry"
              className="mt-1"
            />
          </div>

          <p className="rounded-md border border-border bg-muted/40 px-2.5 py-2 text-[11px] leading-snug text-muted-foreground">
            Approving records that you reviewed{" "}
            <span className="font-medium text-foreground">
              {plan?.plan?.assignments.length ?? 0} site(s)
            </span>{" "}
            under a {capacity}-vessel constraint
            {ablated.size > 0 && ` with ${[...ablated].join(", ")} switched off`}. It does
            not dispatch anything — this is a research prototype.
          </p>

          {approveError && (
            <p className="rounded-md border border-destructive/30 bg-destructive/10 px-2.5 py-2 text-xs text-destructive">
              {approveError}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setApproveOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="warning"
              onClick={submitApproval}
              disabled={approving || reviewer.trim().length === 0}
            >
              {approving ? <RefreshCw className="size-4 animate-spin" /> : null}
              {approving ? "Recording…" : "Record approval"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
