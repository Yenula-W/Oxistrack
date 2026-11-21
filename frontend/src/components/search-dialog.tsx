"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { ArrowElbowDownLeft, CheckSquare, CircleNotch, FileText, GitDiff, Lightbulb, MagnifyingGlass, Quotes, ShieldCheck, Sparkle, Warning } from "@phosphor-icons/react";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Answer, SearchHit, SearchResults } from "@/lib/types";

const GROUPS: { key: keyof Omit<SearchResults, "query">; label: string; icon: React.ComponentType<{ className?: string }>; href: (h: SearchHit) => string }[] = [
  { key: "facts", label: "Extracted facts", icon: Quotes, href: (h) => `/documents/${h.document_id}?fact=${h.id}` },
  { key: "documents", label: "Documents", icon: FileText, href: (h) => `/documents/${h.id}` },
  { key: "contradictions", label: "Contradictions", icon: GitDiff, href: (h) => `/verification?tab=contradictions&focus=${h.id}` },
  { key: "requirements", label: "Requirements", icon: ShieldCheck, href: (h) => `/verification?tab=requirements&focus=${h.id}` },
  { key: "decisions", label: "Decisions", icon: Lightbulb, href: () => `/overview?tab=timeline` },
  { key: "tasks", label: "Tasks", icon: CheckSquare, href: () => `/actions` },
];
const EXAMPLES = ["What is the current project deadline, and which document confirms it?", "How many user roles are required?", "budget"];

export function SearchDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { project } = useSession();
  const router = useRouter();
  const [q, setQ] = React.useState("");
  const [results, setResults] = React.useState<SearchResults | null>(null);
  const [answer, setAnswer] = React.useState<Answer | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [asking, setAsking] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setAnswer(null);
    const term = q.trim();
    if (!project || term.length < 2) { setResults(null); return; }
    setSearching(true);
    const t = setTimeout(async () => {
      try {
        setResults(await api<SearchResults>(`/projects/${project.id}/search?q=${encodeURIComponent(term)}`));
        setError(null);
      } catch (e) { setError(errorMessage(e)); } finally { setSearching(false); }
    }, 220);
    return () => clearTimeout(t);
  }, [q, project]);

  React.useEffect(() => { if (!open) { setQ(""); setResults(null); setAnswer(null); setError(null); } }, [open]);

  async function ask(question = q) {
    if (!project || question.trim().length < 2) return;
    setAsking(true);
    try {
      setAnswer(await api<Answer>(`/projects/${project.id}/ask`, { method: "POST", json: { question: question.trim() } }));
      setError(null);
    } catch (e) { setError(errorMessage(e)); } finally { setAsking(false); }
  }

  const go = (href: string) => { onOpenChange(false); router.push(href); };
  const total = results ? GROUPS.reduce((n, g) => n + results[g.key].length, 0) : 0;

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 animate-fade-in bg-black/60 backdrop-blur-[2px]" />
        <DialogPrimitive.Content className="fixed left-1/2 top-[12vh] z-50 w-[calc(100vw-2rem)] max-w-2xl -translate-x-1/2 animate-fade-in overflow-hidden rounded-2xl border border-line-strong bg-surface shadow-pop">
          <DialogPrimitive.Title className="sr-only">Search project</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">Search documents, facts, requirements, contradictions, decisions and tasks, or ask a question.</DialogPrimitive.Description>
          <form onSubmit={(e) => { e.preventDefault(); void ask(); }} className="flex items-center gap-3 border-b border-line px-4">
            {searching ? <CircleNotch className="h-4 w-4 animate-spin text-ink-3" /> : <MagnifyingGlass className="h-4 w-4 text-ink-3" />}
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} maxLength={200}
              placeholder={`Search ${project?.name ?? "project"} or ask a question…`}
              className="h-12 flex-1 bg-transparent text-base text-ink placeholder:text-ink-3 focus:outline-none" />
            <button type="submit" disabled={q.trim().length < 2 || asking}
              className="flex items-center gap-1.5 rounded-md border border-line-strong px-2 py-1 text-xs text-ink-2 hover:bg-surface-2 disabled:opacity-40">
              {asking ? <CircleNotch className="h-3 w-3 animate-spin" /> : <Sparkle className="h-3 w-3 text-brand" />} Ask <ArrowElbowDownLeft className="h-3 w-3" />
            </button>
          </form>

          <div className="max-h-[60vh] overflow-y-auto p-2 scroll-thin">
            {error && <p className="m-2 rounded-lg border border-bad/30 bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}

            {answer && (
              <div className="m-2 rounded-xl border border-brand/30 bg-brand-soft p-4">
                <div className="mb-1.5 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-brand-text">
                  <Sparkle className="h-3 w-3" /> Answer from project documents
                  <span className="ml-auto normal-case tracking-normal text-ink-3">{answer.mode === "llm" ? "AI assistant" : "Built from extracted facts"}</span>
                </div>
                <p className="text-base leading-relaxed text-ink">{answer.answer}</p>
                {answer.uncertainty && (
                  <p className="mt-2 flex gap-1.5 text-sm leading-relaxed text-warn"><Warning className="mt-0.5 h-3.5 w-3.5 shrink-0" />{answer.uncertainty}</p>
                )}
                {answer.interpretation && <p className="mt-2 text-xs italic text-ink-3">Interpretation: {answer.interpretation}</p>}
                {answer.citations.length > 0 && (
                  <div className="mt-3 space-y-1.5">
                    <div className="text-[11px] font-medium uppercase tracking-wider text-ink-3">Sources</div>
                    {answer.citations.map((c) => (
                      <button key={c.fact_id} onClick={() => go(`/documents/${c.document_id}?fact=${c.fact_id}`)}
                        className="block w-full rounded-lg border border-line bg-bg/40 px-3 py-2 text-left hover:border-line-strong">
                        <div className="text-sm text-ink-2">“{c.text}”</div>
                        <div className="mt-0.5 text-xs text-ink-3">{c.document_name}{c.location ? ` · ${c.location}` : " · location unknown"}</div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {!results && !answer && (
              <div className="p-3">
                <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-ink-3">Try</div>
                {EXAMPLES.map((ex) => (
                  <button key={ex} onClick={() => { setQ(ex); if (ex.includes(" ")) void ask(ex); }}
                    className="block w-full rounded-lg px-2.5 py-2 text-left text-base text-ink-2 hover:bg-surface-2 hover:text-ink">{ex}</button>
                ))}
              </div>
            )}

            {results && total === 0 && !searching && !answer && (
              <p className="px-4 py-8 text-center text-base text-ink-3">No matches for “{results.query}”. Press Enter to ask it as a question.</p>
            )}

            {results && GROUPS.map((g) => results[g.key].length > 0 && (
              <div key={g.key} className="mb-1">
                <div className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wider text-ink-3">{g.label}</div>
                {results[g.key].map((h) => (
                  <button key={`${g.key}-${h.id}`} onClick={() => go(g.href(h))}
                    className="flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left hover:bg-surface-2">
                    <g.icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-3" />
                    <span className="min-w-0">
                      <span className="line-clamp-2 text-base text-ink">{h.title}</span>
                      <span className="block truncate text-xs text-ink-3">{h.subtitle}</span>
                    </span>
                  </button>
                ))}
              </div>
            ))}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
