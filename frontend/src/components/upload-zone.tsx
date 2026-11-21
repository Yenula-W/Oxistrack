"use client";

import * as React from "react";
import { CloudArrowUp } from "@phosphor-icons/react";
import { toast } from "sonner";
import { errorMessage, uploadFiles } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { UploadResult } from "@/lib/types";
import { cn } from "@/lib/utils";

const ALLOWED = ["pdf", "docx", "txt", "csv", "xlsx", "md", "markdown"];
const MAX_MB = 15;

export function UploadZone({ kind, onUploaded, compact, hint }: {
  kind: "source" | "deliverable"; onUploaded: () => void; compact?: boolean; hint?: string;
}) {
  const { project, canEdit } = useSession();
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [drag, setDrag] = React.useState(false);
  const [progress, setProgress] = React.useState<number | null>(null);
  const [problems, setProblems] = React.useState<string[]>([]);

  async function handle(list: FileList | File[]) {
    if (!project) return;
    const files = Array.from(list);
    const bad: string[] = [];
    const ok = files.filter((f) => {
      const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
      if (!ALLOWED.includes(ext)) { bad.push(`“${f.name}”: unsupported file type.`); return false; }
      if (f.size > MAX_MB * 1024 * 1024) { bad.push(`“${f.name}” is larger than ${MAX_MB} MB.`); return false; }
      if (f.size === 0) { bad.push(`“${f.name}” is empty.`); return false; }
      return true;
    });
    setProblems(bad);
    if (!ok.length) return;
    setProgress(0);
    try {
      const res = await uploadFiles<UploadResult>(`/projects/${project.id}/documents`, ok, kind, setProgress);
      const fresh = res.documents.length - res.unchanged.length;
      if (fresh > 0) toast.success(`${fresh} file${fresh === 1 ? "" : "s"} uploaded`, { description: "Analysis has started. Results appear as each file finishes." });
      if (res.unchanged.length) toast.info(`${res.unchanged.join(", ")} unchanged`, { description: "This exact file is already in the project." });
      setProblems([...bad, ...res.errors]);
      onUploaded();
    } catch (e) {
      setProblems([...bad, errorMessage(e)]);
    } finally {
      setProgress(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div>
      <div
        role="button" tabIndex={0} aria-disabled={!canEdit} aria-label="Upload files"
        onClick={() => canEdit && inputRef.current?.click()}
        onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && canEdit) { e.preventDefault(); inputRef.current?.click(); } }}
        onDragOver={(e) => { e.preventDefault(); if (canEdit) setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); if (canEdit) void handle(e.dataTransfer.files); }}
        className={cn("flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed text-center transition-colors",
          compact ? "px-4 py-5" : "px-6 py-9",
          drag ? "border-brand bg-brand-soft" : "border-line-strong bg-surface hover:border-brand/50 hover:bg-surface-2/60",
          !canEdit && "cursor-not-allowed opacity-60")}>
        <CloudArrowUp className={cn("text-brand", compact ? "h-5 w-5" : "h-7 w-7")} />
        <div className={cn("font-medium text-ink", compact ? "mt-2 text-sm" : "mt-3 text-base")}>
          {progress !== null ? `Uploading… ${Math.round(progress * 100)}%` : drag ? "Drop to upload" : hint ?? "Drag and drop files, or click to browse"}
        </div>
        <div className="mt-1 text-xs text-ink-3">PDF, DOCX, TXT, CSV, XLSX or Markdown · up to {MAX_MB} MB each</div>
        {progress !== null && (
          <div className="mt-3 h-1.5 w-56 max-w-full overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full rounded-full bg-brand transition-[width]" style={{ width: `${progress * 100}%` }} />
          </div>
        )}
        <input ref={inputRef} type="file" multiple hidden accept={ALLOWED.map((e) => `.${e}`).join(",")}
          onChange={(e) => e.target.files && void handle(e.target.files)} />
      </div>
      {problems.length > 0 && (
        <ul role="alert" className="mt-2 space-y-1 rounded-lg border border-bad/30 bg-bad-soft px-3 py-2 text-sm text-bad">
          {problems.map((p) => <li key={p}>{p}</li>)}
        </ul>
      )}
    </div>
  );
}
