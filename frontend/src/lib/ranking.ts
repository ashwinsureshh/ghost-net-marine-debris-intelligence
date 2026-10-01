/**
 * How each dispatch site moved between two plans.
 *
 * Positive = moved up (towards rank 1). `null` = newly in the plan, so there
 * is no previous rank to compare against; that is shown as NEW, not as a
 * jump from some invented position.
 */
export type RankDelta = number | null;

export function rankDeltas(
  previous: readonly { detection_id: string; rank: number }[] | null,
  next: readonly { detection_id: string; rank: number }[],
): Map<string, RankDelta> {
  const before = new Map(previous?.map(a => [a.detection_id, a.rank]) ?? []);
  const out = new Map<string, RankDelta>();
  for (const { detection_id, rank } of next) {
    const was = before.get(detection_id);
    out.set(detection_id, previous === null ? 0 : was === undefined ? null : was - rank);
  }
  return out;
}

export function formatDelta(delta: RankDelta): { label: string; tone: "up" | "down" | "same" | "new" } {
  if (delta === null) return { label: "NEW", tone: "new" };
  if (delta > 0) return { label: `↑ +${delta}`, tone: "up" };
  if (delta < 0) return { label: `↓ ${delta}`, tone: "down" };
  return { label: "—", tone: "same" };
}
