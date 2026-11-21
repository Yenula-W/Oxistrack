import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** API timestamps are naive UTC; make that explicit before parsing. */
export function parseDate(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) || value.length <= 10 ? value : value + "Z");
}

export function formatDate(value?: string | null, withTime = false): string {
  if (!value) return "Not set";
  const d = value.length <= 10 ? new Date(value + "T00:00:00") : parseDate(value);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric",
    ...(withTime ? { hour: "numeric", minute: "2-digit" } : {}) });
}

export function timeAgo(value: string): string {
  const s = Math.max(0, (Date.now() - parseDate(value).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
  return formatDate(value);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function label(value: string): string {
  const s = value.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}
