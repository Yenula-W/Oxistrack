"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowsClockwise, FileText, GitDiff, ShieldCheck } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Badge, ConfidenceBadge, LevelBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/overlays";
import { Card, EmptyState, ErrorState, Field, Select, Skeleton, Textarea } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { useProjectData, useSession } from "@/lib/session";
import type { Contradiction, ContradictionSource } from "@/lib/types";
import { cn, formatDate, label } from "@/lib/utils";

const ROLE: Record<ContradictionSource["role"], { text: string; tone: "ok" | "neutral" | "bad" }> = {
  authoritative: { text: "Authoritative", tone: "ok" }, superseded: { text: "Superseded", tone: "neutral" },
  conflicting: { text: "Conflicting", tone: "bad" },
};

function ResolveDialog({ c, onClose, onDone }: { c: Contradiction; onClose: () => void; onDone: () => void }) {
  const [outcome, setOutcome] = React.useState<"resolved" | "superseded" | "under_review">("resolved");
  const [auth, setAuth] = React.useState<number | null>(null);
  const [superseded, setSuperseded] = React.useState<Set<number>>(new Set());
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const sources = c.sources.filter((s) => s.fact_id !== null);

  function pick(factId: number) {
    setAuth(factId);
    const chosen = sources.find((s) => s.fact_id === factId);
    setSuperseded(new Set(sources.filter((s) => s.value_text !== chosen?.value_text).map((s) => s.fact_id as number)));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api(`/contradictions/${c.id}/resolve`, { method: "PATCH", json: {
        status: outcome, note: note || null,
        authoritative_fact_id: outcome === "resolved" ? auth : null,
        superseded_fact_ids: outcome === "resolved" && auth ? Array.from(superseded) : null,
      } });
      toast.success(outcome === "resolved" ? `${c.code} resolved` : `${c.code} marked ${label(outcome).toLowerCase()}`);
      onDone();
      onClose();
    } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent wide title={`Resolve ${c.code}`}>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Outcome">
            <Select value={outcome} onChange={(e) => setOutcome(e.target.value as typeof outcome)}>
              <option value="resolved">Resolve: one source is authoritative</option>
              <option value="under_review">Keep under review</option>
              <option value="superseded">Mark the whole issue as superseded (no longer relevant)</option>
            </Select>
          </Field>
          {outcome === "resolved" && (
            <fieldset className="space-y-2">
              <legend className="mb-1.5 text-sm font-medium text-ink-2">Which source is authoritative?</legend>
              {sources.map((s) => (
                <div key={s.id} className={cn("rounded-xl border p-3 transition-colors", auth === s.fact_id ? "border-ok/50 bg-ok-soft" : "border-line")}>
                  <label className="flex cursor-pointer items-start gap-3">
                    <input type="radio" name="auth" className="mt-1 accent-[#EDEDEF]" checked={auth === s.fact_id} onChange={() => pick(s.fact_id as number)} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-base font-semibold text-ink">{s.value_text}</span>
                      <span className="block text-sm text-ink-2">“{s.statement}”</span>
                      <span className="block text-xs text-ink-3">{s.document_name}{s.document_date ? ` · dated ${formatDate(s.document_date)}` : ""}{s.location ? ` · ${s.location}` : ""}</span>
                    </span>
                  </label>
                  {auth !== null && auth !== s.fact_id && (
                    <label className="ml-7 mt-2 flex cursor-pointer items-center gap-2 text-xs text-ink-2">
                      <input type="checkbox" className="accent-[#EDEDEF]" checked={superseded.has(s.fact_id as number)}
                        onChange={(e) => { const n = new Set(superseded); if (e.target.checked) n.add(s.fact_id as number); else n.delete(s.fact_id as number); setSuperseded(n); }} />
                      Mark this statement as superseded
                    </label>
                  )}
                </div>
              ))}
            </fieldset>
          )}
          <Field label="Explanation" hint={outcome === "resolved" ? "Recorded with your name and the time in the evidence timeline." : outcome === "superseded" ? "Required: why is this issue no longer relevant?" : "Optional note for reviewers."}>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} required={outcome === "superseded"}
              placeholder={outcome === "resolved" ? "e.g. Confirmed with the client on the Nov 10 call." : ""} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={busy} disabled={outcome === "resolved" && auth === null && !note.trim()}>
              {outcome === "resolved" ? "Resolve contradiction" : "Save"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ContradictionsPanel({ focus }: { focus: number | null }) {
  const { project, refresh, canEdit } = useSession();
  const { data, error, isLoading, mutate } = useProjectData<Contradiction[]>("/contradictions");
  const [status, setStatus] = React.useState("all");
  const [category, setCategory] = React.useState("all");
  const [resolving, setResolving] = React.useState<Contradiction | null>(null);
  const [detecting, setDetecting] = React.useState(false);
  const focusRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => { if (data && focus) focusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [data, focus]);

  async function detect() {
    if (!project) return;
    setDetecting(true);
    try {
      const r = await api<{ created: number; updated: number; reopened: number; closed: number; resolved_by_autopilot?: number }>(`/projects/${project.id}/contradictions/detect`, { method: "POST" });
      toast.success("Detection finished", { description: `${r.created} new, ${r.updated} updated, ${r.reopened} reopened, ${r.closed} closed${r.resolved_by_autopilot ? `, ${r.resolved_by_autopilot} decided by Autopilot` : ""}.` });
      refresh();
    } catch (e) { toast.error(errorMessage(e)); } finally { setDetecting(false); }
  }
  async function setState(c: Contradiction, next: "open" | "under_review") {
    try { await api(`/contradictions/${c.id}/resolve`, { method: "PATCH", json: { status: next } }); toast.success(`${c.code} marked ${label(next).toLowerCase()}`); refresh(); }
    catch (e) { toast.error(errorMessage(e)); }
  }

  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (isLoading || !data) return <div className="space-y-3">{[0, 1].map((i) => <Skeleton key={i} className="h-56 w-full" />)}</div>;

  const cats = Array.from(new Set(data.map((c) => c.category)));
  const list = data.filter((c) => (status === "all" || c.status === status) && (category === "all" || c.category === category));

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-auto" aria-label="Filter by status">
          <option value="all">All statuses</option><option value="open">Open</option><option value="under_review">Under review</option><option value="resolved">Resolved</option><option value="superseded">Superseded</option>
        </Select>
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-auto" aria-label="Filter by category">
          <option value="all">All categories</option>{cats.map((c) => <option key={c} value={c}>{label(c)}</option>)}
        </Select>
        {canEdit && <Button variant="secondary" className="ml-auto" onClick={detect} loading={detecting}><ArrowsClockwise /> Re-run detection</Button>}
      </div>

      {data.length === 0 ? (
        <Card><EmptyState icon={ShieldCheck} title="No contradictions found" description="Your documents agree." /></Card>
      ) : list.length === 0 ? <Card><p className="px-6 py-10 text-center text-base text-ink-3">No contradictions match these filters.</p></Card> : (
        <div className="space-y-4">
          {list.map((c) => (
            <Card key={c.id} ref={c.id === focus ? focusRef : undefined} className={cn("p-5", c.id === focus && "ring-1 ring-brand/50")}>
              <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
                <div className="min-w-[220px] flex-1">
                  <h3 className="text-lg font-semibold leading-snug">{c.title}</h3>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-ink-3">{c.code}</span>
                    <StatusBadge status={c.status} />
                    {c.auto_resolved && <Badge>Decided by Autopilot</Badge>}
                    <LevelBadge level={c.severity} />
                    <Badge>{label(c.category)}</Badge>
                    <ConfidenceBadge value={c.confidence} />
                  </div>
                </div>
                {canEdit && (
                  <div className="flex gap-2">
                    {c.status === "open" && <Button variant="ghost" size="sm" onClick={() => setState(c, "under_review")}>Mark under review</Button>}
                    {(c.status === "open" || c.status === "under_review") && <Button size="sm" onClick={() => setResolving(c)}>Resolve…</Button>}
                    {(c.status === "resolved" || c.status === "superseded") && <Button variant="outline" size="sm" onClick={() => setState(c, "open")}>{c.auto_resolved ? "Overrule" : "Reopen"}</Button>}
                  </div>
                )}
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-line text-xs text-ink-3">
                      <th className="py-2 pr-4 font-normal">Value</th>
                      <th className="py-2 pr-4 font-normal">Source</th><th className="py-2 pr-4 font-normal">Dated</th>
                      {c.status === "resolved" && <th className="py-2 font-normal">Standing</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {c.sources.map((s) => (
                      <tr key={s.id} className={cn("border-b border-line/60 align-top", s.role === "superseded" && "text-ink-3")}>
                        <td className={cn("whitespace-nowrap py-2.5 pr-4 font-medium", s.role === "superseded" ? "line-through decoration-ink-3/60" : "text-ink")}>{s.value_text}</td>
                        <td className="py-2.5 pr-4">
                          {s.document_id && s.fact_id
                            ? <Link href={`/documents/${s.document_id}?fact=${s.fact_id}`} className="text-ink-2 underline decoration-line-strong underline-offset-2 hover:text-ink">{s.document_name}</Link>
                            : <span>{s.document_name} (removed)</span>}
                          <span className="block text-xs text-ink-3">{s.location ?? "Location unknown"}</span>
                        </td>
                        <td className="whitespace-nowrap py-2.5 pr-4 text-ink-3">{s.document_date ? formatDate(s.document_date) : "No date stated"}</td>
                        {c.status === "resolved" && <td className={cn("whitespace-nowrap py-2.5", s.role === "authoritative" ? "font-medium text-ink" : "text-ink-3")}>{ROLE[s.role].text}</td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <details className="group mt-3 text-sm">
                <summary className="cursor-pointer select-none text-ink-3 transition-colors hover:text-ink">
                  {(c.status === "resolved" || c.status === "superseded")
                    ? <>{label(c.status)}{c.resolved_by_name ? ` by ${c.resolved_by_name}` : ""}</>
                    : "Details"}
                </summary>
                <p className="mt-2 leading-relaxed text-ink-3">{c.explanation}</p>
                {c.resolution_note && (c.status === "resolved" || c.status === "superseded") && (
                  <p className="mt-2 leading-relaxed text-ink-3">{c.resolution_note}</p>
                )}
              </details>
              {(c.status === "under_review" || c.status === "open") && c.resolution_note && (
                <p className="mt-3 border-l-2 border-ink pl-3 text-sm text-ink-2">{c.resolution_note}</p>
              )}
            </Card>
          ))}
        </div>
      )}
      {resolving && <ResolveDialog c={resolving} onClose={() => setResolving(null)} onDone={refresh} />}
    </div>
  );
}
