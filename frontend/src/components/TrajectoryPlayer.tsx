import { Pause, Play, RotateCcw } from "lucide-react";
import * as React from "react";
import type { Trajectory } from "@/lib/types";
import { PLAYBACK_SECONDS, playback, usePlayback } from "@/lib/playback";
import { cumulativeKm, sampleTrack, trackHours } from "@/lib/trajectory";
import { useReducedMotion } from "@/lib/motion";
import { formatCoord, formatDate } from "@/lib/utils";
import { Term } from "@/components/Term";

/**
 * Plays one modelled drift track on the map, with the readout beside it.
 *
 * Everything shown is interpolated between the Drift Agent's exported steps
 * (see lib/trajectory.ts). With reduced motion the track never auto-plays;
 * the scrubber reaches every position without it.
 */
export function TrajectoryPlayer({ detectionId, forward, backward }: {
  detectionId: string; forward?: Trajectory; backward?: Trajectory;
}) {
  const state = usePlayback();
  const reduced = useReducedMotion();
  const ours = state.detectionId === detectionId;
  const direction = ours ? state.direction : forward ? "forward" : "backward";
  const track = direction === "forward" ? forward : backward;
  const points = track?.points ?? [];
  const distances = React.useMemo(() => cumulativeKm(points), [points]);
  const fraction = ours ? state.fraction : 0;
  const sample = sampleTrack(points, fraction, distances);

  // Selecting another detection or leaving the panel stops playback.
  React.useEffect(() => () => {
    if (playback.get().detectionId === detectionId) playback.reset();
  }, [detectionId]);

  // The frame loop lives here, not in the map: the map only listens.
  React.useEffect(() => {
    if (!ours || !state.playing || reduced) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const s = playback.get();
      const next = Math.min(s.fraction + ((now - last) / 1000) * s.speed / PLAYBACK_SECONDS, 1);
      last = now;
      playback.set({ fraction: next, playing: next < 1 });
      if (next < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [ours, state.playing, reduced]);

  if (!track || points.length < 2 || !sample) return null;

  const claim = (patch: Partial<typeof state>) =>
    playback.set({ detectionId, direction, ...(ours ? {} : { fraction: 0, speed: state.speed }), ...patch });
  const hours = trackHours(points) * fraction;

  return (
    <div className="gn-player" aria-label="Trajectory playback">
      <div className="gn-player-head">
        <span className="gn-player-label"><Term term="Modelled trajectory">MODELLED TRAJECTORY</Term></span>
        <div className="gn-segment" role="group" aria-label="Direction">
          {(["forward", "backward"] as const).map(d => (
            <button key={d} type="button" aria-pressed={direction === d} disabled={!(d === "forward" ? forward : backward)}
              onClick={() => playback.set({ detectionId, direction: d, fraction: 0, playing: false })}>
              {d === "forward" ? "Forward" : "Backward"}
            </button>
          ))}
        </div>
      </div>
      <div className="gn-player-controls">
        {!reduced && (ours && state.playing
          ? <button type="button" onClick={() => claim({ playing: false })} aria-label="Pause"><Pause size={14} /></button>
          : <button type="button" onClick={() => claim({ playing: true, ...(fraction >= 1 ? { fraction: 0 } : {}) })}
              aria-label="Play trajectory"><Play size={14} /></button>)}
        <button type="button" onClick={() => claim({ fraction: 0, playing: false })} aria-label="Restart"><RotateCcw size={14} /></button>
        <input type="range" min={0} max={1000} value={Math.round(fraction * 1000)} aria-label="Position along the modelled trajectory"
          aria-valuetext={`${hours.toFixed(0)} hours ${direction === "forward" ? "after" : "before"} detection`}
          onChange={e => claim({ fraction: Number(e.target.value) / 1000, playing: false })} />
        {!reduced && <div className="gn-segment gn-speed" role="group" aria-label="Playback speed">
          {([1, 2, 4] as const).map(s => (
            <button key={s} type="button" aria-pressed={state.speed === s} onClick={() => playback.set({ speed: s })}>{s}×</button>
          ))}
        </div>}
      </div>
      <dl className="gn-player-readout">
        <div><dt>{direction === "forward" ? "Modelled time" : "Back-traced time"}</dt><dd>{formatDate(sample.t)}</dd></div>
        <div><dt>Offset</dt><dd>{direction === "forward" ? "+" : "−"}{hours.toFixed(0)} h</dd></div>
        <div><dt>Position</dt><dd>{formatCoord(sample.lat, sample.lon)}</dd></div>
        <div><dt><Term term="Uncertainty envelope">Envelope radius</Term></dt><dd>{sample.uncertainty_km.toFixed(1)} km</dd></div>
        <div><dt>Distance along path</dt><dd>{sample.distance_km.toFixed(1)} km</dd></div>
      </dl>
      <p className="gn-player-note">Ensemble-mean path from {track.current_field || "the current field"}, interpolated between
        exported steps. A prediction, not observed movement: the envelope is known to be too narrow.</p>
    </div>
  );
}
