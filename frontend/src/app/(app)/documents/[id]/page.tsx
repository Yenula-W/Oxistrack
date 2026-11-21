"use client";

import * as React from "react";
import { Suspense } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { ArrowLeft, Graph, Quotes } from "@phosphor-icons/react";
import { FileTypeIcon } from "@/components/file-icon";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Tip } from "@/components/ui/overlays";
import { Card, EmptyState, ErrorState, Select, Skeleton } from "@/components/ui/primitives";
import { fetcher } from "@/lib/api";
import type { DocDetail, Fact } from "@/lib/types";
import { cn, formatBytes, formatDate, label } from "@/lib/utils";

const CATEGORY_TONE: Record<string, "bad" | "warn" | "ok" | "brand" | "blue" | "neutral"> = {
  deadline: "bad", date: "neutral", requirement: "brand", decision: "ok", goal: "blue", budget: "warn", quantity: "blue",
  technical_spec: "blue", constraint: "warn", dependency: "brand", entity: "neutral", statement: "neutral",
};

function DocumentInner() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const focusFact = Number(params.get("fact")) || null;
  const { data: doc, error, mutate } = useSWR<DocDetail>(`/documents/${id}`, fetcher, {
    revalidateOnFocus: false, refreshInterval: (d) => (d && (d.status === "queued" || d.status === "processing") ? 1200 : 0),
  });
  const [category, setCategory] = React.useState("all");
  const [active, setActive] = React.useState<number | null>(null); // segment index
  const segRefs = React.useRef<Record<number, HTMLDivElement | null>>({});

  const jump = React.useCallback((f: Fact) => {
    if (f.segment_index === null) return;
    setActive(f.segment_index);
    segRefs.current[f.segment_index]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  React.useEffect(() => {
    if (!doc || !focusFact) return;
    const f = doc.facts.find((x) => x.id === focusFact);
    if (f) setTimeout(() => jump(f), 80);
  }, [doc, focusFact, jump]);

  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!doc) return <div className="space-y-4"><Skeleton className="h-10 w-80" /><Skeleton className="h-96 w-full" /></div>;

  const factsBySeg = new Map<number, Fact[]>();
  doc.facts.forEach((f) => { if (f.segment_index !== null) factsBySeg.set(f.segment_index, [...(factsBySeg.get(f.segment_index) ?? []), f]); });
  const cats = Array.from(new Set(doc.facts.map((f) => f.category)));
  const facts = doc.facts.filter((f) => category === "all" || f.category === category);

  return (
    <>
      <Link href="/documents" className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink"><ArrowLeft className="h-3.5 w-3.5" /> Documents</Link>
      <div className="mb-6 flex flex-wrap items-start gap-3">
        <FileTypeIcon type={doc.file_type} className="mt-0.5" />
        <div className="min-w-0 flex-1">
          <h1 className="break-words text-xl font-semibold tracking-tight">{doc.filename}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-ink-3">
            <StatusBadge status={doc.status} />
            {doc.kind === "deliverable" && <Badge tone="blue">Deliverable</Badge>}
            {doc.is_sample && <Badge tone="brand">Sample data</Badge>}
            <span>{formatBytes(doc.size_bytes)}</span>
            <span>Version {doc.current_version}</span>
            <span>Uploaded {formatDate(doc.created_at, true)}</span>
            {doc.document_date && <Tip content="Date stated inside the document."><span className="cursor-help">Dated {formatDate(doc.document_date)}</span></Tip>}
          </div>
        </div>
      </div>

      {doc.status === "failed" && <div role="alert" className="mb-5 rounded-xl border border-bad/30 bg-bad-soft px-4 py-3 text-base text-bad">{doc.error ?? "This document could not be analyzed."}</div>}
      {(doc.status === "queued" || doc.status === "processing") && (
        <Card className="mb-5 flex items-center gap-3 px-4 py-3 text-base text-ink-2"><span className="h-2 w-2 animate-pulse rounded-full bg-ink-3" /> Reading the document and extracting facts…</Card>
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <section aria-label="Extracted facts">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold">{doc.kind === "deliverable" ? "Extracted facts" : `Extracted facts (${doc.facts.length})`}</h2>
            {cats.length > 1 && (
              <Select value={category} onChange={(e) => setCategory(e.target.value)} className="h-8 w-auto text-sm" aria-label="Filter facts by category">
                <option value="all">All categories</option>{cats.map((c) => <option key={c} value={c}>{label(c)}</option>)}
              </Select>
            )}
          </div>
          {doc.kind === "deliverable" ? (
            <Card><EmptyState icon={Quotes} title="Deliverables are checked, not mined" description="Used as evidence for requirements." /></Card>
          ) : facts.length === 0 && doc.status === "analyzed" ? (
            <Card><EmptyState icon={Quotes} title="No facts found" description="Nothing trackable in this file." /></Card>
          ) : (
            <ul className="space-y-2">
              {facts.map((f) => (
                <li key={f.id}>
                  <button onClick={() => jump(f)} className={cn("w-full rounded-xl border bg-surface p-3.5 text-left transition-colors hover:border-line-strong",
                    active !== null && active === f.segment_index ? "border-brand/50" : "border-line")}>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={CATEGORY_TONE[f.category] ?? "neutral"}>{label(f.category)}</Badge>
                      {f.value_text && f.value_type !== "presence" && f.value_type !== "text" && <span className="text-sm font-medium text-ink">{f.value_text}</span>}
                      <span className="ml-auto tabular text-xs text-ink-3">{Math.round(f.confidence * 100)}%</span>
                    </div>
                    <p className="mt-2 text-base leading-relaxed text-ink">{f.text}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-3">
                      <span>{f.location ?? "Location unknown"}</span>
                      {f.subject && <span>Subject: {f.subject}</span>}
                      <span>{f.extractor === "llm" ? "AI extraction (quote verified)" : "Rule-based extraction"}</span>
                      <span>{formatDate(f.created_at, true)}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {doc.versions.length > 1 && (
            <Card className="mt-5 p-4">
              <h3 className="text-base font-semibold">Version history</h3>
              <ul className="mt-2 space-y-1.5 text-sm text-ink-2">
                {[...doc.versions].reverse().map((v) => (
                  <li key={v.version} className="flex justify-between gap-3">
                    <span>Version {v.version}{v.version === doc.current_version ? " (current)" : ""}</span>
                    <span className="text-ink-3">{formatDate(v.created_at, true)} · {formatBytes(v.size_bytes)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </section>

        <section aria-label="Document content" className="lg:sticky lg:top-0 lg:self-start">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-semibold">Document content</h2>
            <Link href="/graph" className="inline-flex items-center gap-1.5 text-xs text-ink-3 hover:text-ink"><Graph className="h-3.5 w-3.5" /> View in knowledge graph</Link>
          </div>
          <Card className="max-h-[70vh] overflow-y-auto p-2 scroll-thin">
            {doc.segments.length === 0 && <p className="px-3 py-8 text-center text-sm text-ink-3">No extracted text is available for this document.</p>}
            {doc.segments.map((s, i) => {
              const has = factsBySeg.has(i);
              return (
                <div key={i} ref={(el) => { segRefs.current[i] = el; }}
                  className={cn("flex gap-3 rounded-lg px-3 py-1.5 transition-colors", active === i ? "bg-brand-soft ring-1 ring-brand/40" : has && "bg-surface-2/60")}>
                  <span className="w-20 shrink-0 pt-0.5 font-mono text-[10.5px] text-ink-3">{s.location ?? ""}</span>
                  <span className={cn("text-base leading-relaxed", has ? "text-ink" : "text-ink-3")}>{s.text}</span>
                </div>
              );
            })}
          </Card>
        </section>
      </div>
    </>
  );
}

export default function DocumentPage() {
  return <Suspense><DocumentInner /></Suspense>;
}
