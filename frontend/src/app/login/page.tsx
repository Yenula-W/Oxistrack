"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { DotField } from "@/components/dot-field";
import { LogoMark } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { User } from "@/lib/types";
import { useTryDemo } from "@/lib/use-try-demo";
import { cn } from "@/lib/utils";

type Auth = { access_token: string; user: User };

export default function LoginPage() {
  const { user, loading, signIn } = useSession();
  const router = useRouter();
  const { tryDemo, busy: demoBusy } = useTryDemo();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user && !busy && !demoBusy) router.replace("/overview");
  }, [loading, user, busy, demoBusy, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api<Auth>(mode === "login" ? "/auth/login" : "/auth/register", {
        method: "POST", json: mode === "login" ? { email: form.email, password: form.password } : form });
      signIn(res.access_token, res.user);
      router.replace("/overview");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main className="relative flex min-h-[100dvh] items-center justify-center overflow-hidden bg-bg px-5 py-10">
      <DotField className="absolute inset-0 h-full w-full" />
      <div className="relative z-10 w-full max-w-sm rounded-2xl border border-line bg-surface/80 p-6 shadow-pop backdrop-blur-md">
        <Link href="/" className="mb-6 flex items-center gap-2.5">
          <LogoMark className="h-7 w-7" />
          <span className="font-heading text-base font-bold tracking-[-0.02em] text-ink">OxisTrack</span>
        </Link>

        <div className="grid grid-cols-2 rounded-lg border border-line bg-bg/60 p-1 text-sm">
          {(["login", "register"] as const).map((m) => (
            <button key={m} type="button" onClick={() => { setMode(m); setError(null); }}
              className={cn("rounded-md py-1.5 font-medium transition-colors", mode === m ? "bg-surface-3 text-ink" : "text-ink-3 hover:text-ink")}>
              {m === "login" ? "Sign in" : "Create account"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="mt-5 space-y-4">
          {mode === "register" && (
            <Field label="Name">
              <Input required autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
          )}
          <Field label="Email">
            <Input type="email" required autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </Field>
          <Field label="Password">
            <Input type="password" required minLength={mode === "register" ? 8 : undefined}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </Field>
          {error && <p role="alert" className="rounded-lg border border-bad/30 bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
          <Button type="submit" size="lg" className="w-full" loading={busy} disabled={busy || demoBusy}>
            {mode === "login" ? "Sign in" : "Create account"}
          </Button>
        </form>

        <Button variant="ghost" size="lg" className="mt-2 w-full" onClick={tryDemo} loading={demoBusy} disabled={busy || demoBusy}>
          {demoBusy ? "Loading sample" : "Try the sample project"}
        </Button>
      </div>
    </main>
  );
}
