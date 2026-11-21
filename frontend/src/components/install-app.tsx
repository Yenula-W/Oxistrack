"use client";

import * as React from "react";
import { DownloadSimple } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };

/** Tracks whether the browser is offering to install OxisTrack, and whether it is already running installed. */
export function useInstall() {
  const [event, setEvent] = React.useState<InstallEvent | null>(null);
  const [installed, setInstalled] = React.useState(false);

  React.useEffect(() => {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    setInstalled(window.matchMedia("(display-mode: standalone)").matches);
    const onPrompt = (e: Event) => { e.preventDefault(); setEvent(e as InstallEvent); };
    const onInstalled = () => { setInstalled(true); setEvent(null); toast.success("OxisTrack is installed"); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => { window.removeEventListener("beforeinstallprompt", onPrompt); window.removeEventListener("appinstalled", onInstalled); };
  }, []);

  const install = React.useCallback(async () => {
    if (!event) return;
    await event.prompt();
    const choice = await event.userChoice;
    if (choice.outcome === "accepted") setEvent(null);
  }, [event]);

  return { canInstall: !!event && !installed, installed, install };
}

/** Shown only when the browser can install the app right now. */
export function InstallButton({ className, variant = "secondary" }: { className?: string; variant?: "secondary" | "outline" | "ghost" }) {
  const { canInstall, install } = useInstall();
  if (!canInstall) return null;
  return <Button variant={variant} className={className} onClick={install}><DownloadSimple /> Install app</Button>;
}
