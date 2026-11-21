"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowCounterClockwise, ArrowsClockwise, Check, CheckCircle, CheckSquare, FileText, GitDiff, PencilSimple, Plus, ShieldCheck, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import { ImpactPanel } from "@/components/impact-panel";
import { Badge, LevelBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, Tabs, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { Card, EmptyState, ErrorState, Field, Input, PageHeader, Select, Skeleton, Textarea } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { useProjectData, useSession } from "@/lib/session";
import type { Task, TaskStatus } from "@/lib/types";
import { formatDate, label } from "@/lib/utils";

const ORIGIN: Record<string, string> = {
  contradiction: "Unresolved contradiction", failed_check: "Failed requirement", needs_review: "Needs review",
  impact: "Ripple impact", deadline: "Upcoming deadline", manual: "Created manually",
};
const EMPTY: Record<TaskStatus, { title: string; text: string }> = {
  suggested: { title: "No suggestions waiting", text: "With Autopilot on, recommended steps are approved for you and appear under Active. Turn Autopilot off in Settings to approve each one yourself." },
  active: { title: "No active tasks", text: "When OxisTrack finds a failed requirement, an outdated document or an approaching deadline, the next step appears here." },
  completed: { title: "Nothing completed yet", text: "Tasks you mark as done are kept here." },
  dismissed: { title: "Nothing dismissed", text: "Suggestions you dismiss are kept here and will not be suggested again." },
};

function TaskDialog({ task, onClose, onDone }: { task: Task | "new"; onClose: () => void; onDone: () => void }) {
  const { project } = useSession();
  const existing = task === "new" ? null : task;
  const [f, setF] = React.useState({ title: existing?.title ?? "", description: existing?.description ?? "", priority: existing?.priority ?? "medium", due_date: existing?.due_date ?? "" });
  const [busy, setBusy] = React.useState(false);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={existing ? "Edit task" : "New task"}>
        <form className="space-y-4" onSubmit={async (e) => {
          e.preventDefault(); if (!project) return; setBusy(true);
          const body = { ...f, due_date: f.due_date || null };
          try {
            if (existing) await api(`/tasks/${existing.id}`, { method: "PATCH", json: body });
            else await api(`/projects/${project.id}/tasks`, { method: "POST", json: body });
            toast.success(existing ? "Task updated" : "Task created"); onDone(); onClose();
          } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
        }}>
          <Field label="Title"><Input autoFocus required maxLength={255} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Description"><Textarea maxLength={4000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Priority">
              <Select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value as Task["priority"] })}><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></Select>
            </Field>
            <Field label="Due date"><Input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></Field>
          </div>
          <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" loading={busy}>{existing ? "Save" : "Create task"}</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function ActionsPage() {
  const { project, refresh, canEdit } = useSession();
  const { data, error, isLoading, mutate } = useProjectData<Task[]>("/tasks");
  const [tab, setTab] = React.useState<TaskStatus | "impact">("active");
  const autopilot = !!project?.autopilot;
  const picked = React.useRef(false);
  const [priority, setPriority] = React.useState("all");
  const [origin, setOrigin] = React.useState("all");
  const [editing, setEditing] = React.useState<Task | "new" | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function patch(t: Task, body: Partial<Pick<Task, "status" | "priority">>, message: string) {
    try { await api(`/tasks/${t.id}`, { method: "PATCH", json: body }); toast.success(message); refresh(); }
    catch (e) { toast.error(errorMessage(e)); }
  }
  async function suggest() {
    if (!project) return; setBusy(true);
    try { const r = await api<{ created: number }>(`/projects/${project.id}/tasks/suggest`, { method: "POST" }); toast.success(r.created ? `${r.created} new suggestion${r.created === 1 ? "" : "s"}` : "Suggestions are up to date"); refresh(); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  }

  const all = data ?? [];
  React.useEffect(() => {  // open on whichever list has work waiting
    if (!data || picked.current) return;
    picked.current = true;
    if (!data.some((t) => t.status === "active") && data.some((t) => t.status === "suggested")) setTab("suggested");
  }, [data]);
  const count = (s: TaskStatus) => all.filter((t) => t.status === s).length;
  const origins = Array.from(new Set(all.map((t) => t.origin)));
  const list = all.filter((t) => t.status === tab && (priority === "all" || t.priority === priority) && (origin === "all" || t.origin === origin));

  return (
    <>
      <PageHeader title="Action Center">
        {canEdit && <><Button variant="secondary" onClick={suggest} loading={busy}><ArrowsClockwise /> Refresh suggestions</Button><Button onClick={() => setEditing("new")}><Plus /> New task</Button></>}
      </PageHeader>
      <Tabs value={tab} onValueChange={(v) => setTab(v as TaskStatus | "impact")}>
        <TabsList>
          {(["active", "suggested", "completed", "dismissed"] as TaskStatus[]).map((s) => (
            <TabsTrigger key={s} value={s}>{label(s)} <span className="tabular rounded-md bg-surface-3 px-1.5 text-[11px] leading-5 text-ink-2">{count(s)}</span></TabsTrigger>
          ))}
          <TabsTrigger value="impact">Impact reports</TabsTrigger>
        </TabsList>
      </Tabs>
      {tab === "impact" ? <ImpactPanel presetRequirement={null} /> : <>
      <div className="mb-4 flex flex-wrap gap-2">
        <Select value={priority} onChange={(e) => setPriority(e.target.value)} className="w-auto" aria-label="Filter by priority">
          <option value="all">All priorities</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
        </Select>
        <Select value={origin} onChange={(e) => setOrigin(e.target.value)} className="w-auto" aria-label="Filter by reason">
          <option value="all">All reasons</option>{origins.map((o) => <option key={o} value={o}>{ORIGIN[o] ?? label(o)}</option>)}
        </Select>
      </div>

      {error ? <ErrorState message={error.message} onRetry={() => mutate()} /> : isLoading || !data ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 w-full" />)}</div>
      ) : list.length === 0 ? (
        <Card><EmptyState icon={CheckSquare} title={count(tab as TaskStatus) ? "No tasks match these filters" : EMPTY[tab as TaskStatus].title} description={count(tab as TaskStatus) ? "Try clearing the priority or reason filter." : EMPTY[tab as TaskStatus].text} /></Card>
      ) : (
        <ul className="space-y-3">
          {list.map((t) => (
            <li key={t.id}>
              <Card className="p-4">
                <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
                  <div className="min-w-[220px] flex-1">
                    <h3 className={`text-base font-semibold ${t.status === "completed" ? "text-ink-3 line-through" : ""}`}>{t.title}</h3>
                    {t.description && <p className="mt-1 text-sm leading-relaxed text-ink-2">{t.description}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    {canEdit && t.status !== "completed" && t.status !== "dismissed" ? (
                      <Select value={t.priority} onChange={(e) => patch(t, { priority: e.target.value as Task["priority"] }, "Priority updated")} className="h-7 w-auto py-0 pl-2 text-xs" aria-label="Change priority">
                        <option value="high">High priority</option><option value="medium">Medium priority</option><option value="low">Low priority</option>
                      </Select>
                    ) : <LevelBadge level={t.priority} />}
                    <StatusBadge status={t.status} />
                  </div>
                </div>
                <details className="mt-3 text-sm">
                  <summary className="cursor-pointer select-none text-ink-3 transition-colors hover:text-ink">Why</summary>
                  <p className="mt-2 whitespace-pre-line leading-relaxed text-ink-3">{t.reason}</p>
                </details>
                <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-ink-3">
                  <Badge>{ORIGIN[t.origin] ?? label(t.origin)}</Badge>
                  {t.auto_approved && <Badge tone="brand">Approved by Autopilot</Badge>}
                  {t.related_document_id && <Link href={`/documents/${t.related_document_id}`} className="inline-flex items-center gap-1 hover:text-ink"><FileText className="h-3 w-3" />{t.related_document_name}</Link>}
                  {t.related_requirement_id && <Link href={`/verification?tab=requirements&focus=${t.related_requirement_id}`} className="inline-flex items-center gap-1 hover:text-ink"><ShieldCheck className="h-3 w-3" />{t.related_requirement_code}</Link>}
                  {t.related_contradiction_id && <Link href={`/verification?tab=contradictions&focus=${t.related_contradiction_id}`} className="inline-flex items-center gap-1 hover:text-ink"><GitDiff className="h-3 w-3" />{t.related_contradiction_code}</Link>}
                  {t.due_date && <span>Due {formatDate(t.due_date)}</span>}
                  <span>Created {formatDate(t.created_at)}</span>
                  {t.completed_at && <span>Completed {formatDate(t.completed_at)}</span>}
                  {canEdit && (
                    <span className="ml-auto flex flex-wrap gap-2">
                      {t.status === "suggested" && <>
                        <Button variant="ghost" size="sm" onClick={() => patch(t, { status: "dismissed" }, "Suggestion dismissed")}><X /> Dismiss</Button>
                        <Button variant="ghost" size="sm" onClick={() => setEditing(t)}><PencilSimple /> Edit</Button>
                        <Button size="sm" onClick={() => patch(t, { status: "active" }, "Task approved")}><Check /> Approve</Button>
                      </>}
                      {t.status === "active" && <>
                        <Button variant="ghost" size="sm" onClick={() => setEditing(t)}><PencilSimple /> Edit</Button>
                        <Button size="sm" onClick={() => patch(t, { status: "completed" }, "Task completed")}><CheckCircle /> Mark complete</Button>
                      </>}
                      {t.status === "completed" && <Button variant="ghost" size="sm" onClick={() => patch(t, { status: "active" }, "Task reopened")}><ArrowCounterClockwise /> Reopen</Button>}
                      {t.status === "dismissed" && <Button variant="ghost" size="sm" onClick={() => patch(t, { status: "suggested" }, "Moved back to suggestions")}><ArrowCounterClockwise /> Restore</Button>}
                    </span>
                  )}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      </>}
      {editing && <TaskDialog task={editing} onClose={() => setEditing(null)} onDone={refresh} />}
    </>
  );
}
