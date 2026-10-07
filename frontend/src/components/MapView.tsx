import L from "leaflet";
import { Globe2, Layers, Scan, WifiOff } from "lucide-react";
import * as React from "react";
import type { DispatchPlan, RunArtefact, RunSummary } from "@/lib/types";
import { cn, humanise } from "@/lib/utils";
import { clusterObservations } from "@/lib/mapClusters";
import { runCoverage, type RunCoverage } from "@/lib/coverage";
import { formatDateShort } from "@/lib/utils";
import { Badge } from "@/components/ui/primitives";
import { DURATION, MAP_FLY_SECONDS, useAnimatedNumber, useReducedMotion } from "@/lib/motion";
import { playback } from "@/lib/playback";
import { sampleTrack } from "@/lib/trajectory";
import { dataQuality, latestCandidateDate } from "@/lib/regions";

/**
 * The operations map.
 *
 * Two decisions worth knowing:
 *
 * 1. **Basemap tiles are optional.** PRD 9.1 names dead venue wifi as a demo
 *    risk, so a failed tile load is a handled state, not a broken screen: the
 *    map keeps every marker, trajectory and MPA and falls back to a graticule
 *    over the app surface. Everything that matters is vector data we already
 *    hold; the basemap is context, not content.
 * 2. **Rejected detections are drawn, not hidden.** The Verification Agent's
 *    contribution is what it threw away (PRD 8), so rejections stay on the map
 *    as hollow markers and can be toggled — never silently dropped.
 *
 * Motion is reserved for changes the operator caused: flying to a region or a
 * selection, a group opening outward, rejected records leaving, a modelled
 * track being traced. The overlay is rebuilt on every zoom, so every entrance
 * effect is a one-shot cue consumed by the next redraw, never a default.
 */

/*
 * Basemaps are Esri's Canvas services, keyless, and the zoom cap below is
 * measured rather than assumed.
 *
 * TWO PROVIDERS HAVE NOW FAILED HERE THE SAME WAY, so the shape is worth
 * naming: neither returns 404 when it cannot serve a tile. CARTO returns a
 * tile stamped "API KEY REQUIRED"; Esri returns one reading "Map data not yet
 * available". Both are HTTP 200. `tileerror` never fires, the graticule
 * fallback never triggers, and the map looks broken while every health check
 * says it is fine.
 *
 * That is also why this is Canvas and not the Ocean basemap it briefly was.
 * World_Ocean_Base is the prettier and more thematically apt choice — a
 * bathymetric chart for a marine console — but it only carries real data to
 * ZOOM 10 in both our regions, and the console opens at 11. Everything past
 * that was the placeholder. Bathymetry is not worth a map that stops working
 * at the zoom an operator actually inspects a detection at.
 *
 * maxNativeZoom is 16 because that is where the placeholder starts, verified
 * tile-by-tile at both Pondicherry (the synthetic demo) and the Gulf of
 * Honduras (the real region). The service metadata CLAIMS 23; it describes the
 * tiling scheme, not the coverage, and trusting it is what produced the bug.
 * Beyond 16 Leaflet upscales the last real level, which is blurry but honest.
 *
 * No `{s}` subdomains — Esri serves from one host.
 */
const TILE_LIGHT =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const TILE_DARK =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}";
/* The Canvas bases carry roads and coastline but no place names, and losing
 * coastal labels costs an operator their orientation. Esri publish a matching
 * transparent Reference overlay for each. */
const TILE_LIGHT_LABELS =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
const TILE_DARK_LABELS =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
/** Where Esri's Canvas tiles stop being real. Measured, not from metadata. */
const MAX_NATIVE_ZOOM = 16;
const ATTRIBUTION_LIGHT = "Esri, HERE, Garmin, &copy; OpenStreetMap contributors";
const ATTRIBUTION_DARK = "Esri, HERE, Garmin, &copy; OpenStreetMap contributors";

interface MapViewProps {
  artefact: RunArtefact;
  plan: DispatchPlan | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** A point to move to that is not a detection (a protected area picked in search). */
  focus?: { lat: number; lon: number; key: number } | null;
  showRejected: boolean;
  onShowRejectedChange: (show: boolean) => void;
  isDark: boolean;
  coverage: RunCoverage[];
  coverageFailed: number;
  coverageLoading: boolean;
  overview: boolean;
  onOverviewChange: (value: boolean) => void;
  onRunChange: (id: string) => void;
  summaries?: RunSummary[];
}

type LayerKey = "areas" | "forward" | "backward" | "sar";

const css = (name: string, fallback: string) => {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
};

export function MapView({
  artefact,
  plan,
  selectedId,
  onSelect,
  focus = null,
  showRejected,
  onShowRejectedChange,
  isDark,
  coverage, coverageFailed, coverageLoading, overview, onOverviewChange, onRunChange, summaries = [],
}: MapViewProps) {
  const reduced = useReducedMotion();
  const currentCoverage = React.useMemo(() => runCoverage(artefact), [artefact]);
  const container = React.useRef<HTMLDivElement>(null);
  const map = React.useRef<L.Map | null>(null);
  const tiles = React.useRef<L.TileLayer | null>(null);
  const tileLabels = React.useRef<L.TileLayer | null>(null);
  const overlay = React.useRef<L.LayerGroup | null>(null);
  const fittedRun = React.useRef<string | null>(null);
  const [tilesFailed, setTilesFailed] = React.useState(false);
  const [zoom, setZoom] = React.useState(11);
  const [layersOpen, setLayersOpen] = React.useState(false);
  const [layers, setLayers] = React.useState<Record<LayerKey, boolean>>({ areas: true, forward: true, backward: true, sar: true });
  const layerControls = React.useRef<HTMLDivElement>(null);
  // One-shot cues for the NEXT redraw only (see the header comment).
  const enter = React.useRef<{ ids: Set<string> | null; from: L.LatLng | null }>({ ids: null, from: null });
  const drawnSelection = React.useRef<string | null>(null);
  const previousLayers = React.useRef<Record<LayerKey, boolean> | null>(null);
  const [leaving, setLeaving] = React.useState(false);

  const fitObservations = React.useCallback((animate = false) => {
    const instance = map.current;
    if (!instance) return;
    const fly = animate && !reduced;
    const fit = (bounds: L.LatLngBounds, options: L.FitBoundsOptions) => fly
      ? instance.flyToBounds(bounds, { ...options, duration: MAP_FLY_SECONDS * 1.4, easeLinearity: 0.35 })
      : instance.fitBounds(bounds, { ...options, animate: false });
    if (overview) {
      const bounds = coverage.flatMap(r => r.bounds ? [
        [r.bounds[1], r.bounds[0]] as L.LatLngTuple, [r.bounds[3], r.bounds[2]] as L.LatLngTuple,
      ] : []);
      if (bounds.length) {
        const compact = instance.getSize().x < 760;
        fit(L.latLngBounds(bounds).pad(0.2), { maxZoom: 3,
          paddingTopLeft: compact ? [20, 55] : [350, 55],
          paddingBottomRight: compact ? [20, instance.getSize().y * 0.52] : [30, 40] });
      } else instance.setView([18, 0], 2, { animate: false });
      return;
    }
    const verified = new Set(artefact.verifications.filter(v => v.verified).map(v => v.detection_id));
    const visible = artefact.detections.filter(d => showRejected || verified.has(d.id) || d.id === selectedId);
    if (visible.length) {
      fit(L.latLngBounds(visible.map(d => [d.lat, d.lon] as L.LatLngTuple)).pad(0.25), { maxZoom: 12 });
    } else if (currentCoverage.bounds) {
      const [west, south, east, north] = currentCoverage.bounds;
      fit(L.latLngBounds([[south, west], [north, east]]), { maxZoom: 12 });
    }
  }, [artefact, showRejected, selectedId, currentCoverage, overview, coverage, reduced]);

  React.useEffect(() => {
    if (!overview || !map.current) return;
    const instance = map.current;
    const refit = () => fitObservations(false);
    instance.on('resize', refit);
    return () => { instance.off('resize', refit); };
  }, [overview, fitObservations]);

  React.useEffect(() => {
    if (!layersOpen) return;
    const dismiss = (event: PointerEvent) => {
      if (!layerControls.current?.contains(event.target as Node)) setLayersOpen(false);
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [layersOpen]);

  // -- create once ------------------------------------------------------
  React.useEffect(() => {
    if (!container.current || map.current) return;
    const instance = L.map(container.current, {
      zoomControl: true,
      attributionControl: true,
      // Only selected trajectories and protected areas are vector paths.
      // SVG avoids a pending Canvas redraw after StrictMode tears down a map.
      preferCanvas: false,
    });
    instance.setView([12.1, 80.0], 11);
    overlay.current = L.layerGroup().addTo(instance);
    map.current = instance;
    const updateZoom = () => setZoom(instance.getZoom());
    instance.on("zoomend", updateZoom);
    const resize = new ResizeObserver(() => instance.invalidateSize());
    resize.observe(container.current);
    return () => {
      resize.disconnect();
      instance.off("zoomend", updateZoom);
      instance.remove();
      map.current = null;
      fittedRun.current = null;
    };
  }, []);

  // -- basemap follows the theme, and degrades if it cannot load ---------
  React.useEffect(() => {
    if (!map.current) return;
    tiles.current?.remove();
    tileLabels.current?.remove();
    tileLabels.current = null;
    const layer = L.tileLayer(isDark ? TILE_DARK : TILE_LIGHT, {
      attribution: isDark ? ATTRIBUTION_DARK : ATTRIBUTION_LIGHT,
      // Keep the measured Canvas limit; upscale beyond it instead of requesting placeholders.
      maxZoom: 19,
      maxNativeZoom: MAX_NATIVE_ZOOM,
      crossOrigin: true,
    });
    let failures = 0;
    layer.on("tileerror", () => {
      failures += 1;
      // One dropped tile is noise; a handful means we are offline.
      if (failures >= 3) setTilesFailed(true);
    });
    layer.on("tileload", () => setTilesFailed(false));
    layer.addTo(map.current);
    tiles.current = layer;

    // Labels for both themes now. No tileerror handler: if the base loaded the
    // network is fine, and a missing label is not worth claiming we are offline.
    const labels = L.tileLayer(isDark ? TILE_DARK_LABELS : TILE_LIGHT_LABELS, {
      maxZoom: 19,
      maxNativeZoom: MAX_NATIVE_ZOOM,
      crossOrigin: true,
    });
    labels.addTo(map.current);
    tileLabels.current = labels;
  }, [isDark]);

  // -- redraw the vector overlay ----------------------------------------
  React.useEffect(() => {
    const instance = map.current;
    const group = overlay.current;
    if (!instance || !group) return;
    group.clearLayers();

    // Study coverage is distinct from detection density. Never suggest that
    // empty ocean outside these requested windows has been surveyed.
    const overviewLabels: L.Point[] = [];
    for (const region of overview ? coverage : [currentCoverage]) {
      if (!region.bounds || region.synthetic) continue;
      const [w, s, e, n] = region.bounds;
      const label = regionPreview(region, summaries.find(r => r.run_id === region.runId), overview);
      const rectangle = L.rectangle([[s, w], [n, e]], {
        color: css('--primary', '#a35d42'), weight: 1.5, dashArray: '6 5',
        fillOpacity: overview ? 0.12 : 0.025, interactive: overview,
      }).bindTooltip(label).addTo(group);
      if (overview) {
        rectangle.on('click', () => onRunChange(region.runId));
        rectangle.on('mouseover', () => rectangle.setStyle({ fillOpacity: 0.22, weight: 2.5 }));
        rectangle.on('mouseout', () => rectangle.setStyle({ fillOpacity: 0.12, weight: 1.5 }));
        const icon = L.divIcon({ className: 'atlas-coverage-marker', iconSize: [46, 34], iconAnchor: [23, 17],
          html: `<span>${region.detections}</span>` });
        const centre = L.latLng((s + n) / 2, (w + e) / 2);
        const projected = instance.project(centre, zoom);
        const labelPoint = projected.clone();
        while (overviewLabels.some(p => Math.abs(p.x - labelPoint.x) < 54 && Math.abs(p.y - labelPoint.y) < 40)) labelPoint.y -= 42;
        overviewLabels.push(labelPoint);
        const labelPosition = instance.unproject(labelPoint, zoom);
        if (!labelPoint.equals(projected)) L.polyline([centre, labelPosition], {
          color: css('--foreground', '#203e39'), weight: 1, opacity: 0.7, interactive: false,
        }).addTo(group);
        L.marker(labelPosition, { icon,
          title: `Open ${region.name} · ${region.detections} detection records`,
        }).bindTooltip(label.cloneNode(true) as HTMLElement).on('click', () => onRunChange(region.runId)).addTo(group);
      }
    }
    const frameKey = `${artefact.run_id}:${overview ? coverage.map(r => r.runId).join(',') : 'regional'}`;
    if (overview) {
      // Fly between a region and the global view; the very first frame snaps.
      if (fittedRun.current !== frameKey) { const had = fittedRun.current !== null; fittedRun.current = frameKey; fitObservations(had); }
      return;
    }

    const cue = enter.current;
    enter.current = { ids: null, from: null };
    const selectionChanged = drawnSelection.current !== selectedId;
    drawnSelection.current = selectedId;
    const priorLayers = previousLayers.current;
    const newlyOn = (key: LayerKey) => !reduced && priorLayers !== null && !priorLayers[key] && layers[key];
    previousLayers.current = { ...layers };

    const verified = new Set(artefact.verifications.filter((v) => v.verified).map((v) => v.detection_id));
    const verifications = new Map(artefact.verifications.map(v => [v.detection_id, v]));
    const ranked = new Map(plan?.assignments.map((a) => [a.detection_id, a.rank]) ?? []);
    const colVerified = css("--chart-verified", "#22a5a5");
    const colRejected = css("--chart-rejected", "#e07a3c");
    const colPrimary = css("--primary", "#3b82f6");
    const colWarning = css("--warning", "#f59e0b");

    // Protected areas first, so they sit under everything else.
    for (const area of layers.areas ? artefact.protected_areas : []) {
      L.circle([area.lat, area.lon], {
        radius: Math.max(area.radius_km, 1) * 1000,
        color: colVerified,
        weight: 1,
        opacity: 0.5,
        fillColor: colVerified,
        fillOpacity: 0.07,
        dashArray: "4 4",
        interactive: false,
        className: newlyOn("areas") ? "gn-fade-in" : undefined,
      })
        .bindTooltip(`${area.name}${area.designation ? ` — ${area.designation}` : ""}`, {
          sticky: true,
        })
        .addTo(group);
    }

    // Trajectories for the selected detection only — drawing every track at
    // once turns the map into spaghetti and hides the thing being inspected.
    if (selectedId) {
      for (const [track, colour, dash] of [
        [artefact.backward[selectedId], colWarning, "5 5"],
        [artefact.forward[selectedId], colPrimary, undefined],
      ] as const) {
        if (!track || !layers[track.direction]) continue;
        const line = track.points.map((p) => [p.lat, p.lon] as L.LatLngExpression);
        // Trace the path out from the detection when the selection changes,
        // so the eye follows it. Only then: not on zoom or pan.
        const animateIn = !reduced && (selectionChanged || newlyOn(track.direction));
        L.polyline(line, {
          color: colour,
          weight: 2,
          opacity: 0.85,
          dashArray: dash,
          className: animateIn ? (dash ? "gn-fade-in" : "gn-track-draw") : undefined,
        })
          .bindTooltip(
            `Modelled ${track.direction} trajectory — ` +
              `${track.horizon_days} days, ${track.ensemble_size}-member ensemble. A prediction, not observed movement.`,
          )
          .addTo(group);
        // Uncertainty envelope at the endpoint (FR-3.3).
        const end = track.points[track.points.length - 1];
        if (end && end.uncertainty_km > 0) {
          L.circle([end.lat, end.lon], {
            radius: end.uncertainty_km * 1000,
            color: colour,
            weight: 1,
            opacity: 0.45,
            fillColor: colour,
            fillOpacity: 0.06,
            interactive: false,
            className: animateIn ? "gn-fade-in-late" : undefined,
          }).addTo(group);
        }
      }
    }

    // Dark vessels for the selected detection.
    const correlation = selectedId ? artefact.correlations[selectedId] : undefined;
    const sarFade = newlyOn("sar") || (selectionChanged && !reduced);
    for (const vessel of layers.sar ? correlation?.dark_vessels ?? [] : []) {
      L.marker([vessel.lat, vessel.lon], {
        icon: L.divIcon({
          className: "",
          html: `<div class="${sarFade ? "gn-fade-in-late" : ""}" style="width:14px;height:14px;border:2px solid ${colWarning};transform:rotate(45deg);background:transparent"></div>`,
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        }),
        keyboard: false,
      })
        .bindTooltip(
          `AIS-unmatched SAR grid observation` +
            (vessel.length_m ? ` — ${vessel.length_m} m` : "") +
            "<br><em>Investigation signal only, not an accusation.</em>",
        )
        .addTo(group);
    }

    // Project in world coordinates so clusters remain stable when the user pans.
    const visible = artefact.detections.filter(d => showRejected || verified.has(d.id) || d.id === selectedId);
    const projected = visible.map(detection => {
      const point = instance.project([detection.lat, detection.lon], zoom);
      return { id: detection.id, x: point.x, y: point.y, detection };
    });
    for (const cluster of clusterObservations(projected, selectedId)) {
      if (cluster.members.length > 1) {
        const count = cluster.members.length;
        const kept = cluster.members.filter(p => verified.has(p.id)).length;
        const dispatch = cluster.members.filter(p => ranked.has(p.id)).length;
        const centre = instance.unproject([cluster.x, cluster.y], zoom);
        const marker = L.marker(centre, {
          icon: L.divIcon({ className: "atlas-cluster-icon", iconSize: [40, 40], iconAnchor: [20, 20],
            html: `<span class="atlas-cluster-count">${count}</span>${dispatch ? '<i aria-hidden="true"></i>' : ''}` }),
          title: `${count} detections · ${kept} verified · ${count - kept} rejected${dispatch ? ` · ${dispatch} dispatch sites` : ""}`,
          zIndexOffset: 100,
        });
        // Build real DOM nodes: data values are text, never interpolated HTML.
        const content = document.createElement("div");
        content.className = "atlas-cluster-popup";
        const heading = document.createElement("h3");
        heading.textContent = `${count} detections in this group`;
        content.append(heading);
        const detail = document.createElement("p");
        detail.textContent = `${kept} verified · ${count - kept} rejected · ${dispatch} dispatch sites. Records across acquisitions, not distinct debris objects.`;
        content.append(detail);
        if (zoom < 19) {
          const closer = document.createElement("button");
          closer.className = "atlas-cluster-zoom";
          closer.textContent = "Zoom into group";
          closer.onclick = () => {
            instance.closePopup();
            // The group opens outward: the redraw after the zoom starts its
            // members at the group's centre and moves each to its position.
            enter.current = { ids: new Set(cluster.members.map(p => p.id)), from: centre };
            const bounds = L.latLngBounds(cluster.members.map(p => [p.detection.lat, p.detection.lon] as L.LatLngTuple));
            const options = { padding: [60, 60] as L.PointTuple, maxZoom: Math.min(zoom + 3, 19) };
            if (reduced) instance.fitBounds(bounds, { ...options, animate: false });
            else instance.flyToBounds(bounds, { ...options, duration: MAP_FLY_SECONDS });
          };
          content.append(closer);
        }
        const list = document.createElement("div");
        list.className = "atlas-cluster-members";
        for (const { detection } of cluster.members) {
          const item = document.createElement("button");
          const rank = ranked.get(detection.id);
          item.textContent = `${rank === undefined ? "" : `Rank ${rank} · `}${verified.has(detection.id) ? "Verified" : "Rejected"} · ${detection.acquired_at.slice(0, 10)} — ${detection.id}`;
          item.onclick = () => { instance.closePopup(); onSelect(detection.id); };
          list.append(item);
        }
        content.append(list);
        marker.bindPopup(content, {
          maxWidth: 280, minWidth: 210, className: "atlas-map-popup",
          autoPanPaddingTopLeft: [12, 70], autoPanPaddingBottomRight: [12, 40],
        });
        marker.on("popupopen", () => content.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true }));
        marker.addTo(group);
        continue;
      }
      const detection = cluster.members[0].detection;
      const isVerified = verified.has(detection.id);
      const rank = ranked.get(detection.id);
      const isSelected = detection.id === selectedId;
      const colour = rank !== undefined ? colPrimary : isVerified ? colVerified : colRejected;
      const size = rank !== undefined ? 28 : isSelected ? 22 : 14;
      // Entrance: members of an opened group travel out from its centre (a
      // spatial transition in screen pixels at the new zoom); records being
      // restored to the map fade in. Otherwise markers simply exist.
      let wrap = "gn-marker-wrap";
      let wrapStyle = "";
      if (!reduced && cue.ids?.has(detection.id)) {
        if (cue.from) {
          const a = instance.latLngToLayerPoint(cue.from);
          const b = instance.latLngToLayerPoint([detection.lat, detection.lon]);
          wrap += " gn-marker-expand";
          wrapStyle = `--from-x:${(a.x - b.x).toFixed(1)}px;--from-y:${(a.y - b.y).toFixed(1)}px`;
        } else wrap += " gn-marker-enter";
      }
      const dot = `atlas-single-dot${isSelected ? " selected" : ""}${isSelected && selectionChanged && !reduced ? " pulse-once" : ""}${rank !== undefined ? " ranked" : ""}`;
      const marker = L.marker([detection.lat, detection.lon], {
        icon: L.divIcon({
          className: `atlas-single-icon${isSelected ? " is-selected" : ""}${isVerified ? "" : " is-rejected"}${rank !== undefined ? " is-ranked" : ""}`,
          iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: `<span class="${wrap}" style="${wrapStyle}"><span style="--marker-color:${colour};--marker-fill:${rank !== undefined || isVerified ? colour : 'var(--card)'}" class="${dot}">${rank ?? ''}</span></span>`,
        }),
        title: `${isSelected ? "Selected · " : ""}${rank !== undefined ? `Rank ${rank} · ` : ""}${isVerified ? "Verified" : "Rejected"} detection ${detection.id}`,
        zIndexOffset: isSelected ? 2000 : rank !== undefined ? 1000 : 0,
      });
      marker.on("click", () => onSelect(detection.id));
      // Hover preview: status, rank and both confidences, as text nodes.
      const tooltip = document.createElement("span");
      tooltip.className = "gn-marker-tip";
      const verification = verifications.get(detection.id);
      const failed = verification?.checks.find(c => c.disqualified);
      for (const [text, strong] of [
        [rank !== undefined ? `Dispatch rank ${rank} · verified` : isVerified ? "Verified candidate" : `Rejected · ${failed ? humanise(failed.name) : "check failed"}`, true],
        [`Detection confidence ${detection.confidence.toFixed(2)}${verification ? ` · verification ${verification.confidence.toFixed(2)}` : ""}`, false],
        [`${detection.acquired_at.slice(0, 10)} · ${detection.id}`, false],
      ] as const) {
        const line = document.createElement(strong ? "strong" : "span");
        line.textContent = text;
        tooltip.append(line);
      }
      marker.bindTooltip(tooltip, { direction: "top", offset: [0, -size / 2] }).addTo(group);
    }

    if (fittedRun.current !== frameKey) {
      const had = fittedRun.current !== null;
      fittedRun.current = frameKey;
      fitObservations(had);
    }
  }, [artefact, plan, selectedId, showRejected, onSelect, isDark, zoom, layers, fitObservations, overview, coverage, currentCoverage, onRunChange, reduced, summaries]);

  // Focus the selection: glide to it without zooming out an operator who is
  // already closer in. Reduced motion jumps.
  React.useEffect(() => {
    const selected = artefact.detections.find(d => d.id === selectedId);
    const instance = map.current;
    if (overview || !selected || !instance) return;
    const target = L.latLng(selected.lat, selected.lon);
    if (reduced) instance.panTo(target, { animate: false });
    else if (instance.getBounds().pad(-0.2).contains(target)) instance.panTo(target, { animate: true, duration: DURATION.slow });
    else instance.flyTo(target, Math.max(instance.getZoom(), 11), { duration: MAP_FLY_SECONDS });
  }, [selectedId, artefact, overview, reduced]);

  // A searched-for place that is not a detection. Keyed on the pick, not on
  // `reduced` or `overview`, so it moves only when a new pick arrives, and
  // picking the same place twice moves the map back to it. Reduced motion jumps.
  React.useEffect(() => {
    const instance = map.current;
    if (!focus || overview || !instance) return;
    const target = L.latLng(focus.lat, focus.lon);
    const zoom = Math.max(instance.getZoom(), 10);
    if (reduced) instance.setView(target, zoom, { animate: false });
    else instance.flyTo(target, zoom, { duration: MAP_FLY_SECONDS });
  }, [focus?.key]);

  // Trajectory playback: one marker and one growing envelope, moved in place
  // each frame. Nothing else on the map is redrawn while it plays.
  React.useEffect(() => {
    const instance = map.current;
    if (!instance || overview) return;
    const layer = L.layerGroup().addTo(instance);
    let marker: L.Marker | null = null;
    let ring: L.Circle | null = null;
    let drawnDirection: string | null = null;
    const update = () => {
      const state = playback.get();
      const track = state.detectionId && state.detectionId === selectedId
        ? (state.direction === "forward" ? artefact.forward : artefact.backward)[state.detectionId] : undefined;
      const sample = track ? sampleTrack(track.points, state.fraction) : null;
      if (!sample || (state.fraction === 0 && !state.playing)) {
        layer.clearLayers(); marker = null; ring = null; drawnDirection = null; return;
      }
      const at = L.latLng(sample.lat, sample.lon);
      if (!marker || !ring || drawnDirection !== state.direction) {
        layer.clearLayers();
        const colour = css(state.direction === "forward" ? "--primary" : "--warning", "#98632c");
        ring = L.circle(at, { radius: 50, color: colour, weight: 1.5, opacity: 0.75, fillColor: colour,
          fillOpacity: 0.12, interactive: false }).addTo(layer);
        marker = L.marker(at, { interactive: false, keyboard: false, zIndexOffset: 3000,
          icon: L.divIcon({ className: `gn-playhead gn-playhead--${state.direction}`, iconSize: [14, 14], iconAnchor: [7, 7],
            html: "<span></span><em>Modelled</em>" }) }).addTo(layer);
        drawnDirection = state.direction;
      }
      ring.setLatLng(at).setRadius(Math.max(sample.uncertainty_km, 0.05) * 1000);
      marker.setLatLng(at);
    };
    update();
    const unsubscribe = playback.subscribe(update);
    return () => { unsubscribe(); layer.remove(); };
  }, [artefact, selectedId, overview]);

  // RAW DETECTIONS vs VERIFIED ONLY: rejected markers fade before they are
  // removed, and fade back in when restored.
  const setRawMode = (raw: boolean) => {
    if (raw === showRejected || leaving) return;
    if (raw) {
      enter.current = { ids: new Set(artefact.verifications.filter(v => !v.verified).map(v => v.detection_id)), from: null };
      onShowRejectedChange(true);
      return;
    }
    if (reduced) { onShowRejectedChange(false); return; }
    setLeaving(true);
    window.setTimeout(() => { onShowRejectedChange(false); setLeaving(false); }, DURATION.normal * 1000);
  };

  return (
    <div className={cn("relative size-full", overview && "atlas-overview", selectedId && "map-has-selection", leaving && "rejected-leaving")}>
      <div
        ref={container}
        className="size-full"
        role="application"
        aria-label="Map of detections, drift trajectories and protected areas"
      />

      {tilesFailed && (
        <>
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 z-[400] opacity-40"
            style={{
              backgroundImage:
                "linear-gradient(to right, var(--border) 1px, transparent 1px)," +
                "linear-gradient(to bottom, var(--border) 1px, transparent 1px)",
              backgroundSize: "64px 64px",
            }}
          />
          <div className="absolute bottom-3 left-3 z-[500] flex items-center gap-2 rounded-md border border-border bg-card/95 px-2.5 py-1.5 text-xs shadow-sm backdrop-blur">
            <WifiOff className="size-3.5 text-warning" />
            <span className="text-muted-foreground">
              Basemap offline — positions, tracks and areas are unaffected.
            </span>
          </div>
        </>
      )}

      <div className="atlas-layer-controls" ref={layerControls} onKeyDown={event => {
        if (event.key === "Escape" && layersOpen) {
          event.stopPropagation(); setLayersOpen(false);
          layerControls.current?.querySelector<HTMLButtonElement>("[aria-expanded]")?.focus();
        }
      }}>
        <div className="atlas-layer-toolbar">
          <button type="button" onClick={() => { setLayersOpen(false); onOverviewChange(!overview); }} aria-pressed={overview}><Globe2 size={15} /> {overview ? 'Back to region' : 'Coverage'}</button>
          {!overview && <button type="button" onClick={() => fitObservations(true)} title="Fit visible observations" aria-label="Fit observations"><Scan size={15} /> <span className="atlas-fit-label">Fit observations</span><span className="atlas-fit-short">Fit</span></button>}
          {!overview && <button type="button" onClick={() => setLayersOpen(open => !open)} aria-expanded={layersOpen} aria-controls="map-layer-options">
            <Layers size={15} /> Layers
          </button>}
        </div>
        {layersOpen && <fieldset id="map-layer-options" className="atlas-layer-options">
          <legend>Map layers</legend>
          <label><input type="checkbox" checked={showRejected} onChange={e => setRawMode(e.target.checked)} /> Rejected detections</label>
          {([{ id: "areas", label: "Protected areas" }, { id: "forward", label: "Forward drift & envelope" },
            { id: "backward", label: "Backward drift & envelope" }, { id: "sar", label: "Unmatched SAR observations" }] as const).map(layer => (
            <label key={layer.id}><input type="checkbox" checked={layers[layer.id]}
              onChange={e => setLayers(current => ({ ...current, [layer.id]: e.target.checked }))} /> {layer.label}</label>
          ))}
          <p>Drift and SAR layers use the selected detection. The selected marker stays visible, even if rejected detections are hidden.</p>
        </fieldset>}
      </div>
      {overview ? <section className="atlas-coverage-panel" aria-label="Available study regions">
        <span className="atlas-eyebrow">Coverage atlas</span>
        <h2>Where we have looked.</h2>
        <p>Historical regional runs, not a global survey. Blank areas mean no analysis is available here — not no debris.</p>
        {coverageLoading && <p role="status">Loading available regions…</p>}
        {coverageFailed > 0 && <p role="alert">{coverageFailed} run(s) could not be loaded. Their coverage is unavailable.</p>}
        {!coverageLoading && !coverage.length && <p>No readable real runs are available. Synthetic demos are excluded from this atlas.</p>}
        <div className="atlas-coverage-list">{coverage.map(region => {
          const summary = summaries.find(r => r.run_id === region.runId);
          return <button key={region.runId} type="button" onClick={() => onRunChange(region.runId)}>
            <strong>{region.name}</strong>
            <span>{region.start ? formatDateShort(region.start) : 'Unknown date'} — {region.end ? formatDateShort(region.end) : 'unknown'} · {region.detections} records{summary?.verified !== undefined ? ` · ${summary.verified} verified` : ''}</span>
            <small>{region.scope === 'requested-aoi' ? 'Requested imagery AOI' : region.scope === 'region' ? 'Study region · exact imagery footprint unavailable' : 'Extent unavailable'}
              {summary ? ` · data quality ${dataQuality(summary).label.toLowerCase()}` : ''}</small>
            {region.partial && <small className="text-warning">Partial inputs · see run caveats</small>}
          </button>;
        })}</div>
        <small>Rectangles show requested areas, not uninterrupted cloud-free coverage. Synthetic demos remain in the region selector.</small>
      </section> : <aside className="atlas-coverage-context" aria-label="Regional coverage">
        <strong>{currentCoverage.synthetic ? 'Synthetic scene · no observed coverage' : currentCoverage.scope === 'requested-aoi' ? 'Regional imagery window' : 'Regional study window'}</strong>
        <span>{currentCoverage.start ? formatDateShort(currentCoverage.start) : 'Date unavailable'}{currentCoverage.end ? ` — ${formatDateShort(currentCoverage.end)}` : ''}</span>
        <small>{currentCoverage.synthetic ? 'Generated data, not satellite detections.' : currentCoverage.scope === 'requested-aoi' ? 'Dashed outline: requested AOI. Cloud and water masks leave gaps.' : 'Exact imagery footprint unavailable; outline is the study region.'} Outside this run: not analysed. No detection is not the same as no debris.</small>
        {zoom < 7 && <button type="button" onClick={() => fitObservations(true)}>Return to coastal detail →</button>}
      </aside>}
      {!overview && <VerificationCompare artefact={artefact} raw={showRejected && !leaving} onChange={setRawMode} />}
      {!overview && <div className="atlas-map-legend pointer-events-none absolute right-3 top-3 z-[500] flex flex-col items-end gap-1.5">
        <Legend showRejected={showRejected} layers={layers} />
      </div>}
    </div>
  );
}

/**
 * Agent 2's contribution as a switch: every raw candidate, or only those that
 * survived the five false-positive checks. The counts are the run's own.
 */
function VerificationCompare({ artefact, raw, onChange }: {
  artefact: RunArtefact; raw: boolean; onChange: (raw: boolean) => void;
}) {
  const total = artefact.detections.length;
  const kept = React.useMemo(() => artefact.verifications.filter(v => v.verified).length, [artefact]);
  const top = React.useMemo(() => {
    const failed = new Map<string, number>();
    for (const v of artefact.verifications) if (!v.verified) for (const c of v.checks) if (c.disqualified) failed.set(c.name, (failed.get(c.name) ?? 0) + 1);
    return [...failed].sort((a, b) => b[1] - a[1])[0];
  }, [artefact]);
  const shown = useAnimatedNumber(raw ? total : kept);
  return (
    <div className="gn-verify-compare" role="group" aria-label="Verification comparison">
      <div className="gn-segment">
        <button type="button" aria-pressed={raw} onClick={() => onChange(true)}>Raw detections</button>
        <button type="button" aria-pressed={!raw} onClick={() => onChange(false)}>Verified only</button>
      </div>
      <p><strong className="tabular">{Math.round(shown)}</strong> {raw ? "raw candidates shown" : "verified shown"}</p>
      <small>{total} → {kept} after verification · {total - kept} rejected{top ? ` · most often ${humanise(top[0]).toLowerCase()} (${top[1]})` : ""}</small>
    </div>
  );
}

/** Hover card for a region outline, built from text nodes. */
function regionPreview(region: RunCoverage, summary: RunSummary | undefined, rich: boolean): HTMLElement {
  const root = document.createElement("span");
  root.className = "gn-region-tip";
  const add = (tag: string, text: string) => { const el = document.createElement(tag); el.textContent = text; root.append(el); };
  add("strong", region.name);
  if (!rich || !summary) {
    add("span", region.scope === "requested-aoi" ? "Requested imagery AOI" : "Study region; imagery footprint unavailable");
    return root;
  }
  add("span", `${summary.detections ?? region.detections} candidates · ${summary.verified ?? "—"} verified`);
  add("span", `Data quality: ${dataQuality(summary).label} (inputs, not accuracy)`);
  const latest = latestCandidateDate(summary);
  if (latest) add("span", `Latest candidate: ${latest}`);
  add("small", "Click to open this region");
  return root;
}

function Legend({ showRejected, layers }: { showRejected: boolean; layers: Record<LayerKey, boolean> }) {
  const items = [
    { label: "Count = grouped detections", className: "bg-foreground", shape: "round" as const },
    { label: "Dispatch rank", className: "bg-primary", shape: "round" as const },
    { label: "Verified", className: "bg-chart-verified/60 border-chart-verified", shape: "ring" as const },
    ...(showRejected
      ? [{ label: "Rejected", className: "border-chart-rejected", shape: "ring" as const }]
      : []),
    ...(layers.areas ? [{ label: "Protected area (approx.)", className: "border-chart-verified", shape: "ring" as const }] : []),
    ...(layers.forward ? [{ label: "Forward drift (modelled)", className: "bg-primary", shape: "line" as const }] : []),
    ...(layers.backward ? [{ label: "Backward drift (modelled)", className: "bg-warning", shape: "dash" as const }] : []),
    ...(layers.sar ? [{ label: "Unmatched SAR observation", className: "border-warning", shape: "diamond" as const }] : []),
  ];

  /* A key, not a card: no heading, no shadow, no chrome. It sits over the
     chart and has to stay legible without competing with it — the map is the
     content, and a legend that announces itself is taking attention the
     detections need. */
  return (
    <div className="rounded-sm bg-card/85 px-2 py-1.5 backdrop-blur-[2px]">
      <ul className="space-y-[3px]">
        {items.map((item) => (
          <li
            key={item.label}
            className="flex items-center gap-1.5 text-[10.5px] leading-tight text-muted-foreground"
          >
            <span
              aria-hidden="true"
              className={cn(
                "inline-block shrink-0",
                item.shape === "round" && "size-2 rounded-full",
                item.shape === "ring" && "size-2 rounded-full border",
                item.shape === "line" && "h-px w-3.5",
                item.shape === "dash" && "h-px w-3.5 opacity-70",
                item.shape === "diamond" && "size-2 rotate-45 border",
                item.className,
              )}
            />
            {item.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function MapBadge({ children }: { children: React.ReactNode }) {
  return <Badge variant="outline">{children}</Badge>;
}
