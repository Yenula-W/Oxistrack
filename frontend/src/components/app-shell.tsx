"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bell, CaretUpDown, Check, CheckSquare, FileText, FolderPlus, GearSix, Graph, List, MagnifyingGlass, Plus, ShieldCheck, SignOut, SquaresFour, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import { InstallButton } from "@/components/install-app";
import { Logo, LogoMark } from "@/components/logo";
import { SearchDialog } from "@/components/search-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, Dropdown, DropdownContent, DropdownItem, DropdownLabel, DropdownSeparator, DropdownTrigger,
} from "@/components/ui/overlays";
import { EmptyState, Field, Input, Skeleton, Textarea } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { loadDemo, useProjectData, useSession } from "@/lib/session";
import type { Activity, Overview, Project } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { motion } from "framer-motion";
import { ProgressiveBlur, TextRoll } from "@/components/skiper";

const MotionLink = motion.create(Link);

const NAV = [
  { href: "/overview", label: "Overview", icon: SquaresFour },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/verification", label: "Verification", icon: ShieldCheck },
  { href: "/graph", label: "Knowledge Graph", icon: Graph },
  { href: "/actions", label: "Action Center", icon: CheckSquare },
  { href: "/settings", label: "Settings", icon: GearSix },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data } = useProjectData<Overview>("/overview");
  const counts: Record<string, number | undefined> = {
    "/verification": data?.metrics.open_contradictions,
    "/actions": data ? data.metrics.suggested_tasks + data.metrics.open_tasks : undefined,
  };
  return (
    <nav className="space-y-0.5 px-3" aria-label="Main">
      {NAV.map((item) => {
        const active = pathname === item.href || pathname.startsWith(item.href + "/");
        return (
          <MotionLink key={item.href} href={item.href} onClick={onNavigate} aria-current={active ? "page" : undefined}
            initial="initial" whileHover="hovered"
            className={cn("group flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-base font-medium transition-colors",
              active ? "bg-brand-soft text-ink" : "text-ink-3 hover:bg-surface-2 hover:text-ink")}>
            <item.icon className={cn("h-4 w-4", active ? "text-brand" : "text-ink-3 group-hover:text-ink-2")} />
            <TextRoll className="flex-1">{item.label}</TextRoll>
            {!!counts[item.href] && (
              <span className="tabular rounded-md bg-surface-3 px-1.5 text-[11px] leading-5 text-ink-2">{counts[item.href]}</span>
            )}
          </MotionLink>
        );
      })}
    </nav>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center px-5">
        <Link href="/overview" onClick={onNavigate}><Logo /></Link>
      </div>
      <div className="mt-3 flex-1"><NavLinks onNavigate={onNavigate} /></div>
      <InstallButton className="m-3" />
    </div>
  );
}

export function NewProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { refreshProjects, selectProject } = useSession();
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New project">
        <form className="space-y-4" onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const p = await api<Project>("/projects", { method: "POST", json: { name, description } });
            await refreshProjects();
            selectProject(p.id);
            toast.success(`Project “${p.name}” created`);
            setName(""); setDescription("");
            onOpenChange(false);
          } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
        }}>
          <Field label="Project name"><Input autoFocus required maxLength={160} value={name} onChange={(e) => setName(e.target.value)} placeholder="Capstone project" /></Field>
          <Field label="Description" hint="Optional"><Textarea maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Create project</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ProjectSelector({ onNew }: { onNew: () => void }) {
  const { projects, project, selectProject } = useSession();
  return (
    <Dropdown>
      <DropdownTrigger asChild>
        <button className="flex h-9 min-w-0 max-w-[260px] items-center gap-2 rounded-lg border border-line bg-surface px-2.5 text-base hover:bg-surface-2" aria-label="Select project">
          <span className="h-2 w-2 shrink-0 rounded-full bg-brand" />
          <span className="truncate font-medium">{project?.name ?? "No project"}</span>
          {project?.is_demo && <Badge tone="brand" className="hidden sm:inline-flex">Sample</Badge>}
          <CaretUpDown className="h-3.5 w-3.5 shrink-0 text-ink-3" />
        </button>
      </DropdownTrigger>
      <DropdownContent align="start" className="w-72">
        <DropdownLabel>Projects</DropdownLabel>
        {projects.map((p) => (
          <DropdownItem key={p.id} onSelect={() => selectProject(p.id)}>
            <span className="flex-1 truncate">{p.name}</span>
            {p.is_demo && <Badge tone="brand">Sample</Badge>}
            {p.id === project?.id && <Check className="text-brand" />}
          </DropdownItem>
        ))}
        {projects.length > 0 && <DropdownSeparator />}
        <DropdownItem onSelect={onNew}><Plus /> New project</DropdownItem>
      </DropdownContent>
    </Dropdown>
  );
}

function Notifications() {
  const { data } = useProjectData<Activity[]>("/activity?limit=12", { refreshInterval: 30000 });
  const [seen, setSeen] = React.useState(0);
  React.useEffect(() => { setSeen(Number(window.localStorage.getItem("oxistrack.seen") || 0)); }, []);
  const latest = data?.[0]?.id ?? 0;
  const unread = (data ?? []).filter((a) => a.id > seen).length;
  return (
    <Dropdown onOpenChange={(o) => { if (o && latest) { setSeen(latest); window.localStorage.setItem("oxistrack.seen", String(latest)); } }}>
      <DropdownTrigger asChild>
        <button className="relative flex h-9 w-9 items-center justify-center rounded-lg text-ink-2 hover:bg-surface-2 hover:text-ink" aria-label={`Notifications${unread ? `, ${unread} new` : ""}`}>
          <Bell className="h-4 w-4" />
          {unread > 0 && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-brand ring-2 ring-bg" />}
        </button>
      </DropdownTrigger>
      <DropdownContent className="w-80 p-0">
        <div className="border-b border-line px-3.5 py-2.5 text-base font-semibold">Recent activity</div>
        <div className="max-h-80 overflow-y-auto scroll-thin">
          {!data?.length && <p className="px-3.5 py-6 text-center text-sm text-ink-3">Nothing has happened in this project yet.</p>}
          {data?.map((a) => (
            <div key={a.id} className="border-b border-line/60 px-3.5 py-2.5 last:border-0">
              <div className="text-sm leading-snug text-ink-2">{a.message}</div>
              <div className="mt-0.5 text-[11px] text-ink-3">{timeAgo(a.created_at)}</div>
            </div>
          ))}
        </div>
      </DropdownContent>
    </Dropdown>
  );
}

function UserMenu() {
  const { user, signOut } = useSession();
  const router = useRouter();
  const initials = (user?.name ?? "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  return (
    <Dropdown>
      <DropdownTrigger asChild>
        <button className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line-strong bg-surface-2 text-xs font-medium text-ink" aria-label="Account menu">
          {initials}
        </button>
      </DropdownTrigger>
      <DropdownContent>
        <div className="px-2.5 py-2">
          <div className="text-base font-medium text-ink">{user?.name}</div>
          <div className="max-w-[220px] truncate text-xs text-ink-3">{user?.email}</div>
        </div>
        <DropdownSeparator />
        <DropdownItem onSelect={() => router.push("/settings")}><GearSix /> Settings</DropdownItem>
        <DropdownItem onSelect={() => { signOut(); router.replace("/login"); }}><SignOut /> Sign out</DropdownItem>
      </DropdownContent>
    </Dropdown>
  );
}

function NoProject({ onNew }: { onNew: () => void }) {
  const { refreshProjects, selectProject } = useSession();
  const [busy, setBusy] = React.useState(false);
  return (
    <div className="mx-auto mt-16 max-w-lg rounded-2xl border border-line bg-surface">
      <EmptyState icon={FolderPlus} title="Create your first project"
        description="Upload your files or open the sample.">
        <Button onClick={onNew}><Plus /> New project</Button>
        <Button variant="secondary" loading={busy} onClick={async () => {
          setBusy(true);
          try { const p = await loadDemo(); await refreshProjects(); selectProject(p.id); toast.success("Sample project loaded"); }
          catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); }
        }}>Load sample project</Button>
      </EmptyState>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, project, projectsLoading } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileNav, setMobileNav] = React.useState(false);
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [newProject, setNewProject] = React.useState(false);

  React.useEffect(() => { if (!loading && !user) router.replace("/login"); }, [loading, user, router]);
  React.useEffect(() => { setMobileNav(false); }, [pathname]);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (loading || !user) {
    return <div className="flex h-screen items-center justify-center"><LogoMark className="h-10 w-10 animate-pulse" /></div>;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="hidden w-60 shrink-0 border-r border-line bg-surface lg:block"><Sidebar /></aside>
      {mobileNav && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 animate-fade-in bg-black/60" onClick={() => setMobileNav(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-line bg-surface shadow-pop">
            <button className="absolute right-3 top-3.5 rounded-md p-1.5 text-ink-3 hover:bg-surface-2" onClick={() => setMobileNav(false)} aria-label="Close menu"><X className="h-4 w-4" /></button>
            <Sidebar onNavigate={() => setMobileNav(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line bg-bg/80 px-4 backdrop-blur lg:px-6">
          <button className="rounded-lg p-2 text-ink-2 hover:bg-surface-2 lg:hidden" onClick={() => setMobileNav(true)} aria-label="Open menu"><List className="h-4 w-4" /></button>
          <ProjectSelector onNew={() => setNewProject(true)} />
          <button onClick={() => setSearchOpen(true)} disabled={!project}
            className="ml-auto flex h-9 items-center gap-2 rounded-lg border border-line bg-surface px-2.5 text-base text-ink-3 hover:bg-surface-2 hover:text-ink-2 disabled:opacity-50 sm:w-64" aria-label="Search project">
            <MagnifyingGlass className="h-4 w-4" />
            <span className="hidden flex-1 text-left sm:block">Search or ask…</span>
            <kbd className="hidden rounded border border-line-strong px-1.5 font-mono text-[10px] text-ink-3 sm:block">⌘K</kbd>
          </button>
          {project && <Notifications />}
          <UserMenu />
        </header>
        <div className="relative min-h-0 flex-1">
          <main className="h-full overflow-y-auto scroll-thin">
            <div className="mx-auto w-full max-w-[1280px] px-4 pb-24 pt-6 lg:px-8 lg:pt-8">
              {projectsLoading ? <div className="space-y-4"><Skeleton className="h-8 w-64" /><Skeleton className="h-40 w-full" /></div>
                : project || pathname.startsWith("/settings") ? children : <NoProject onNew={() => setNewProject(true)} />}
            </div>
          </main>
          <ProgressiveBlur position="bottom" height="72px" className="right-2" />
        </div>
      </div>
      {project && <SearchDialog open={searchOpen} onOpenChange={setSearchOpen} />}
      <NewProjectDialog open={newProject} onOpenChange={setNewProject} />
    </div>
  );
}
