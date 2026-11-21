"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowsClockwise, DownloadSimple, FileMagnifyingGlass, MagnifyingGlass, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";
import { FileTypeIcon } from "@/components/file-icon";
import { UploadZone } from "@/components/upload-zone";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Tip } from "@/components/ui/overlays";
import { Card, EmptyState, ErrorState, Input, PageHeader, Select, Skeleton } from "@/components/ui/primitives";
import { api, downloadFile, errorMessage, fetcher } from "@/lib/api";
import { useProjectData, useSession } from "@/lib/session";
import type { Doc, SampleFile } from "@/lib/types";
import { formatBytes, formatDate } from "@/lib/utils";
import useSWR from "swr";

const busy = (d: Doc) => d.status === "queued" || d.status === "processing";

export default function DocumentsPage() {
  const { refresh, canEdit } = useSession();
  const { data, error, isLoading, mutate } = useProjectData<Doc[]>("/documents", {
    refreshInterval: (docs) => (docs?.some(busy) ? 1200 : 0),
  });
  const samples = useSWR<SampleFile[]>("/demo/samples", fetcher, { revalidateOnFocus: false });
  const [q, setQ] = React.useState("");
  const [type, setType] = React.useState("all");
  const [status, setStatus] = React.useState("all");
  const [kind, setKind] = React.useState("all");
  const [toDelete, setToDelete] = React.useState<Doc | null>(null);

  // When analysis finishes, refresh everything derived from documents (contradictions, tasks, overview…).
  const wasBusy = React.useRef(false);
  React.useEffect(() => {
    const now = !!data?.some(busy);
    if (wasBusy.current && !now) refresh();
    wasBusy.current = now;
  }, [data, refresh]);

  const docs = (data ?? []).filter((d) =>
    (!q || d.filename.toLowerCase().includes(q.toLowerCase())) && (type === "all" || d.file_type === type) &&
    (status === "all" || d.status === status) && (kind === "all" || d.kind === kind));
  const types = Array.from(new Set((data ?? []).map((d) => d.file_type))).sort();

  async function reanalyze(d: Doc) {
    try { await api(`/documents/${d.id}/analyze`, { method: "POST" }); toast.success(`Re-analyzing ${d.filename}`); void mutate(); }
    catch (e) { toast.error(errorMessage(e)); }
  }

  return (
    <>
      <PageHeader title="Documents" />
      <UploadZone kind="source" onUploaded={() => mutate()} />

      {data && data.length === 0 && samples.data && (
        <Card className="mt-4 p-4">
          <div className="text-sm font-medium text-ink-2">Sample files</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {samples.data.filter((s) => s.kind === "source").map((s) => (
              <Button key={s.filename} variant="outline" size="sm" onClick={() => downloadFile(`/demo/samples/${encodeURIComponent(s.filename)}`, s.filename).catch((e) => toast.error(errorMessage(e)))}>
                <DownloadSimple /> {s.filename}
              </Button>
            ))}
          </div>
        </Card>
      )}

      <div className="mb-3 mt-6 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <MagnifyingGlass className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-3" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search documents" className="pl-9" aria-label="Search documents" />
        </div>
        <Select value={kind} onChange={(e) => setKind(e.target.value)} className="w-auto" aria-label="Filter by kind">
          <option value="all">All kinds</option><option value="source">Source documents</option><option value="deliverable">Deliverables</option>
        </Select>
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-auto" aria-label="Filter by file type">
          <option value="all">All types</option>{types.map((t) => <option key={t} value={t}>{t.toUpperCase()}</option>)}
        </Select>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-auto" aria-label="Filter by status">
          <option value="all">All statuses</option><option value="analyzed">Analyzed</option><option value="processing">Analyzing</option><option value="queued">Queued</option><option value="failed">Failed</option>
        </Select>
      </div>

      {error ? <ErrorState message={error.message} onRetry={() => mutate()} /> : isLoading || !data ? (
        <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}</div>
      ) : data.length === 0 ? (
        <Card><EmptyState icon={FileMagnifyingGlass} title="No documents yet" description="Drop files above to start." /></Card>
      ) : docs.length === 0 ? (
        <Card><p className="px-6 py-10 text-center text-base text-ink-3">No documents match these filters.</p></Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="hidden grid-cols-[minmax(0,1fr)_130px_90px_130px_84px] gap-4 border-b border-line px-4 py-2.5 text-xs font-medium text-ink-3 md:grid">
            <span>Document</span><span>Status</span><span className="text-right">Facts</span><span>Last modified</span><span />
          </div>
          <ul>
            {docs.map((d) => (
              <li key={d.id} className="grid grid-cols-1 items-center gap-x-4 gap-y-2 border-b border-line/70 px-4 py-3 last:border-0 hover:bg-surface-2/50 md:grid-cols-[minmax(0,1fr)_130px_90px_130px_84px]">
                <Link href={`/documents/${d.id}`} className="flex min-w-0 items-center gap-3">
                  <FileTypeIcon type={d.file_type} />
                  <span className="min-w-0">
                    <span className="block truncate text-base font-medium text-ink">{d.filename}</span>
                    <span className="flex flex-wrap items-center gap-x-2 text-xs text-ink-3">
                      {formatBytes(d.size_bytes)}
                      {d.current_version > 1 && <span>· version {d.current_version}</span>}
                      {d.kind === "deliverable" && <Badge tone="blue">Deliverable</Badge>}
                      {d.is_sample && <Badge tone="brand">Sample data</Badge>}
                    </span>
                  </span>
                </Link>
                <div className="flex items-center gap-2">
                  <StatusBadge status={d.status} />
                </div>
                <div className="tabular text-base text-ink-2 md:text-right">
                  <span className="text-ink-3 md:hidden">Facts: </span>{d.kind === "deliverable" ? "n/a" : d.status === "analyzed" ? d.fact_count : "…"}
                </div>
                <div className="text-sm text-ink-3">{formatDate(d.updated_at, true)}</div>
                <div className="flex justify-end gap-1">
                  {canEdit && (
                    <>
                      <Tip content="Re-run analysis"><Button variant="ghost" size="icon" disabled={busy(d)} onClick={() => reanalyze(d)} aria-label={`Re-analyze ${d.filename}`}><ArrowsClockwise /></Button></Tip>
                      <Tip content="Delete document"><Button variant="ghost" size="icon" onClick={() => setToDelete(d)} aria-label={`Delete ${d.filename}`}><Trash /></Button></Tip>
                    </>
                  )}
                </div>
                {d.status === "failed" && d.error && <p className="text-sm text-bad md:col-span-5" role="alert">{d.error}</p>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} danger confirmLabel="Delete document"
        title={`Delete ${toDelete?.filename ?? "document"}?`}
        description="Removes the file, its versions and facts. Cannot be undone."
        onConfirm={async () => {
          if (!toDelete) return;
          try { await api(`/documents/${toDelete.id}`, { method: "DELETE" }); toast.success(`${toDelete.filename} deleted`); refresh(); }
          catch (e) { toast.error(errorMessage(e)); }
        }} />
    </>
  );
}
