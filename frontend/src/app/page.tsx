"use client";

import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react";
import { DotField } from "@/components/dot-field";
import { LogoMark } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/session";
import { useTryDemo } from "@/lib/use-try-demo";

export default function Home() {
  const { user, loading } = useSession();
  const { tryDemo, busy } = useTryDemo();

  return (
    <main className="relative h-[100dvh] overflow-hidden bg-bg">
      <DotField className="absolute inset-0 h-full w-full" />

      <header className="pointer-events-none relative z-10 flex items-center justify-between px-5 py-5 sm:px-8">
        <span className="flex items-center gap-2.5">
          <LogoMark className="h-7 w-7" />
          <span className="font-heading text-base font-bold tracking-[-0.02em] text-ink">OxisTrack</span>
        </span>
        {!loading && (
          <Link href={user ? "/overview" : "/login"}
            className="pointer-events-auto rounded-lg px-3 py-1.5 text-sm text-ink-2 transition-colors hover:text-ink">
            {user ? "Open workspace" : "Sign in"}
          </Link>
        )}
      </header>

      <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center px-5">
        <h1 className="select-none font-heading text-[clamp(56px,11vw,168px)] font-bold leading-none tracking-[-0.055em] text-ink">
          OxisTrack
        </h1>
        <div className="pointer-events-auto mt-10 flex items-center gap-2">
          {user ? (
            <Button asChild size="lg" className="rounded-full px-6">
              <Link href="/overview">Open workspace <ArrowRight /></Link>
            </Button>
          ) : (
            <Button size="lg" className="rounded-full px-6" onClick={tryDemo} loading={busy} disabled={loading}>
              {busy ? "Loading sample" : "Try it"} {!busy && <ArrowRight />}
            </Button>
          )}
        </div>
      </div>
    </main>
  );
}
