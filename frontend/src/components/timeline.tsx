"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle, ClockCounterClockwise, FileText, GitDiff, Info, Prohibit, Quotes } from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { Tip } from "@/components/ui/overlays";
import { Card, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useProjectData } from "@/lib/session";
import type { TimelineEvent } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

export const KIND = {
  statement: { label: "Source statement", icon: Quotes, tone: "blue", dot: "bg-ink-3" },
  disagreement: { label: "Unresolved disagreement", icon: GitDiff, tone: "bad", dot: "bg-bad" },
  confirmed_change: { label: "Confirmed change", icon: CheckCircle, tone: "ok", dot: "bg-ok" },
  superseded: { label: "Superseded source", icon: Prohibit, tone: "neutral", dot: "bg-ink-3" },
  info: { label: "Activity", icon: Info, tone: "neutral", dot: "bg-line-strong" },
} as const;

export function ValueChange({ previous, next }: { previous: string | null; next: string | null }) {
  if (!previous && !next) return null;
  return (
    <div className="mt-2 inline-flex flex-wrap items-center gap-2 rounded-lg border border-line bg-bg/50 px-2.5 py-1.5 text-sm">
      {previous && <span className="text-ink-3 line-through decoration-ink-3/50">{previous}</span>}
      {previous && next && <ArrowRight className="h-3.5 w-3.5 text-ink-3" />}
      {next && <span className="font-medium text-ink">{next}</span>}
    </div>
  );
}

export function EvidenceTimeline() {
  const { data, error, isLoading, mutate } = useProjectData<TimelineEvent[]>("/timeline");
  const [filter, setFilter] = React.useState<string>("evidence");
  const [newestFirst, setNewestFirst] = React.useState(false);

  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (isLoading || !data) return <div className="space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20 w-full" />)}</div>;
  if (!data.length) {
    return <Card><EmptyState icon={ClockCounterClockwise} title="No history yet" description="Changes show up here." /></Card>;
  }
  const filtered = data.filter((e) => (filter === "all" ? true : filter === "evidence" ? e.kind !== "info" : e.kind === filter));
  const events = newestFirst ? filtered : [...filtered].reverse();
  const chips = [
    { id: "evidence", label: "Evidence" }, { id: "statement", label: "Statements" }, { id: "disagreement", label: "Disagreements" },
    { id: "confirmed_change", label: "Confirmed changes" }, { id: "superseded", label: "Superseded" }, { id: "all", label: "Everything" },
  ];
  return (
    <div>
      <div className="mb-5 flex flex-wrap gap-1.5" role="tablist" aria-label="Filter timeline">
        {chips.map((c) => (
          <button key={c.id} role="tab" aria-selected={filter === c.id} onClick={() => setFilter(c.id)}
            className={cn("h-7 rounded-full border px-3 text-xs font-medium transition-colors",
              filter === c.id ? "border-brand/40 bg-brand-soft text-ink" : "border-line text-ink-3 hover:text-ink")}>
            {c.label}
          </button>
        ))}
        <button onClick={() => setNewestFirst(!newestFirst)} className="ml-auto h-7 rounded-full border border-line px-3 text-xs font-medium text-ink-3 hover:text-ink">
          {newestFirst ? "Newest first" : "Oldest first"}
        </button>
      </div>
      {!events.length && <p className="py-10 text-center text-base text-ink-3">No events of this kind yet.</p>}
      <ol className="relative ml-2 space-y-4 border-l border-line pl-6">
        {events.map((e) => {
          const k = KIND[e.kind];
          return (
            <li key={e.id} className="relative">
              <span className={cn("absolute -left-[30px] top-4 h-2.5 w-2.5 rounded-full ring-4 ring-bg", k.dot)} />
              <Card className="p-4">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  <Badge tone={k.tone} icon={k.icon}>{k.label}</Badge>
                  <Tip content={e.date_source === "document" ? "Date stated inside the source document." : "Date this was recorded in OxisTrack."}>
                    <span className="tabular cursor-help text-xs text-ink-3">
                      {formatDate(e.event_date, e.date_source === "system")}{e.date_source === "document" ? " · document date" : ""}
                    </span>
                  </Tip>
                </div>
                <div className="mt-2 text-base font-medium text-ink">{e.title}</div>
                {e.description && <p className="mt-1 text-sm leading-relaxed text-ink-3">{e.description}</p>}
                <ValueChange previous={e.previous_value} next={e.new_value} />
                {e.resolution && <p className="mt-2 text-sm text-ink-2"><span className="text-ink-3">Resolution:</span> {e.resolution}</p>}
                <div className="mt-2.5 flex flex-wrap items-center gap-3 text-xs text-ink-3">
                  {e.source && (e.document_id
                    ? <Link href={`/documents/${e.document_id}`} className="inline-flex items-center gap-1 hover:text-ink"><FileText className="h-3 w-3" />{e.source}</Link>
                    : <span>Source: {e.source}</span>)}
                  {e.contradiction_id && <Link href={`/verification?tab=contradictions&focus=${e.contradiction_id}`} className="hover:text-ink">View contradiction</Link>}
                </div>
              </Card>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
