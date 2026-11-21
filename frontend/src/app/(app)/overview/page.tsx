"use client";

import * as React from "react";
import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, Check, CheckSquare, FileText, GitDiff, Quotes, UploadSimple } from "@phosphor-icons/react";
import { EvidenceTimeline, KIND, ValueChange } from "@/components/timeline";
import { LevelBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger, Tip } from "@/components/ui/overlays";
import { Card, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useProjectData, useSession } from "@/lib/session";
import type { ImpactReport, Overview } from "@/lib/types";
import { cn, formatDate, timeAgo } from "@/lib/utils";
import { AnimatedNumber } from "@/components/skiper";

function HealthRing({ score }: { score: number }) {
  const color = score >= 85 ? "#2FBF8A" : score >= 60 ? "#F0A63A" : "#F0616D";
  return (
    <div role="img" aria-label={`Project health ${score} out of 100`} className="relative h-[84px] w-[84px] shrink-0 rounded-full"
      style={{ background: `conic-gradient(${color} ${score * 3.6}deg, #27272A 0deg)` }}>
      <div className="absolute inset-[7px] flex items-center justify-center rounded-full bg-surface text-xl font-semibold tabular"><AnimatedNumber value={score} /></div>
    </div>
  );
}

function Stat({ label, value, sub, href, tone }: { label: string; value: number; sub?: string; href: string; tone?: "bad" }) {
  return (
    <Link href={href} className="block px-5 py-4 transition-colors hover:bg-surface-2">
      <div className="text-sm text-ink-3">{label}</div>
      <div className={cn("mt-2 text-[28px] font-semibold leading-none tabular", tone === "bad" && value > 0 ? "text-bad" : "text-ink")}><AnimatedNumber value={value} /></div>
      {sub && <div className="mt-1.5 text-xs text-ink-3">{sub}</div>}
    </Link>
  );
}

const SEGMENTS = [
  { key: "requirements_passed", label: "Passed", color: "#2FBF8A" },
  { key: "requirements_failed", label: "Failed", color: "#F0616D" },
  { key: "requirements_needs_review", label: "Needs review", color: "#F0A63A" },
  { key: "requirements_not_checked", label: "Not checked", color: "#52525B" },
] as const;

function VerificationProgress({ m }: { m: Overview["metrics"] }) {
  const total = m.requirements_total;
  const checked = total - m.requirements_not_checked;
  return (
    <Card>
      <CardHeader title="Verification progress" description={total ? `${checked} of ${total} checked` : undefined}
        action={<Button asChild variant="ghost" size="sm"><Link href="/verification?tab=requirements">Open <ArrowRight /></Link></Button>} />
      <div className="px-5 pb-5 pt-4">
        {total === 0 ? (
          <p className="py-4 text-sm text-ink-3">No requirements yet.</p>
        ) : (
          <>
            <div className="flex items-baseline gap-2">
              <span className="text-[26px] font-semibold tabular leading-none">{Math.round((m.requirements_passed / total) * 100)}%</span>
              <span className="text-sm text-ink-3">met</span>
            </div>
            <div className="mt-4 flex h-2.5 gap-0.5 overflow-hidden rounded-full" role="img"
              aria-label={SEGMENTS.map((s) => `${m[s.key]} ${s.label}`).join(", ")}>
              {SEGMENTS.map((s) => m[s.key] > 0 && (
                <Tip key={s.key} content={`${s.label}: ${m[s.key]} of ${total}`}>
                  <div style={{ width: `${(m[s.key] / total) * 100}%`, background: s.color }} className="h-full first:rounded-l-full last:rounded-r-full" />
                </Tip>
              ))}
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
              {SEGMENTS.map((s) => (
                <div key={s.key}>
                  <dt className="flex items-center gap-1.5 text-xs text-ink-3"><span className="h-2 w-2 rounded-sm" style={{ background: s.color }} />{s.label}</dt>
                  <dd className="mt-0.5 text-base font-semibold tabular">{m[s.key]}</dd>
                </div>
              ))}
            </dl>
          </>
        )}
      </div>
    </Card>
  );
}

function ActivityChart({ data }: { data: Overview["document_activity"] }) {
  const total = data.reduce((n, d) => n + d.facts, 0);
  return (
    <Card>
      <CardHeader title="Document activity" description={`${total} facts · 14 days`} />
      <div className="h-[168px] px-3 pb-3 pt-4">
        {total === 0 ? <p className="px-2 py-4 text-sm text-ink-3">No activity yet.</p> : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }} barCategoryGap="28%">
              <CartesianGrid vertical={false} stroke="#27272A" />
              <XAxis dataKey="date" tickLine={false} axisLine={{ stroke: "#27272A" }} tick={{ fill: "#A1A1AA", fontSize: 11 }} interval={1}
                tickFormatter={(d: string) => new Date(d + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: "#A1A1AA", fontSize: 11 }} width={44} />
              <Tooltip cursor={{ fill: "#FFFFFF0F" }} content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload as Overview["document_activity"][number];
                return (
                  <div className="rounded-lg border border-line-strong bg-surface-3 px-3 py-2 text-xs shadow-pop">
                    <div className="font-medium text-ink">{formatDate(d.date)}</div>
                    <div className="mt-1 text-ink-2">{d.facts} facts extracted</div>
                    <div className="text-ink-3">{d.documents} document{d.documents === 1 ? "" : "s"} added</div>
                  </div>
                );
              }} />
              <Bar dataKey="facts" fill="#EDEDEF" radius={[4, 4, 0, 0]} maxBarSize={22} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}

function Walkthrough({ o }: { o: Overview }) {
  const reports = useProjectData<ImpactReport[]>("/impact-reports");
  const m = o.metrics;
  const auto = o.project.autopilot;
  const whatIfs = (reports.data ?? []).filter((r) => !r.source_of_change.includes("Autopilot")).length;
  const steps = [
    { done: m.documents_analyzed > 0, label: "Upload documents", href: "/documents" },
    { done: m.contradictions_total > 0 && m.open_contradictions === 0,
      label: auto ? "Review auto-resolved conflicts" : "Resolve a conflict", href: "/verification?tab=contradictions" },
    { done: m.deliverables > 0 && m.requirements_total > 0 && m.requirements_not_checked < m.requirements_total,
      label: "Add a deliverable", href: "/verification?tab=requirements" },
    { done: whatIfs > 0, label: "Run a what-if", href: "/graph?tab=impact" },
    { done: m.completed_tasks > 0, label: "Complete a task", href: "/actions" },
  ];
  const next = steps.findIndex((s) => !s.done);
  if (next === -1) return null;
  return (
    <Card className="mb-5 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold">{"Getting started"}</h3>
        <span className="ml-auto text-xs tabular text-ink-3">{steps.filter((s) => s.done).length} of {steps.length} done</span>
      </div>
      <ol className="mt-4 divide-y divide-line border-t border-line">
        {steps.map((s, i) => (
          <li key={s.label}>
            <Link href={s.href} className={cn("flex items-center gap-3 py-2.5 text-base transition-colors hover:text-ink", i === next ? "text-ink" : "text-ink-2")}>
              <span className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] tabular",
                s.done ? "border-ok bg-ok text-bg" : i === next ? "border-brand text-brand" : "border-line-strong text-ink-3")}>
                {s.done ? <Check className="h-3 w-3" /> : i + 1}
              </span>
              <span className={cn("flex-1", s.done && "text-ink-3 line-through decoration-ink-3/40")}>{s.label}</span>
              {i === next && <span className="flex items-center gap-1 text-xs text-brand-text">Next <ArrowRight className="h-3 w-3" /></span>}
            </Link>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function Summary() {
  const { data: o, error, isLoading, mutate } = useProjectData<Overview>("/overview");
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (isLoading || !o) {
    return <div className="space-y-5"><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div><Skeleton className="h-64" /></div>;
  }
  const m = o.metrics;
  if (m.documents_total === 0 && m.requirements_total === 0) {
    return (
      <Card>
        <EmptyState icon={UploadSimple} title="This project has no documents yet"
          description="Upload documents or open the sample.">
          <Button asChild><Link href="/documents"><UploadSimple /> Upload documents</Link></Button>
        </EmptyState>
      </Card>
    );
  }
  return (
    <div>
      <Walkthrough o={o} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,2fr)]">
        <Card className="p-5">
          <div className="text-sm text-ink-3">Project health</div>
          {o.health.score === null ? <p className="mt-3 text-sm text-ink-3">Analyze documents to see health.</p> : (
            <div className="mt-3 flex items-center gap-4">
              <HealthRing score={o.health.score} />
              <div className="min-w-0">
                <div className="text-lg font-semibold">{o.health.label}</div>
                <ul className="mt-1 space-y-0.5 text-sm text-ink-3">
                  {o.health.factors.length === 0 && <li>No open issues found.</li>}
                  {o.health.factors.map((f) => (
                    <li key={f.label} className="flex justify-between gap-3"><span>{f.label}</span>{f.impact !== 0 && <span className="tabular text-bad">{f.impact}</span>}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </Card>
        <Card className="grid grid-cols-2 divide-x divide-line overflow-hidden max-lg:[&>*:nth-child(-n+2)]:border-b max-lg:[&>*:nth-child(-n+2)]:border-line lg:grid-cols-4">
          <Stat label="Documents" value={m.documents_analyzed} sub={`of ${m.documents_total}`} href="/documents" />
          <Stat label="Facts" value={m.facts}  href="/documents" />
          <Stat label="Conflicts" value={m.open_contradictions} sub={`of ${m.contradictions_total}`} href="/verification?tab=contradictions" tone="bad" />
          <Stat label="Tasks" value={m.open_tasks} sub="open" href="/actions" />
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <VerificationProgress m={m} />
        <ActivityChart data={o.document_activity} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Recent contradictions" action={<Button asChild variant="ghost" size="sm"><Link href="/verification?tab=contradictions">View all <ArrowRight /></Link></Button>} />
          <div className="p-2 pt-3">
            {o.recent_contradictions.length === 0 && <p className="px-3 pb-3 text-sm text-ink-3">No conflicts.</p>}
            {o.recent_contradictions.map((c) => (
              <Link key={c.id} href={`/verification?tab=contradictions&focus=${c.id}`} className="flex items-start gap-3 rounded-lg px-3 py-2.5 hover:bg-surface-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-base text-ink">{c.title}</div>
                  <div className="mt-0.5 truncate text-xs text-ink-3">{c.sources.map((s) => s.value_text).filter((v, i, a) => a.indexOf(v) === i).join("  ·  ")}</div>
                </div>
                <LevelBadge level={c.severity} />
                <StatusBadge status={c.status} />
              </Link>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Next steps" description={o.project.autopilot ? "Recommended by OxisTrack and approved by Autopilot" : "Suggestions become tasks after you approve them"}
            action={<Button asChild variant="ghost" size="sm"><Link href="/actions">Open <ArrowRight /></Link></Button>} />
          <div className="p-2 pt-3">
            {o.suggested_tasks.length === 0 && <p className="px-3 pb-3 text-sm text-ink-3">Nothing needs doing right now.</p>}
            {o.suggested_tasks.map((t) => (
              <Link key={t.id} href="/actions" className="flex items-start gap-3 rounded-lg px-3 py-2.5 hover:bg-surface-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-base text-ink">{t.title}</div>
                  <div className="mt-0.5 truncate text-xs text-ink-3">{t.reason}</div>
                </div>
                <LevelBadge level={t.priority} />
              </Link>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Recent changes" action={<Button asChild variant="ghost" size="sm"><Link href="/overview?tab=timeline">Timeline <ArrowRight /></Link></Button>} />
          <div className="space-y-3 px-5 pb-5 pt-4">
            {o.recent_changes.length === 0 && <p className="text-sm text-ink-3">No changes recorded yet.</p>}
            {o.recent_changes.map((e) => (
              <div key={e.id} className="flex gap-3">
                <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", KIND[e.kind].dot)} />
                <div className="min-w-0">
                  <div className="text-sm text-ink">{e.title}</div>
                  <div className="text-xs text-ink-3">{KIND[e.kind].label} · {formatDate(e.event_date)}</div>
                  {e.kind === "confirmed_change" && <ValueChange previous={e.previous_value} next={e.new_value} />}
                </div>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Recent activity" />
          <div className="space-y-3 px-5 pb-5 pt-4">
            {o.recent_activity.map((a) => (
              <div key={a.id} className="flex items-baseline justify-between gap-4">
                <span className="min-w-0 truncate text-sm text-ink-2">{a.message}</span>
                <span className="shrink-0 text-xs text-ink-3">{timeAgo(a.created_at)}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function OverviewInner() {
  const { project } = useSession();
  const params = useSearchParams();
  const router = useRouter();
  const tab = params.get("tab") === "timeline" ? "timeline" : "summary";
  return (
    <>
      <PageHeader title={project?.name ?? "Overview"}  />
      <Tabs value={tab} onValueChange={(v) => router.replace(v === "summary" ? "/overview" : `/overview?tab=${v}`)}>
        <TabsList>
          <TabsTrigger value="summary">Summary</TabsTrigger>
          <TabsTrigger value="timeline">Evidence timeline</TabsTrigger>
        </TabsList>
        <TabsContent value="summary"><Summary /></TabsContent>
        <TabsContent value="timeline">
          <EvidenceTimeline />
        </TabsContent>
      </Tabs>
    </>
  );
}

export default function OverviewPage() {
  return <Suspense><OverviewInner /></Suspense>;
}
