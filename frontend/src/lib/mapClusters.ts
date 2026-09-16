/** Display-only bins in Leaflet's world-pixel coordinates (stable while panning).
 * Each record appears once. A selected record is always its own marker.
 * A bin is not a merged scientific detection or a distinct debris/vessel count.
 */
export interface ProjectedObservation {
  id: string;
  x: number;
  y: number;
}

export function clusterObservations<T extends ProjectedObservation>(
  observations: readonly T[],
  selectedId: string | null = null,
  cellSize = 56,
): { x: number; y: number; members: T[] }[] {
  if (!Number.isFinite(cellSize) || cellSize <= 0) throw new Error("Invalid cluster cell size");
  const bins = new Map<string, T[]>();
  for (const observation of observations) {
    const key = observation.id === selectedId
      ? `selected:${observation.id}`
      : `${Math.floor(observation.x / cellSize)}:${Math.floor(observation.y / cellSize)}`;
    const members = bins.get(key) ?? [];
    members.push(observation);
    bins.set(key, members);
  }
  return [...bins.values()].map(members => ({
    x: members.reduce((sum, p) => sum + p.x, 0) / members.length,
    y: members.reduce((sum, p) => sum + p.y, 0) / members.length,
    members,
  }));
}
