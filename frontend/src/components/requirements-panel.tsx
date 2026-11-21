"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowsClockwise, CaretDown, ClipboardText, FileText, Graph, ListChecks, MagicWand, PencilSimple, Play, Plus, Sparkle, Trash, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";
import { FileTypeIcon } from "@/components/file-icon";
import { UploadZone } from "@/components/upload-zone";
import { Badge, LevelBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog, DialogContent, Tip } from "@/components/ui/overlays";
import { Card, EmptyState, ErrorState, Field, Input, Select, Skeleton, Textarea } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { useProjectData, useSession } from "@/lib/session";
import type { Doc, Method, Requirement } from "@/lib/types";
import { cn, formatDate, label } from "@/lib/utils";

const METHOD: Record<Method, { name: string; help: string }> = {
  keyword: { name: "Keyword evidence", help: "Deterministic: looks for statements that reference this requirement and checks they do not say it is missing." },
  numeric: { name: "Numeric check", help: "Deterministic: finds the stated count in the deliverable and compares it with the expected value." },
  file_exists: { name: "File check", help: "Deterministic: checks that a deliverable file with the expected name was uploaded." },
  semantic: { name: "Semantic (AI)", help: "AI-assisted review. A pass is accepted only if the quoted evidence is found verbatim in the deliverable." },
  manual: { name: "Manual review", help: "Cannot be verified reliably by software. A person records the result." },
};
const POLARITY = { supports: { text: "Supports", cls: "border-ok/40 bg-ok-soft" }, contradicts: { text: "Contradicts", cls: "border-bad/40 bg-bad-soft" }, neutral: { text: "Related", cls: "border-line bg-bg/40" } };

function CompileDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => void }) {
  const { project } = useSession();
  const [source, setSource] = React.useState<"documents" | "text">("documents");
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!project) return;
    setBusy(true);
    try {
      const r = await api<{ created: Requirement[]; skipped_duplicates: number }>(`/projects/${project.id}/requirements/compile`, { method: "POST", json: { source, text: source === "text" ? text : null } });
      if (r.created.length) toast.success(`${r.created.length} requirement${r.created.length === 1 ? "" : "s"} compiled`, { description: r.skipped_duplicates ? `${r.skipped_duplicates} already existed and were skipped.` : undefined });
      else toast.info("No new requirements found", { description: r.skipped_duplicates ? "Everything found already exists." : "No requirement statements were detected." });
      onDone(); onOpenChange(false); setText("");
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent wide title="Compile requirements">
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2">
            {([["documents", "From analyzed documents", "Uses the requirement statements already extracted from this project's documents."],
              ["text", "From pasted instructions", "Paste an assignment brief, spec paragraph or checklist."]] as const).map(([id, title, help]) => (
              <button type="button" key={id} onClick={() => setSource(id)}
                className={cn("rounded-xl border p-3 text-left transition-colors", source === id ? "border-brand/50 bg-brand-soft" : "border-line hover:border-line-strong")}>
                <div className="text-base font-medium">{title}</div>
                <div className="mt-0.5 text-xs leading-relaxed text-ink-3">{help}</div>
              </button>
            ))}
          </div>
          {source === "text" ? (
            <Field label="Instructions">
              <Textarea required rows={6} maxLength={20000} value={text} onChange={(e) => setText(e.target.value)}
                placeholder="Create a website with a login system, a dashboard, a search feature, and a responsive mobile layout." />
            </Field>
          ) : (
            <p className="rounded-lg border border-line bg-bg/40 px-3 py-2.5 text-sm leading-relaxed text-ink-3">
              Conflicting requirements are held for review.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" loading={busy}><MagicWand /> Compile</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RequirementForm({ req, onClose, onDone }: { req: Requirement | "new"; onClose: () => void; onDone: () => void }) {
  const { project } = useSession();
  const existing = req === "new" ? null : req;
  const [f, setF] = React.useState({
    title: existing?.title ?? "", description: existing?.description ?? "", category: existing?.category ?? "functional",
    priority: existing?.priority ?? "medium", verification_method: existing?.verification_method ?? ("keyword" as Method),
    expected_value: existing?.expected_value ?? "", keywords: (existing?.keywords ?? []).join(", "),
  });
  const [busy, setBusy] = React.useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!project) return;
    setBusy(true);
    const kws = f.keywords.split(",").map((k) => k.trim()).filter(Boolean);
    const body = { ...f, expected_value: f.expected_value.trim() || null, keywords: kws.length ? kws : null };
    try {
      if (existing) await api(`/requirements/${existing.id}`, { method: "PATCH", json: body });
      else await api(`/projects/${project.id}/requirements`, { method: "POST", json: body });
      toast.success(existing ? `${existing.code} updated` : "Requirement added", { description: existing ? "Its previous check result was cleared; run verification again." : undefined });
      onDone(); onClose();
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent wide title={existing ? `Edit ${existing.code}` : "Add requirement"}>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Title"><Input required maxLength={255} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Password reset" /></Field>
          <Field label="Description"><Textarea maxLength={4000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="The application must let users reset their password by email." /></Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Category"><Input maxLength={40} value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} /></Field>
            <Field label="Priority">
              <Select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value as Requirement["priority"] })}>
                <option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
              </Select>
            </Field>
            <Field label="Verification method">
              <Select value={f.verification_method} onChange={(e) => setF({ ...f, verification_method: e.target.value as Method })}>
                {(Object.keys(METHOD) as Method[]).map((m) => <option key={m} value={m}>{METHOD[m].name}</option>)}
              </Select>
            </Field>
          </div>
          <p className="-mt-2 text-xs leading-relaxed text-ink-3">{METHOD[f.verification_method].help}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Search terms" hint="Comma-separated. Leave empty to derive them from the title.">
              <Input value={f.keywords} onChange={(e) => setF({ ...f, keywords: e.target.value })} placeholder="password reset, forgot password" />
            </Field>
            {f.verification_method === "numeric" && (
              <Field label="Expected value" hint="The number the deliverable must state."><Input required value={f.expected_value} onChange={(e) => setF({ ...f, expected_value: e.target.value })} placeholder="5" /></Field>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={busy}>{existing ? "Save changes" : "Add requirement"}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ReviewDialog({ req, onClose, onDone }: { req: Requirement; onClose: () => void; onDone: () => void }) {
  const [status, setStatus] = React.useState<"passed" | "failed">("passed");
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={`Manual review: ${req.code}`}>
        <form className="space-y-4" onSubmit={async (e) => {
          e.preventDefault(); setBusy(true);
          try { await api(`/requirements/${req.id}/review`, { method: "POST", json: { status, note } }); toast.success(`${req.code} marked ${status}`); onDone(); onClose(); }
          catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
        }}>
          <Field label="Result">
            <Select value={status} onChange={(e) => setStatus(e.target.value as "passed" | "failed")}><option value="passed">Passed</option><option value="failed">Failed</option></Select>
          </Field>
          <Field label="What did you check?"><Textarea required minLength={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reviewed the build on a phone with the design lead." /></Field>
          <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" loading={busy}>Record review</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Row({ r, open, onToggle, onEdit, onDelete, onReview, onRerun, focusRef }: {
  r: Requirement; open: boolean; onToggle: () => void; onEdit: () => void; onDelete: () => void; onReview: () => void; onRerun: () => void;
  focusRef?: React.Ref<HTMLLIElement>;
}) {
  const { canEdit } = useSession();
  const v = r.latest_validation;
  return (
    <li ref={focusRef} className="border-b border-line/70 last:border-0">
      <button onClick={onToggle} aria-expanded={open} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-surface-2/50">
        <span className="mt-0.5 w-[68px] shrink-0 font-mono text-xs text-ink-3">{r.code}</span>
        <span className="min-w-0 flex-1">
          <span className="block text-base font-medium text-ink">{r.title}</span>
          <span className="mt-0.5 block text-sm leading-relaxed text-ink-3">{r.description}</span>
          <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <Badge>{label(r.category)}</Badge>
            <Tip content={METHOD[r.verification_method].help}><span className="meta cursor-help text-xs text-ink-3"><span className="underline decoration-dotted underline-offset-2">{METHOD[r.verification_method].name}</span></span></Tip>
            <Badge>{label(r.priority)} priority</Badge>
          </span>
        </span>
        <StatusBadge status={r.status} className="mt-0.5" />
        <CaretDown className={cn("mt-1 h-4 w-4 shrink-0 text-ink-3 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-4 border-t border-line/70 bg-bg/30 px-4 py-4 sm:pl-[96px]">
          {r.blocked_by_contradiction_id && (
            <div className="flex items-start gap-2 text-sm text-ink-2">
              <Warning className="mt-0.5 h-4 w-4 shrink-0" />
              <span>The source documents disagree about this requirement. <Link className="font-medium text-ink underline underline-offset-2" href={`/verification?tab=contradictions&focus=${r.blocked_by_contradiction_id}`}>Resolve the contradiction</Link> and the confirmed value is applied here.</span>
            </div>
          )}
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-ink-3">Original source</dt>
              <dd className="mt-0.5 text-ink-2">
                {r.source_document_id ? <Link href={`/documents/${r.source_document_id}${r.source_fact_id ? `?fact=${r.source_fact_id}` : ""}`} className="inline-flex items-center gap-1.5 hover:text-ink"><FileText className="h-3 w-3" />{r.source_document_name}</Link>
                  : r.source_type === "text" ? "Pasted instructions" : "Added manually"}
                {r.source_text && <span className="mt-0.5 block text-ink-3">“{r.source_text}”</span>}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-3">{r.verification_method === "numeric" ? "Expected value" : "Search terms"}</dt>
              <dd className="mt-0.5 text-ink-2">{r.verification_method === "numeric" ? (r.expected_value ?? "Not set") : (r.keywords ?? []).join(", ") || "None"}</dd>
            </div>
          </dl>

          {v ? (
            <div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
                <span className="font-medium uppercase tracking-wider">Latest check</span><StatusBadge status={v.status} />
                <span>{METHOD[v.method].name} · {formatDate(v.created_at, true)}</span>
              </div>
              <p className="mt-2 text-sm text-ink-2"><span className="text-ink-3">What was checked:</span> {v.checked}</p>
              <p className="mt-1 text-sm text-ink"><span className="text-ink-3">Result:</span> {v.explanation}</p>
              {v.evidence.length > 0 ? (
                <ul className="mt-3 space-y-2">
                  {v.evidence.map((e) => (
                    <li key={e.id} className="border-l-2 border-line-strong pl-3">
                      <div className="text-sm leading-relaxed text-ink">“{e.snippet}”</div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-ink-3">
                        <span className="font-medium text-ink-2">{POLARITY[e.polarity].text}</span>
                        {e.document_id ? <Link href={`/documents/${e.document_id}`} className="hover:text-ink">{e.document_name}</Link> : e.document_name && <span>{e.document_name}</span>}
                        {e.location && <span>· {e.location}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : <p className="mt-2 text-xs text-ink-3">No evidence was found in the deliverable.</p>}
            </div>
          ) : <p className="text-sm text-ink-3">Not checked yet.</p>}

          {canEdit && (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" onClick={onRerun}><ArrowsClockwise /> Re-run check</Button>
              <Button variant="secondary" size="sm" onClick={onReview}><ClipboardText /> Record manual review</Button>
              <Button asChild variant="secondary" size="sm"><Link href={`/graph?tab=impact&requirement=${r.id}`}><Graph /> What if this changes?</Link></Button>
              <Button variant="ghost" size="sm" onClick={onEdit}><PencilSimple /> Edit</Button>
              <Button variant="ghost" size="sm" onClick={onDelete}><Trash /> Delete</Button>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function RequirementsPanel({ focus }: { focus: number | null }) {
  const { project, refresh, canEdit } = useSession();
  const reqs = useProjectData<Requirement[]>("/requirements");
  const docs = useProjectData<Doc[]>("/documents?kind=deliverable", { refreshInterval: (d) => (d?.some((x) => x.status === "queued" || x.status === "processing") ? 1200 : 0) });
  const [open, setOpen] = React.useState<number | null>(focus);
  const [compile, setCompile] = React.useState(false);
  const [editing, setEditing] = React.useState<Requirement | "new" | null>(null);
  const [reviewing, setReviewing] = React.useState<Requirement | null>(null);
  const [deleting, setDeleting] = React.useState<Requirement | null>(null);
  const [running, setRunning] = React.useState(false);
  const [sampleBusy, setSampleBusy] = React.useState(false);
  const [filter, setFilter] = React.useState("all");
  const focusRef = React.useRef<HTMLLIElement | null>(null);
  React.useEffect(() => { if (reqs.data && focus) { setOpen(focus); focusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }); } }, [reqs.data, focus]);

  async function verify(ids?: number[]) {
    if (!project) return;
    setRunning(true);
    try {
      const r = await api<{ passed: number; failed: number; needs_review: number; total: number }>(`/projects/${project.id}/verify`, { method: "POST", json: ids ? { requirement_ids: ids } : {} });
      toast.success(ids ? "Check finished" : "Verification finished", { description: `${r.passed} passed · ${r.failed} failed · ${r.needs_review} need review` });
      refresh();
    } catch (e) { toast.error(errorMessage(e)); } finally { setRunning(false); }
  }

  if (reqs.error) return <ErrorState message={reqs.error.message} onRetry={() => reqs.mutate()} />;
  if (reqs.isLoading || !reqs.data) return <div className="space-y-3"><Skeleton className="h-24 w-full" /><Skeleton className="h-64 w-full" /></div>;

  const all = reqs.data;
  const count = (s: string) => all.filter((r) => r.status === s).length;
  const deliverables = docs.data ?? [];
  const ready = deliverables.some((d) => d.status === "analyzed");
  const list = all.filter((r) => filter === "all" || r.status === filter);
  return (
    <div>
      <p className="tabular text-base text-ink-2">
        <span className="font-medium text-ink">{all.length} requirement{all.length === 1 ? "" : "s"}</span>
        {all.length > 0 && <>: {count("passed")} passed, <span className={count("failed") ? "font-medium text-ink" : ""}>{count("failed")} failed</span>, {count("needs_review")} need review, {count("not_checked")} not checked.</>}
        {all.length > 0 && <span className="text-ink-3"> {Math.round((count("passed") / all.length) * 100)}% verified as met.</span>}
      </p>

      <Card className="mt-6 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-base font-semibold">Deliverables</h3>
          </div>
          {project?.is_demo && canEdit && deliverables.length === 0 && (
            <Button variant="secondary" size="sm" loading={sampleBusy} onClick={async () => {
              setSampleBusy(true);
              try { await api(`/projects/${project.id}/demo/sample-deliverable`, { method: "POST" }); toast.success("Sample deliverable added", { description: "It intentionally misses some requirements." }); refresh(); }
              catch (e) { toast.error(errorMessage(e)); } finally { setSampleBusy(false); }
            }}><Sparkle /> Use the sample deliverable</Button>
          )}
        </div>
        {deliverables.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {deliverables.map((d) => (
              <li key={d.id} className="flex items-center gap-3 rounded-lg border border-line bg-bg/40 px-3 py-2">
                <FileTypeIcon type={d.file_type} className="h-7 w-9" />
                <Link href={`/documents/${d.id}`} className="min-w-0 flex-1 truncate text-base hover:underline">{d.filename}</Link>
                {d.is_sample && <Badge tone="brand">Sample data</Badge>}
                <StatusBadge status={d.status} />
              </li>
            ))}
          </ul>
        )}
        {canEdit && <div className="mt-3"><UploadZone compact kind="deliverable" hint="Drop a deliverable here, or click to browse" onUploaded={() => { void docs.mutate(); refresh(); }} /></div>}
      </Card>

      <div className="mb-3 mt-6 flex flex-wrap items-center gap-2">
        <h3 className="mr-auto text-base font-semibold">Requirements</h3>
        <Select value={filter} onChange={(e) => setFilter(e.target.value)} className="w-auto" aria-label="Filter requirements by status">
          <option value="all">All statuses</option><option value="passed">Passed</option><option value="failed">Failed</option><option value="needs_review">Needs review</option><option value="not_checked">Not checked</option>
        </Select>
        {canEdit && (
          <>
            <Button variant="secondary" onClick={() => setEditing("new")}><Plus /> Add</Button>
            <Button variant="secondary" onClick={() => setCompile(true)}><MagicWand /> Compile</Button>
            <Tip content={!all.length ? "Add or compile requirements first." : !ready ? "Upload a deliverable to check the requirements against." : "Check every requirement against the deliverables."}>
              <span><Button onClick={() => verify()} loading={running} disabled={!all.length || !ready}><Play /> Run verification</Button></span>
            </Tip>
          </>
        )}
      </div>

      {all.length === 0 ? (
        <Card><EmptyState icon={ListChecks} title="No requirements yet"
          description="Compile from documents or paste instructions.">
          {canEdit && <Button onClick={() => setCompile(true)}><MagicWand /> Compile requirements</Button>}
        </EmptyState></Card>
      ) : list.length === 0 ? <Card><p className="px-6 py-10 text-center text-base text-ink-3">No requirements have this status.</p></Card> : (
        <Card className="overflow-hidden">
          <ul>
            {list.map((r) => (
              <Row key={r.id} r={r} open={open === r.id} focusRef={r.id === focus ? focusRef : undefined}
                onToggle={() => setOpen(open === r.id ? null : r.id)} onEdit={() => setEditing(r)} onDelete={() => setDeleting(r)}
                onReview={() => setReviewing(r)} onRerun={() => (ready ? verify([r.id]) : toast.error("Upload a deliverable before running verification."))} />
            ))}
          </ul>
        </Card>
      )}

      <CompileDialog open={compile} onOpenChange={setCompile} onDone={refresh} />
      {editing && <RequirementForm req={editing} onClose={() => setEditing(null)} onDone={refresh} />}
      {reviewing && <ReviewDialog req={reviewing} onClose={() => setReviewing(null)} onDone={refresh} />}
      <ConfirmDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)} danger confirmLabel="Delete requirement"
        title={`Delete ${deleting?.code ?? ""}?`} description="Removes it and its history."
        onConfirm={async () => {
          if (!deleting) return;
          try { await api(`/requirements/${deleting.id}`, { method: "DELETE" }); toast.success(`${deleting.code} deleted`); refresh(); }
          catch (e) { toast.error(errorMessage(e)); }
        }} />
    </div>
  );
}
