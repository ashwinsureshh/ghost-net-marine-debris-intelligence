import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Signed decimal degrees -> the DMS-ish form an operator reads off a chart. */
export function formatCoord(lat: number, lon: number): string {
  const fmt = (v: number, pos: string, neg: string) =>
    `${Math.abs(v).toFixed(4)}°${v >= 0 ? pos : neg}`;
  return `${fmt(lat, "N", "S")} ${fmt(lon, "E", "W")}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

/** Turn a snake_case component key into a human label. */
export function humanise(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bMpa\b/i, "MPA")
    .replace(/\bFdi\b/i, "FDI")
    .replace(/\bNdvi\b/i, "NDVI")
    .replace(/\bAis\b/i, "AIS")
    .replace(/\bSwir\b/i, "SWIR");
}
