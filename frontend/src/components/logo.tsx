import { cn } from "@/lib/utils";

/** OxisTrack mark: the ox. */
export function LogoMark({ className }: { className?: string }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/logo.png" alt="" width={32} height={32} className={cn("h-8 w-8 rounded-lg grayscale", className)} />;
}

export function Logo({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      {!compact && <span className="font-heading text-lg font-bold tracking-[-0.02em] text-ink">OxisTrack</span>}
    </span>
  );
}
