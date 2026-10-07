import { AlertTriangle, Info, RefreshCw, Compass, FlaskConical, Ship, Moon, Sun, Waves, PanelLeftClose, PanelLeftOpen, Map as MapIcon, Server, Search } from "lucide-react";
import * as React from "react";
import { AgentPipeline } from "@/components/AgentPipeline";
import { CommandPalette } from "@/components/CommandPalette";
import { RegionsView } from "@/components/RegionsView";
import { SystemView } from "@/components/SystemView";
import { useToast } from "@/components/Toasts";
import { buildSearchIndex, type SearchItem } from "@/lib/search";
import { ControlPanel } from "@/components/ControlPanel";
import { DispatchPanel } from "@/components/DispatchPanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { Header } from "@/components/Header";
import { AtlasQueue } from "@/components/AtlasQueue";
import { MapView } from "@/components/MapView";
import { MapErrorBoundary } from "@/components/MapErrorBoundary";
import { MetricsStrip } from "@/components/MetricsStrip";
import { RejectedPanel } from "@/components/RejectedPanel";
import {
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
  RobustnessReport,
  RunArtefact,
  RunSummary,
} from "@/lib/types";
import { PlanRobustness } from "@/components/PlanRobustness";
import { cn, formatDateShort } from "@/lib/utils";
import { coverageFromSummaries } from "@/lib/coverage";

type LeftTab = "explore" | "regions" | "dispatch" | "controls" | "system";

const NAV = [
  { id: "explore", label: "Atlas", icon: Compass },
  { id: "regions", label: "Regions", icon: MapIcon },
  { id: "dispatch", label: "Plan", icon: Ship },
  { id: "controls", label: "Research", icon: FlaskConical },
  { id: "system", label: "System", icon: Server },
] as const;

const THEME_KEY = "ghostnet-theme";

export default function App() {
  const [meta, setMeta] = React.useState<AppMeta | null>(null);
  const [benchmark, setBenchmark] = React.useState<BenchmarkReport | null>(null);
  const [runs, setRuns] = React.useState<RunSummary[]>([]);
  const { coverage, failed: coverageFailed } = React.useMemo(() => coverageFromSummaries(runs), [runs]);
  const coverageLoading = false;
  const [overview, setOverview] = React.useState(false);
  const [runId, setRunId] = React.useState<string | null>(null);
  const [artefact, setArtefact] = React.useState<RunArtefact | null>(null);
  const [plan, setPlan] = React.useState<PlanResponse | null>(null);
  const [rejected, setRejected] = React.useState<RejectedResponse | null>(null);
  const [robustness, setRobustness] = React.useState<RobustnessReport | null>(null);

  const [bootError, setBootError] = React.useState<string | null>(null);
  const [runError, setRunError] = React.useState<string | null>(null);
  const [planError, setPlanError] = React.useState<string | null>(null);
  const [booting, setBooting] = React.useState(true);
  const [loadingRun, setLoadingRun] = React.useState(false);
  const [planning, setPlanning] = React.useState(false);

  const [capacity, setCapacity] = React.useState(3);
  const [horizonDays, setHorizonDays] = React.useState(7);
  const [ablated, setAblated] = React.useState<Set<string>>(new Set());
  const [tab, setTab] = React.useState<LeftTab>("explore");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [showRejectedOnMap, setShowRejectedOnMap] = React.useState(true);

  const [approveOpen, setApproveOpen] = React.useState(false);
  const [reviewer, setReviewer] = React.useState("");
  const [approveNote, setApproveNote] = React.useState("");
  const [approving, setApproving] = React.useState(false);
  const [approvedBy, setApprovedBy] = React.useState<string | null>(null);
  const [approveError, setApproveError] = React.useState<string | null>(null);
  const [approveWarning, setApproveWarning] = React.useState<string | null>(null);

  // Sidebar collapse and the diagnostics drawer. Both live here because the
  // shell's grid template depends on them.
  const [navCollapsed, setNavCollapsed] = React.useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 760px)").matches,
  );
  const [diagnosticsOpen, setDiagnosticsOpen] = React.useState(false);

  const [isDark, setIsDark] = React.useState(
    () => typeof document !== "undefined" && document.documentElement.classList.contains("dark"),
  );

  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [mapFocus, setMapFocus] = React.useState<{ lat: number; lon: number; key: number } | null>(null);
  const toast = useToast();
  // Set by the operator's own controls, so "Plan recomputed" is announced for
  // changes they made and never for the plan that arrives with a region.
  const operatorChangedPlan = React.useRef(false);
  const announcedRun = React.useRef<string | null>(null);

  const staticMode = isStaticMode();
  const pageOpen = tab === "regions" || tab === "system";
  const openRun = React.useCallback((id: string) => {
    setRunId(id); setOverview(false); setSelectedId(null);
    setTab(current => current === "regions" || current === "system" ? "explore" : current);
  }, []);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (approveOpen) return; // never stack the palette over the approval dialog
        setPaletteOpen(open => !open);
        return;
      }
      if (event.key === "Escape" && !approveOpen && !paletteOpen) setSelectedId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [approveOpen, paletteOpen]);

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
        // Prefer a REAL run over the synthetic demo. Until now this worked only
        // by alphabetical luck — the store sorts run ids, and "gulf_of_honduras"
        // happens to precede "synthetic-coastal-demo". A region sorting after
        // "s" would have silently opened the console on generated data, which is
        // the one thing the run picker must not do by default now that a real
        // artefact exists.
        const readable = runsResponse.filter((r) => !r.unreadable);
        const first = readable.find((r) => !r.inputs_are_synthetic) ?? readable[0];
        setRunId(first?.run_id ?? null);
        announcedRun.current = first?.run_id ?? null; // the opening region is not news
        if (isStaticMode()) toast("Offline mode active: read-only copy, approvals need the live server.", "info");
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
        if (announcedRun.current !== runId) {
          announcedRun.current = runId;
          toast(`Region loaded: ${artefactResponse.region.name.split(" — ")[0]}`, "success");
        }
        if (artefactResponse.degradations.some(d => d.startsWith("vessels:"))) {
          toast("GFW data unavailable for this region: vessel context is unknown, not zero.", "warning");
        }
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

  // Separate from the run load: this panel is context, and its failure must
  // never block the run itself.
  React.useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    setRobustness(null);
    api.robustness(runId).then(r => { if (!cancelled) setRobustness(r); }).catch(() => {});
    return () => { cancelled = true; };
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
          if (operatorChangedPlan.current) {
            operatorChangedPlan.current = false;
            toast(response.plan ? `Plan recomputed: ${response.plan.assignments.length} site(s) from ${response.considered} considered` : "Plan recomputed: no ranked plan with prioritisation off", "info");
          }
        }
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof ApiError ? error.message : String(error);
          setPlanError(message);
          toast(`Re-planning failed: ${message}`, "error");
        }
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

  const changeCapacity = (value: number) => { operatorChangedPlan.current = true; setCapacity(value); };
  const changeHorizon = (value: number) => { operatorChangedPlan.current = true; setHorizonDays(value); };

  const toggleAgent = (id: string, active: boolean) => {
    operatorChangedPlan.current = true;
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
      toast(`Approval recorded for ${response.approval.reviewer}`, "success");
      if (response.warning) toast(response.warning, "warning");
      setApproveOpen(false);
      setApproveNote("");
    } catch (error) {
      setApproveError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setApproving(false);
    }
  };

  const selectedScore = plan?.scores.find((s) => s.detection_id === selectedId);
  const selectedRank = plan?.plan?.assignments.find(a => a.detection_id === selectedId)?.rank;
  const prioritisationAblated = ablated.has("prioritisation");

  const searchIndex = React.useMemo(() => buildSearchIndex({
    runs, artefact, views: NAV.map(n => ({ id: n.id, label: n.label })),
  }), [runs, artefact]);
  const onPick = (item: SearchItem) => {
    if (item.kind === "view") { setTab(item.id as LeftTab); setOverview(false); return; }
    if (item.kind === "region" && item.runId) { openRun(item.runId); setTab("explore"); return; }
    setTab(current => current === "regions" || current === "system" ? "explore" : current);
    setOverview(false);
    // Protected areas carry a position but no detection: move the map to them.
    if (!item.detectionId && item.lat !== undefined && item.lon !== undefined) {
      setMapFocus({ lat: item.lat, lon: item.lon, key: Date.now() });
    }
    if (item.detectionId) {
      // A rejected detection is hidden while "Verified only" is on; show it.
      const isRejected = artefact?.verifications.some(v => v.detection_id === item.detectionId && !v.verified);
      if (isRejected) setShowRejectedOnMap(true);
      setSelectedId(item.detectionId);
    }
  };

  // What the system is doing right now. Only real, in-flight work appears.
  const activity = loadingRun ? "Loading region" : planning && !staticMode ? "Re-planning" : null;

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
    <div className="flex h-dvh overflow-hidden">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[2100] focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <nav className="atlas-rail" aria-label="Workspace navigation">
        <a className="atlas-mark" href="#main" aria-label="GhostNet home"><Waves size={26} /></a>
        <span className="atlas-rail-rule" />
        {NAV.map(item => (
          <button key={item.id} data-nav={item.id} onClick={() => { setTab(item.id); setNavCollapsed(false); setOverview(false); }}
            aria-current={tab === item.id ? "page" : undefined} title={item.label}>
            <item.icon size={21} strokeWidth={1.5} /><span>{item.label}</span>
          </button>
        ))}
        <button className="atlas-search-button" onClick={() => setPaletteOpen(true)} aria-label="Search (Ctrl or Cmd plus K)" title="Search · Ctrl/⌘ K">
          <Search size={19} strokeWidth={1.5} /><span>Search</span>
        </button>
        <button className="atlas-theme" onClick={toggleTheme} aria-label={isDark ? "Use light theme" : "Use dark theme"}>
          {isDark ? <Sun size={20} /> : <Moon size={20} />}<span>Theme</span>
        </button>
        <span className="atlas-rail-end">GN / 01</span>
      </nav>
      <div className="atlas-body">
        <Header meta={meta} runs={runs} activeRunId={runId} onRunChange={openRun} staticMode={staticMode} />
        <div className="atlas-context">
          <div><span className="atlas-context-dot" /> {overview ? "Coverage atlas" : artefact?.provenance.inputs_are_synthetic ? "Synthetic observations" : "Historical observations"}
            {overview ? <span className="atlas-window">Historical windows vary by region</span> : artefact?.region.window_start && <span className="atlas-window">{formatDateShort(artefact.region.window_start)} — {artefact.region.window_end ? formatDateShort(artefact.region.window_end) : "open"}</span>}</div>
          <div className="atlas-context-actions">
            <span className="gn-activity-slot" role="status">
              {activity && <span key={activity} className="gn-activity gn-fade">
                <span className="gn-activity-dot" aria-hidden="true" />{activity}
              </span>}
            </span>
            <button onClick={() => { setOverview(false); setDiagnosticsOpen(v => !v); }} aria-expanded={diagnosticsOpen}>
              <FlaskConical size={14} /> {diagnosticsOpen ? "Close diagnostics" : "Run diagnostics"}
            </button>
          </div>
        </div>
        {/* Run diagnostics. Collapsed by default so it does not compete with
            the map, but the verification gain and the detector's region recall
            are rendered together whenever it is open — eval/results.md
            requires that pair and the endpoint is tested to refuse one without
            the other. */}
        {diagnosticsOpen && !overview && <div className="atlas-diagnostics">
          <MetricsStrip
            benchmark={benchmark}
            artefact={artefact}
            summary={runs.find((r) => r.run_id === runId)}
            loading={loadingRun && !artefact}
          />
        </div>}

        <main id="main" className={cn("atlas-workspace", (navCollapsed || overview) && "queue-collapsed", selectedId && "has-selection")}>
          {/* Regions and System cover the workspace; inert keeps what is underneath
              out of the Tab order and the accessibility tree while they are open. */}
          <aside className="atlas-queue" aria-label="Investigation queue" inert={pageOpen || undefined}>
            <div key={tab === "regions" || tab === "system" ? "explore" : tab} className="atlas-queue-inner gn-enter">
            <div className="atlas-queue-heading">
              <div className="atlas-eyebrow">{tab === "dispatch" ? "Human decisions" : tab === "controls" ? "Methods & controls" : "The field atlas"}</div>
              <h1>{tab === "dispatch" ? <>From insight<br /><em>to action.</em></> : tab === "controls" ? <>Look beneath<br /><em>the surface.</em></> : <>An ocean of<br /><em>evidence.</em></>}</h1>
              <p>{tab === "dispatch" ? "A ranked shortlist. Every decision stays with you." : tab === "controls" ? "Inspect the methods. Test each agent’s contribution." : "Trace what was found. Understand what it means."}</p>
            </div>
            {planError && <p role="alert" className="px-5 py-3 text-xs text-destructive">{planError}</p>}
            {(tab === "explore" || tab === "regions" || tab === "system") && (artefact
              ? <AtlasQueue key={runId} artefact={artefact} scores={plan?.scores ?? []} selectedId={selectedId} onSelect={setSelectedId} />
              : <QueueSkeleton />)}
            {tab === "dispatch" && meta && <details className="atlas-plan-settings"><summary>Plan settings · {capacity} vessels / {horizonDays} days</summary>
              <ControlPanel mode="dispatch" capacity={capacity} onCapacityChange={changeCapacity} horizonDays={horizonDays}
                onHorizonChange={changeHorizon} agents={meta.agents} ablatable={meta.ablatable_agents}
                ablated={ablated} onToggleAgent={toggleAgent} disabled={staticMode} />
            </details>}
            {tab === "dispatch" && <DispatchPanel plan={plan?.plan ?? null} scores={plan?.scores ?? []}
              loading={planning && !plan} selectedId={selectedId} onSelect={setSelectedId}
              onApprove={() => setApproveOpen(true)} approved={Boolean(approvedBy)} approvedBy={approvedBy}
              prioritisationAblated={prioritisationAblated} />}
            {tab === "dispatch" && <PlanRobustness report={robustness} capacity={capacity} horizonDays={horizonDays} />}
            {tab === "controls" && <div className="atlas-research-scroll">
              {meta && artefact && <AgentPipeline agents={meta.agents} artefact={artefact} plan={plan} ablated={ablated}
                ablatable={meta.ablatable_agents} onToggleAgent={toggleAgent} disabled={staticMode} />}
              {staticMode && <p className="px-5 pb-3 text-[11px] text-muted-foreground">Ablation re-scores on the server, so it is unavailable in the offline copy.</p>}
              <details className="atlas-rejection-audit" open><summary>False-positive explorer · {rejected?.count ?? 0} rejected</summary>
                <RejectedPanel data={rejected} loading={loadingRun} selectedId={selectedId} onSelect={setSelectedId} />
              </details>
            </div>}
            </div>
          </aside>
        {/* ------------------------------------------------ map column -- */}
        <section
          aria-label="Map"
          className="atlas-map"
          inert={pageOpen || undefined}
        >
          {loadingRun && (
              <div className="gn-map-loading gn-fade">
                {!artefact && <div className="gn-map-skeleton" aria-hidden="true" />}
                <div className="gn-map-loading-card" role="status">
                  <span className="gn-activity-dot" aria-hidden="true" /> Loading region data
                </div>
              </div>
          )}
          {runError ? (
            <EmptyState icon={AlertTriangle} title="Could not load this run">
              {runError}
            </EmptyState>
          ) : artefact ? (
            <MapErrorBoundary>
            <MapView
              artefact={artefact}
              plan={plan?.plan ?? null}
              selectedId={selectedId}
              onSelect={setSelectedId}
              focus={mapFocus}
              showRejected={showRejectedOnMap}
              onShowRejectedChange={setShowRejectedOnMap}
              coverage={coverage} coverageFailed={coverageFailed} coverageLoading={coverageLoading}
              overview={overview} onOverviewChange={value => { setOverview(value); setSelectedId(null); }}
              onRunChange={openRun}
              isDark={isDark}
              summaries={runs}
            />
            </MapErrorBoundary>
          ) : null}

          {artefact && !overview && (
            <div className="atlas-map-tools">
              <Button size="sm" variant="outline" aria-label={navCollapsed ? "Open investigation queue" : "Collapse investigation queue"}
                aria-expanded={!navCollapsed} onClick={() => setNavCollapsed(v => !v)}>
                {navCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
              </Button>
            </div>
          )}
        </section>

        {/* -------------------------------------------- evidence column -- */}
          {selectedId && artefact && (
            <section aria-label="Evidence inspector" className="atlas-evidence gn-enter-x" inert={pageOpen || undefined}>
              <EvidencePanel
                key={selectedId}
                artefact={artefact}
                detectionId={selectedId}
                score={selectedScore}
                rank={selectedRank}
                robustness={robustness}
                onClose={() => setSelectedId(null)}
              />
            </section>
          )}

        {/* ------------------------------------ full-width pages over the map -- */}
          {pageOpen && (
            <div key={tab} className="gn-page-layer gn-enter">
              {tab === "regions"
                ? <RegionsView runs={runs} activeRunId={runId} loading={booting} onOpen={id => { openRun(id); setTab("explore"); }} />
                : <SystemView meta={meta} benchmark={benchmark} runs={runs} artefact={artefact} staticMode={staticMode} />}
            </div>
          )}
      </main>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} index={searchIndex} onPick={onPick} />

      {/* ------------------------------------------------- status strip -- */}
      {!overview && Boolean(plan?.degradations.length || artefact?.provenance.notes.length || approveWarning) && (
        <footer className="atlas-footer">
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
      </div>

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

/** Placeholder rows shaped like the queue, so a loading region never shows a blank column. */
function QueueSkeleton() {
  return (
    <div className="space-y-px px-5 pt-2" aria-hidden="true">
      {[0, 1, 2, 3, 4].map(i => (
        <div key={i} className="space-y-2 border-b border-border py-4">
          <Skeleton className="h-2.5 w-20" />
          <Skeleton className="h-3.5 w-44" />
          <Skeleton className="h-2 w-32" />
        </div>
      ))}
    </div>
  );
}
