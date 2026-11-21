import * as React from "react";
import { CircleNotch } from "@phosphor-icons/react";
import { cn, label } from "@/lib/utils";

type Tone = "neutral" | "ok" | "warn" | "bad" | "brand" | "blue";

/** A plain text label. No pill, no fill, no colour: adjacent labels are separated by a middot (see globals.css). */
export function Badge({ className, children, strong }: { tone?: Tone; icon?: unknown; className?: string; children: React.ReactNode; strong?: boolean }) {
  return <span className={cn("meta whitespace-nowrap text-xs", strong ? "font-medium text-ink" : "text-ink-3", className)}>{children}</span>;
}

// States that need someone's attention are set in full-strength text; settled states recede.
const ATTENTION = new Set(["failed", "open", "needs_review", "under_review", "processing", "queued", "suggested", "active", "draft"]);
const TEXT: Record<string, string> = { processing: "Analyzing", not_checked: "Not checked", needs_review: "Needs review", under_review: "Under review" };

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <span className={cn("meta inline-flex items-center gap-1.5 whitespace-nowrap text-xs", ATTENTION.has(status) ? "font-medium text-ink" : "text-ink-3", className)}>
      {status === "processing" && <CircleNotch className="h-3 w-3 animate-spin" />}
      {TEXT[status] ?? label(status)}
    </span>
  );
}

export function LevelBadge({ level }: { level: string }) {
  return <span className="meta whitespace-nowrap text-xs text-ink-3">{label(level)}</span>;
}

export function ConfidenceBadge({ value }: { value: number }) {
  return <span className="meta tabular whitespace-nowrap text-xs text-ink-3" title="Extraction / detection confidence">{Math.round(value * 100)}% confidence</span>;
}
