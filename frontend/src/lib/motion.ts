import * as React from "react";

/**
 * One set of motion tokens for the whole console.
 *
 * Motion here explains a change of state — a site moving up the ranking, a
 * rejected record leaving the map, a track being traced. It never runs on its
 * own, and components never invent their own timings: they read these. The
 * CSS side mirrors the same values as --motion-* custom properties in
 * interaction.css, so a transition in a stylesheet and one in motion/react agree.
 */
export const DURATION = {
  fast: 0.15,
  normal: 0.24,
  slow: 0.42,
} as const;

/** Decelerating: things arrive and settle; nothing bounces. */
export const EASE_OUT = [0.22, 0.61, 0.36, 1] as const;
export const EASE_IN_OUT = [0.65, 0, 0.35, 1] as const;

/** Stagger between siblings entering together, capped so long lists never crawl. */
export const STAGGER = 0.035;
export const staggerDelay = (index: number, cap = 8) => Math.min(index, cap) * STAGGER;

/** Seconds a map fly-to takes. Leaflet takes seconds, motion/react seconds too. */
export const MAP_FLY_SECONDS = 0.6;

const QUERY = "(prefers-reduced-motion: reduce)";

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    && window.matchMedia(QUERY).matches;
}

/**
 * The OS setting, live. motion/react has its own hook, but Leaflet and
 * requestAnimationFrame code needs a plain boolean too, and both must agree.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = React.useState(prefersReducedMotion);
  React.useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(QUERY);
    const update = () => setReduced(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduced;
}

/**
 * A number that eases to its new value when — and only when — it changes.
 *
 * The first value renders as-is: a metric that counts up every time a page
 * opens is decoration, and it also shows the reader numbers that were never
 * measured on the way to the real one. Reduced motion jumps straight there.
 */
export function useAnimatedNumber(value: number, duration = DURATION.slow): number {
  const reduced = useReducedMotion();
  const [shown, setShown] = React.useState(value);
  const from = React.useRef(value);
  React.useEffect(() => {
    const start = from.current;
    from.current = value;
    if (reduced || start === value || !Number.isFinite(start) || !Number.isFinite(value)) {
      setShown(value);
      return;
    }
    let frame = 0;
    const began = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - began) / (duration * 1000), 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(start + (value - start) * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    // Frames stop in background tabs and hidden panes. The number must still
    // land on the true value, never sit at an intermediate one nobody measured.
    const settle = setTimeout(() => { cancelAnimationFrame(frame); setShown(value); }, duration * 1000 + 120);
    return () => { cancelAnimationFrame(frame); clearTimeout(settle); };
  }, [value, reduced, duration]);
  return shown;
}

/** Inline style for a CSS stagger: `.gn-enter` reads the delay. */
export const staggerStyle = (index: number, cap = 8): { animationDelay: string } =>
  ({ animationDelay: `${Math.round(staggerDelay(index, cap) * 1000)}ms` });
