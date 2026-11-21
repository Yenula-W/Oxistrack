"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, Broadcast, Check, CheckSquare, ClipboardText, FileText, GitDiff, Lightbulb, ShieldCheck, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/overlays";
import { Card, EmptyState, Field, Input, Select } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { useProjectData, useSession } from "@/lib/session";
import type { Fact, ImpactItem, ImpactReport, Requirement } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

const ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  document: FileText, deliverable: ClipboardText, requirement: ShieldCheck, contradiction: GitDiff, decision: Lightbulb, task: CheckSquare,
};
function hrefFor(i: ImpactItem): string {
  if (i.item_type === "document" || i.item_type === "deliverable") return `/documents/${i.item_ref}`;
  if (i.item_type === "requirement") return `/verification?tab=requirements&focus=${i.item_ref}`;
  if (i.item_type === "contradiction") return `/verification?tab=contradictions&focus=${i.item_ref}`;
  if (i.item_type === "task") return "/actions";
  return "/overview?tab=timeline";
}

function Items({ title, hint, items }: { title: string; hint: string; items: ImpactItem[] }) {
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <h4 className="text-base font-semibold">{title}</h4><span className="tabular text-xs text-ink-3">{items.length}</span>
      </div>
      <p className="mt-0.5 text-xs text-ink-3">{hint}</p>
      {items.length === 0 ? <p className="mt-3 text-sm text-ink-3">None found.</p> : (
        <ul className="mt-3 space-y-2">
          {items.map((i) => {
            const Icon = ICON[i.item_type] ?? FileText;
            return (
              <li key={i.id} className="rounded-xl border border-line bg-bg/40 p-3.5">
                <div className="flex items-start gap-2.5">
                  <Icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-3" />
                  <div className="min-w-0 flex-1">
                    <Link href={hrefFor(i)} className="text-base font-medium text-ink hover:underline">{i.label}</Link>
                    <p className="mt-1 text-sm leading-relaxed text-ink-2">{i.reason}</p>
                    <p className="mt-1.5 flex gap-1.5 text-sm text-ink"><ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand" />{i.recommended_action}</p>
                    <p className="mt-2 break-words font-mono text-[10.5px] leading-relaxed text-ink-3" title="Path through the knowledge graph">{i.path}</p>
                  </div>
                  <span className="tabular shrink-0 text-xs text-ink-3">{Math.round(i.confidence * 100)}%</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function ImpactPanel({ presetRequirement }: { presetRequirement: number | null }) {
  const { project, refresh, canEdit } = useSession();
  const reqs = useProjectData<Requirement[]>("/requirements");
  const facts = useProjectData<Fact[]>("/facts");
  const reports = useProjectData<ImpactReport[]>("/impact-reports");
  const [targetType, setTargetType] = React.useState<"requirement" | "fact">("requirement");
  const [targetId, setTargetId] = React.useState<string>("");
  const [newValue, setNewValue] = React.useState("");
  const [source, setSource] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [current, setCurrent] = React.useState<number | null>(null);
  const [confirm, setConfirm] = React.useState(false);

  const typedFacts = React.useMemo(() => (facts.data ?? []).filter((f) => ["date", "number", "money"].includes(f.value_type) && f.subject_key && f.subject_key !== "document date"), [facts.data]);
  const options = targetType === "requirement" ? (reqs.data ?? []).map((r) => ({ id: r.id, text: `${r.code} ${r.title}${r.expected_value ? ` (currently ${r.expected_value})` : ""}` }))
    : typedFacts.map((f) => ({ id: f.id, text: `${f.subject}: ${f.value_text} (${f.document_name})` }));

  React.useEffect(() => {
    if (presetRequirement && reqs.data?.some((r) => r.id === presetRequirement)) { setTargetType("requirement"); setTargetId(String(presetRequirement)); }
  }, [presetRequirement, reqs.data]);
  React.useEffect(() => {
    if (!options.some((o) => String(o.id) === targetId)) setTargetId(options[0] ? String(options[0].id) : "");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetType, reqs.data, facts.data]);
  React.useEffect(() => { if (current === null && reports.data?.[0]) setCurrent(reports.data[0].id); }, [reports.data, current]);

  const report = reports.data?.find((r) => r.id === current) ?? null;

  async function analyze(e: React.FormEvent) {
    e.preventDefault();
    if (!project || !targetId) return;
    setBusy(true);
    try {
      const r = await api<ImpactReport>(`/projects/${project.id}/impact-analysis`, { method: "POST",
        json: { target_type: targetType, target_id: Number(targetId), new_value: newValue, source_of_change: source || null } });
      await reports.mutate();
      setCurrent(r.id);
      toast.success("Impact report ready", { description: `${r.items.length} connected item${r.items.length === 1 ? "" : "s"} found. Nothing has been changed.` });
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
  }
  async function act(kind: "apply" | "discard") {
    if (!report) return;
    try {
      await api(`/impact-reports/${report.id}/${kind}`, { method: "POST" });
      toast.success(kind === "apply" ? "Change applied" : "Report discarded", { description: kind === "apply" ? "The requirement was updated and follow-up tasks were suggested in the Action Center." : undefined });
      refresh();
    } catch (err) { toast.error(errorMessage(err)); }
  }

  const noTargets = reqs.data && facts.data && !reqs.data.length && !typedFacts.length;
  if (noTargets) {
    return <Card><EmptyState icon={Broadcast} title="Nothing to analyze yet" description="Analyze documents first." /></Card>;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
      <div className="space-y-4">
        <Card className="p-4">
          <h3 className="text-base font-semibold">What if something changes?</h3>
          <form onSubmit={analyze} className="mt-4 space-y-3.5">
            <Field label="What is changing?">
              <Select value={targetType} onChange={(e) => setTargetType(e.target.value as "requirement" | "fact")}>
                <option value="requirement">A requirement</option><option value="fact">A fact stated in a document</option>
              </Select>
            </Field>
            <Field label={targetType === "requirement" ? "Requirement" : "Fact"}>
              <Select required value={targetId} onChange={(e) => setTargetId(e.target.value)}>
                {options.length === 0 && <option value="">None available</option>}
                {options.map((o) => <option key={o.id} value={o.id}>{o.text}</option>)}
              </Select>
            </Field>
            <Field label="New value"><Input required maxLength={300} value={newValue} onChange={(e) => setNewValue(e.target.value)} placeholder="e.g. 7, or January 15" /></Field>
            <Field label="Source of the change" hint="Optional: who or what asked for it."><Input maxLength={255} value={source} onChange={(e) => setSource(e.target.value)} placeholder="Client email, Nov 12" /></Field>
            <Button type="submit" className="w-full" loading={busy} disabled={!targetId || !canEdit}><Broadcast /> Analyze impact</Button>
          </form>
        </Card>
        {(reports.data?.length ?? 0) > 0 && (
          <Card className="p-2">
            <div className="px-2 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wider text-ink-3">Previous reports</div>
            {reports.data?.map((r) => (
              <button key={r.id} onClick={() => setCurrent(r.id)} className={cn("flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left hover:bg-surface-2", r.id === current && "bg-surface-2")}>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink">{r.target_label} → {r.new_value}</span>
                  <span className="block text-xs text-ink-3">{formatDate(r.created_at, true)}</span>
                </span>
                <StatusBadge status={r.status} />
              </button>
            ))}
          </Card>
        )}
      </div>

      {!report ? (
        <Card><EmptyState icon={Broadcast} title="No impact report yet" description="Run an analysis." /></Card>
      ) : (
        <Card className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2"><h3 className="text-lg font-semibold">Impact report</h3><StatusBadge status={report.status} /></div>
              <p className="mt-0.5 text-xs text-ink-3">{formatDate(report.created_at, true)} · Source of change: {report.source_of_change}</p>
            </div>
            {report.status === "draft" && canEdit && (
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={() => act("discard")}><Trash /> Discard</Button>
                <Button size="sm" onClick={() => setConfirm(true)}><Check /> Approve change</Button>
              </div>
            )}
          </div>
          <div className="mt-4 grid gap-3 rounded-xl border border-line bg-bg/40 p-4 sm:grid-cols-[1fr_auto_1fr_auto] sm:items-center">
            <div><div className="text-xs text-ink-3">Changed information</div><div className="mt-0.5 text-base font-medium">{report.target_label}</div></div>
            <div className="hidden h-8 w-px bg-line sm:block" />
            <div className="flex flex-wrap items-center gap-2 text-base">
              <span><span className="block text-xs text-ink-3">Previous value</span><span className="text-ink-2 line-through decoration-ink-3/50">{report.previous_value ?? "Not set"}</span></span>
              <ArrowRight className="mt-4 h-4 w-4 text-ink-3" />
              <span><span className="block text-xs text-ink-3">New value</span><span className="font-semibold text-ink">{report.new_value}</span></span>
            </div>
            <div><div className="text-xs text-ink-3">Confidence</div><div className="mt-0.5 text-base font-medium tabular">{Math.round(report.confidence * 100)}%</div></div>
          </div>
          <p className="mt-4 text-sm leading-relaxed text-ink-2">{report.summary}</p>
          {report.status === "applied" && <p className="mt-3 rounded-lg border border-ok/30 bg-ok-soft px-3 py-2 text-sm text-ink-2">Applied {formatDate(report.applied_at, true)}. Follow-up tasks are waiting for approval in the <Link href="/actions" className="font-medium text-ink underline underline-offset-2">Action Center</Link>.</p>}
          <div className="mt-6 grid gap-6 xl:grid-cols-2">
            <Items title="Directly affected" hint="State or depend on this exact value." items={report.items.filter((i) => i.level === "direct")} />
            <Items title="Indirectly affected" hint="Reached through statements that mention this topic; less certain." items={report.items.filter((i) => i.level === "indirect")} />
          </div>
          <div className="mt-5"><Badge>Uncertainty</Badge><span className="ml-2 text-xs text-ink-3">Impact is inferred from graph relationships. Items with lower confidence are further from the change and should be checked by a person.</span></div>
        </Card>
      )}
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} confirmLabel="Approve and apply" title="Approve this change?"
        description={`${report?.target_label ?? "The item"} will be updated to “${report?.new_value ?? ""}”, its verification result will be cleared, the decision will be recorded in the timeline, and follow-up tasks will be suggested. Your documents are never rewritten.`}
        onConfirm={() => act("apply")} />
    </div>
  );
}
