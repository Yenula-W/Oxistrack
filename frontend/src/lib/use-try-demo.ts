"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { loadDemo, useSession } from "@/lib/session";
import type { User } from "@/lib/types";

type Auth = { access_token: string; user: User };

/** Creates a guest account, loads the sample project and opens it. */
export function useTryDemo() {
  const { signIn, selectProject } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function tryDemo() {
    setError(null);
    setBusy(true);
    try {
      const id = crypto.randomUUID().replace(/-/g, "");
      const res = await api<Auth>("/auth/register", { method: "POST",
        json: { name: "Guest", email: `guest-${id.slice(0, 12)}@oxistrack.app`, password: id } });
      signIn(res.access_token, res.user);
      const project = await loadDemo();
      selectProject(project.id);
      toast.success("Sample project loaded");
      router.replace("/overview");
    } catch (err) {
      const message = errorMessage(err);
      setError(message);
      toast.error(message);
      setBusy(false);
    }
  }

  return { tryDemo, busy, error };
}
