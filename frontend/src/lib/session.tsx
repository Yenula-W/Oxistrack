"use client";

import * as React from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher, getToken, setToken } from "./api";
import type { Project, User } from "./types";

interface SessionValue {
  user: User | null;
  loading: boolean;
  projects: Project[];
  projectsLoading: boolean;
  project: Project | null;
  selectProject: (id: number) => void;
  refreshProjects: () => Promise<Project[] | undefined>;
  signIn: (token: string, user: User) => void;
  signOut: () => void;
  /** Revalidate every cached query for the current project. */
  refresh: () => void;
  canEdit: boolean;
}

const SessionContext = React.createContext<SessionValue | null>(null);
const PROJECT_KEY = "oxistrack.project";

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [hasToken, setHasToken] = React.useState<boolean | null>(null);
  const [projectId, setProjectId] = React.useState<number | null>(null);
  const { mutate } = useSWRConfig();

  React.useEffect(() => {
    setHasToken(!!getToken());
    const saved = Number(window.localStorage.getItem(PROJECT_KEY));
    if (saved) setProjectId(saved);
  }, []);

  const me = useSWR<User>(hasToken ? "/auth/me" : null, fetcher, { shouldRetryOnError: false, revalidateOnFocus: false });
  const projects = useSWR<Project[]>(me.data ? "/projects" : null, fetcher, { revalidateOnFocus: false });

  const list = React.useMemo(() => projects.data ?? [], [projects.data]);
  const project = list.find((p) => p.id === projectId) ?? list[0] ?? null;

  const selectProject = React.useCallback((id: number) => {
    setProjectId(id);
    window.localStorage.setItem(PROJECT_KEY, String(id));
  }, []);

  const value: SessionValue = {
    user: me.data ?? null,
    loading: hasToken === null || (hasToken && me.isLoading),
    projects: list,
    projectsLoading: projects.isLoading,
    project,
    selectProject,
    refreshProjects: () => projects.mutate(),
    signIn: (token, user) => { setToken(token); setHasToken(true); void me.mutate(user, { revalidate: false }); },
    signOut: () => { setToken(null); setHasToken(false); window.localStorage.removeItem(PROJECT_KEY); void mutate(() => true, undefined, { revalidate: false }); },
    refresh: () => { void mutate((key) => typeof key === "string" && (key.startsWith("/projects/") || key.startsWith("/documents/"))); },
    canEdit: !!project && project.role !== "viewer",
  };
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = React.useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}

/** SWR hook scoped to the current project: `useProjectData<Doc[]>("/documents")`. */
export function useProjectData<T>(suffix: string | null, opts?: { refreshInterval?: number | ((data: T | undefined) => number) }) {
  const { project } = useSession();
  return useSWR<T>(project && suffix !== null ? `/projects/${project.id}${suffix}` : null, fetcher, {
    revalidateOnFocus: false, ...opts,
  });
}

export async function loadDemo(reset = false): Promise<Project> {
  return api<Project>(reset ? "/demo/reset" : "/demo/load", { method: "POST" });
}
