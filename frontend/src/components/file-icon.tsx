import { cn } from "@/lib/utils";

export function FileTypeIcon({ type, className }: { type: string; className?: string }) {
  return (
    <span className={cn("inline-flex h-8 w-10 shrink-0 items-center justify-center rounded-md border border-line-strong bg-surface-2 font-mono text-[10px] font-medium uppercase text-ink-2", className)}>
      {type}
    </span>
  );
}
