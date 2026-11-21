"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as DropdownPrimitive from "@radix-ui/react-dropdown-menu";
import { X } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({ title, description, children, className, wide }: {
  title: string; description?: string; children: React.ReactNode; className?: string; wide?: boolean;
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 animate-fade-in bg-black/60 backdrop-blur-[2px]" />
      <DialogPrimitive.Content
        className={cn("fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 animate-pop-in overflow-y-auto rounded-2xl border border-line-strong bg-surface p-6 shadow-pop scroll-thin",
          wide ? "max-w-2xl" : "max-w-md", className)}>
        <div className="mb-4 pr-8">
          <DialogPrimitive.Title className="text-base font-semibold text-ink">{title}</DialogPrimitive.Title>
          {description ? <DialogPrimitive.Description className="mt-1 text-sm leading-relaxed text-ink-3">{description}</DialogPrimitive.Description>
            : <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>}
        </div>
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-md p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink" aria-label="Close">
          <X className="h-4 w-4" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = "Confirm", danger, onConfirm }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description: string; confirmLabel?: string; danger?: boolean;
  onConfirm: () => Promise<void> | void;
}) {
  const [busy, setBusy] = React.useState(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} description={description}>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant={danger ? "danger" : "primary"} loading={busy}
            onClick={async () => { setBusy(true); try { await onConfirm(); onOpenChange(false); } finally { setBusy(false); } }}>
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export const TooltipProvider = TooltipPrimitive.Provider;
export function Tip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <TooltipPrimitive.Root delayDuration={200}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content side={side} sideOffset={6}
          className="z-[60] max-w-xs animate-fade-in rounded-lg border border-line-strong bg-surface-3 px-2.5 py-1.5 text-xs leading-relaxed text-ink shadow-pop">
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;
export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("mb-5 flex gap-1 overflow-x-auto overflow-y-hidden [scrollbar-width:none] border-b border-line", className)} {...props} />;
}
export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn("-mb-px flex items-center gap-2 whitespace-nowrap border-b-2 border-transparent px-3 pb-2.5 pt-1 text-base font-medium text-ink-3 transition-colors hover:text-ink data-[state=active]:border-brand data-[state=active]:text-ink", className)}
      {...props} />
  );
}

export const Dropdown = DropdownPrimitive.Root;
export const DropdownTrigger = DropdownPrimitive.Trigger;
export function DropdownContent({ className, ...props }: React.ComponentProps<typeof DropdownPrimitive.Content>) {
  return (
    <DropdownPrimitive.Portal>
      <DropdownPrimitive.Content sideOffset={6} align="end"
        className={cn("z-50 min-w-[200px] animate-fade-in rounded-xl border border-line-strong bg-surface-2 p-1 shadow-pop", className)} {...props} />
    </DropdownPrimitive.Portal>
  );
}
export function DropdownItem({ className, ...props }: React.ComponentProps<typeof DropdownPrimitive.Item>) {
  return (
    <DropdownPrimitive.Item
      className={cn("flex cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-2 text-base text-ink-2 outline-none data-[highlighted]:bg-surface-3 data-[highlighted]:text-ink [&_svg]:size-4", className)}
      {...props} />
  );
}
export const DropdownSeparator = () => <DropdownPrimitive.Separator className="my-1 h-px bg-line" />;
export const DropdownLabel = ({ children }: { children: React.ReactNode }) => (
  <DropdownPrimitive.Label className="px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-ink-3">{children}</DropdownPrimitive.Label>
);
