import L from "leaflet";
import { WifiOff } from "lucide-react";
import * as React from "react";
import type { DispatchPlan, RunArtefact } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/primitives";

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
  showRejected: boolean;
  isDark: boolean;
}

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
  showRejected,
  isDark,
}: MapViewProps) {
  const container = React.useRef<HTMLDivElement>(null);
  const map = React.useRef<L.Map | null>(null);
  const tiles = React.useRef<L.TileLayer | null>(null);
  const tileLabels = React.useRef<L.TileLayer | null>(null);
  const overlay = React.useRef<L.LayerGroup | null>(null);
  const fittedRun = React.useRef<string | null>(null);
  const [tilesFailed, setTilesFailed] = React.useState(false);

  // -- create once ------------------------------------------------------
  React.useEffect(() => {
    if (!container.current || map.current) return;
    const instance = L.map(container.current, {
      zoomControl: true,
      attributionControl: true,
      preferCanvas: true,
    });
    instance.setView([12.1, 80.0], 11);
    overlay.current = L.layerGroup().addTo(instance);
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
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
      // Esri's ocean tiles stop at 13; asking for more returns blanks rather
      // than upscaling, so cap the request and let Leaflet scale the last
      // level instead of showing empty squares when someone zooms right in.
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

    const verified = new Set(artefact.verifications.filter((v) => v.verified).map((v) => v.detection_id));
    const ranked = new Map(plan?.assignments.map((a) => [a.detection_id, a.rank]) ?? []);
    const colVerified = css("--chart-verified", "#22a5a5");
    const colRejected = css("--chart-rejected", "#e07a3c");
    const colPrimary = css("--primary", "#3b82f6");
    const colWarning = css("--warning", "#f59e0b");
    const bounds: L.LatLngExpression[] = [];

    // Protected areas first, so they sit under everything else.
    for (const area of artefact.protected_areas) {
      L.circle([area.lat, area.lon], {
        radius: Math.max(area.radius_km, 1) * 1000,
        color: colVerified,
        weight: 1,
        opacity: 0.5,
        fillColor: colVerified,
        fillOpacity: 0.07,
        dashArray: "4 4",
        interactive: false,
      })
        .bindTooltip(`${area.name}${area.designation ? ` — ${area.designation}` : ""}`, {
          sticky: true,
        })
        .addTo(group);
      bounds.push([area.lat, area.lon]);
    }

    // Trajectories for the selected detection only — drawing every track at
    // once turns the map into spaghetti and hides the thing being inspected.
    if (selectedId) {
      for (const [track, colour, dash] of [
        [artefact.backward[selectedId], colWarning, "5 5"],
        [artefact.forward[selectedId], colPrimary, undefined],
      ] as const) {
        if (!track) continue;
        const line = track.points.map((p) => [p.lat, p.lon] as L.LatLngExpression);
        L.polyline(line, {
          color: colour,
          weight: 2,
          opacity: 0.85,
          dashArray: dash,
        })
          .bindTooltip(
            `${track.direction === "backward" ? "Backward" : "Forward"} track — ` +
              `${track.horizon_days} days, ${track.ensemble_size}-member ensemble`,
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
          }).addTo(group);
        }
        line.forEach((p) => bounds.push(p));
      }
    }

    // Dark vessels for the selected detection.
    const correlation = selectedId ? artefact.correlations[selectedId] : undefined;
    for (const vessel of correlation?.dark_vessels ?? []) {
      L.marker([vessel.lat, vessel.lon], {
        icon: L.divIcon({
          className: "",
          html: `<div style="width:14px;height:14px;border:2px solid ${colWarning};transform:rotate(45deg);background:transparent"></div>`,
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        }),
        keyboard: false,
      })
        .bindTooltip(
          `AIS-silent SAR contact ${vessel.id}` +
            (vessel.length_m ? ` — ${vessel.length_m} m` : "") +
            "<br><em>Investigation signal only, not an accusation.</em>",
        )
        .addTo(group);
      bounds.push([vessel.lat, vessel.lon]);
    }

    // Detections.
    for (const detection of artefact.detections) {
      const isVerified = verified.has(detection.id);
      if (!isVerified && !showRejected) continue;
      const rank = ranked.get(detection.id);
      const isSelected = detection.id === selectedId;
      const colour = isVerified ? colVerified : colRejected;
      bounds.push([detection.lat, detection.lon]);

      if (rank !== undefined) {
        // Ranked dispatch sites get a numbered pin — the operator's answer.
        const marker = L.marker([detection.lat, detection.lon], {
          icon: L.divIcon({
            className: "",
            html:
              `<div style="display:flex;align-items:center;justify-content:center;` +
              `width:26px;height:26px;border-radius:50%;background:${colPrimary};` +
              `color:#fff;font:600 12px/1 ui-sans-serif,system-ui;` +
              `box-shadow:0 0 0 ${isSelected ? 4 : 2}px ${colPrimary}55">${rank}</div>`,
            iconSize: [26, 26],
            iconAnchor: [13, 13],
          }),
          title: `Rank ${rank} — ${detection.id}`,
        });
        marker.on("click", () => onSelect(detection.id));
        marker.bindTooltip(`Rank ${rank} · ${detection.id}`);
        marker.addTo(group);
        continue;
      }

      const marker = L.circleMarker([detection.lat, detection.lon], {
        radius: isSelected ? 9 : 6,
        color: colour,
        weight: isSelected ? 3 : 2,
        opacity: 1,
        fillColor: colour,
        // Hollow for rejected: visibly present, visibly not selected for action.
        fillOpacity: isVerified ? 0.55 : 0.12,
      });
      marker.on("click", () => onSelect(detection.id));
      marker.bindTooltip(
        `${detection.id}<br>${isVerified ? "Verified" : "Rejected"} · confidence ${detection.confidence.toFixed(2)}`,
      );
      marker.addTo(group);
    }

    // Frame the map once per run, on the detections and protected areas only.
    // Re-fitting on every selection would yank the view around — and a 5-day
    // drift envelope is tens of km wide, so fitting to it would zoom out far
    // enough to lose the sites the operator is comparing.
    if (fittedRun.current !== artefact.run_id) {
      const frame: L.LatLngExpression[] = [
        ...artefact.detections.map((d) => [d.lat, d.lon] as L.LatLngExpression),
        ...artefact.protected_areas.map((a) => [a.lat, a.lon] as L.LatLngExpression),
      ];
      if (frame.length > 0) {
        instance.fitBounds(L.latLngBounds(frame).pad(0.35), { animate: false, maxZoom: 12 });
        fittedRun.current = artefact.run_id;
      }
    }
  }, [artefact, plan, selectedId, showRejected, onSelect]);

  return (
    <div className="relative size-full">
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

      <div className="pointer-events-none absolute right-3 top-3 z-[500] flex flex-col items-end gap-1.5">
        <Legend showRejected={showRejected} />
      </div>
    </div>
  );
}

function Legend({ showRejected }: { showRejected: boolean }) {
  const items = [
    { label: "Dispatch rank", className: "bg-primary", shape: "round" as const },
    { label: "Verified", className: "bg-chart-verified/60 border-chart-verified", shape: "ring" as const },
    ...(showRejected
      ? [{ label: "Rejected", className: "border-chart-rejected", shape: "ring" as const }]
      : []),
    { label: "Forward drift", className: "bg-primary", shape: "line" as const },
    { label: "Backward drift", className: "bg-warning", shape: "dash" as const },
    { label: "AIS-silent vessel", className: "border-warning", shape: "diamond" as const },
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
