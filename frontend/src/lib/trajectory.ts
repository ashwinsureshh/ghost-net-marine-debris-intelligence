/**
 * Sampling a modelled drift track for playback.
 *
 * The track is what the Drift Agent exported: ensemble-mean positions at its
 * integration steps, each with its uncertainty radius. Playback interpolates
 * linearly BETWEEN those exported points and never extrapolates past them, so
 * everything a viewer sees at any instant is bounded by numbers in the
 * artefact. It is a modelled trajectory, not observed movement.
 */

export interface TrackPoint {
  t: string;
  lon: number;
  lat: number;
  uncertainty_km: number;
}

export interface TrackSample {
  /** ISO-8601, interpolated between the two neighbouring exported steps. */
  t: string;
  lat: number;
  lon: number;
  uncertainty_km: number;
  /** Great-circle distance along the path from the detection, km. */
  distance_km: number;
  /** Index of the exported step at or before this sample. */
  step: number;
}

const EARTH_RADIUS_KM = 6371.0088;

export function haversineKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Cumulative along-track distance at each exported point. */
export function cumulativeKm(points: readonly TrackPoint[]): number[] {
  const out: number[] = [];
  let total = 0;
  points.forEach((point, i) => {
    if (i > 0) total += haversineKm(points[i - 1], point);
    out.push(total);
  });
  return out;
}

/**
 * The state of the track at `fraction` (0 = detection, 1 = horizon) of its
 * exported steps. Steps are evenly spaced in time in every export, so step
 * fraction and time fraction coincide; interpolating timestamps keeps that
 * honest if a future export is not.
 */
export function sampleTrack(points: readonly TrackPoint[], fraction: number,
  distances: readonly number[] = cumulativeKm(points)): TrackSample | null {
  if (points.length === 0) return null;
  const f = Number.isFinite(fraction) ? Math.min(Math.max(fraction, 0), 1) : 0;
  const position = f * (points.length - 1);
  const step = Math.min(Math.floor(position), points.length - 1);
  const next = Math.min(step + 1, points.length - 1);
  const w = position - step;
  const a = points[step];
  const b = points[next];
  const mix = (x: number, y: number) => x + (y - x) * w;
  const ta = Date.parse(a.t);
  const tb = Date.parse(b.t);
  const t = Number.isFinite(ta) && Number.isFinite(tb)
    ? new Date(mix(ta, tb)).toISOString()
    : a.t;
  return {
    t,
    lat: mix(a.lat, b.lat),
    lon: mix(a.lon, b.lon),
    uncertainty_km: mix(a.uncertainty_km, b.uncertainty_km),
    distance_km: mix(distances[step], distances[next]),
    step,
  };
}

/** Hours between the first and last exported point, for the time readout. */
export function trackHours(points: readonly TrackPoint[]): number {
  if (points.length < 2) return 0;
  const span = Math.abs(Date.parse(points[points.length - 1].t) - Date.parse(points[0].t));
  return Number.isFinite(span) ? span / 3_600_000 : 0;
}
