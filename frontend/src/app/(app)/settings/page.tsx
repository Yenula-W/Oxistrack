"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { ArrowCounterClockwise, Cpu, Database, DownloadSimple, Sparkle, Trash, UserPlus } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useInstall } from "@/components/install-app";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/overlays";
import { Card, Field, Input, PageHeader, Select, Textarea } from "@/components/ui/primitives";
import { api, errorMessage, fetcher } from "@/lib/api";
import { loadDemo, useProjectData, useSession } from "@/lib/session";
import type { Member, SystemStatus, User } from "@/lib/types";
import { label } from "@/lib/utils";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="grid gap-5 p-5 md:grid-cols-[240px_minmax(0,1fr)]">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="min-w-0">{children}</div>
    </Card>
  );
}

export default function SettingsPage() {
  const { user, project, projects, refreshProjects, selectProject, refresh, canEdit } = useSession();
  const router = useRouter();
  const system = useSWR<SystemStatus>("/system/status", fetcher, { revalidateOnFocus: false });
  const members = useProjectData<Member[]>("/members");
  const me = useSWR<User>("/auth/me", fetcher, { revalidateOnFocus: false });
  const [name, setName] = React.useState("");
  const [proj, setProj] = React.useState({ name: "", description: "" });
  const [invite, setInvite] = React.useState({ email: "", role: "editor" });
  const [busy, setBusy] = React.useState<string | null>(null);
  const [confirm, setConfirm] = React.useState<"delete" | "reset" | null>(null);
  const isOwner = !!project && project.owner_id === user?.id;
  const app = useInstall();
  const hasDemo = projects.some((p) => p.is_demo);

  React.useEffect(() => { if (user) setName(user.name); }, [user]);
  React.useEffect(() => { if (project) setProj({ name: project.name, description: project.description }); }, [project]);

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    try { await fn(); } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(null); }
  }

  return (
    <>
      <PageHeader title="Settings" />
      <div className="space-y-4">
        <Section title="Profile">
          <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); void run("profile", async () => { await api("/auth/me", { method: "PATCH", json: { name } }); await me.mutate(); toast.success("Profile updated"); }); }}>
            <Field label="Name" className="min-w-[200px] flex-1"><Input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Email" className="min-w-[200px] flex-1"><Input disabled value={user?.email ?? ""} /></Field>
            <Button type="submit" variant="secondary" loading={busy === "profile"}>Save</Button>
          </form>
        </Section>

        {project && (
          <Section title="Project">
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void run("project", async () => { await api(`/projects/${project.id}`, { method: "PATCH", json: proj }); await refreshProjects(); refresh(); toast.success("Project updated"); }); }}>
              <Field label="Project name"><Input required maxLength={160} disabled={!canEdit} value={proj.name} onChange={(e) => setProj({ ...proj, name: e.target.value })} /></Field>
              <Field label="Description"><Textarea maxLength={2000} disabled={!canEdit} value={proj.description} onChange={(e) => setProj({ ...proj, description: e.target.value })} /></Field>
              <div className="flex flex-wrap justify-between gap-2">
                <Button type="submit" variant="secondary" disabled={!canEdit} loading={busy === "project"}>Save changes</Button>
                {isOwner && <Button type="button" variant="outline" className="border-bad/40 text-bad hover:bg-bad-soft hover:text-bad" onClick={() => setConfirm("delete")}><Trash /> Delete project</Button>}
              </div>
            </form>
          </Section>
        )}

        {project && (
          <Section title="Autopilot">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line p-4">
              <div className="min-w-[220px] flex-1">
                <div className="text-base font-medium">{project.autopilot ? "Autopilot is on" : "Autopilot is off"}</div>
                <p className="mt-1 text-sm leading-relaxed text-ink-3">
                  {project.autopilot
                    ? "Settles clear-cut contradictions and approves next steps. Close calls stay with you."
                    : "You settle every contradiction and approve every task."}
                </p>
              </div>
              <Button variant={project.autopilot ? "outline" : "primary"} disabled={!canEdit} loading={busy === "autopilot"}
                onClick={() => run("autopilot", async () => { await api(`/projects/${project.id}`, { method: "PATCH", json: { autopilot: !project.autopilot } }); await refreshProjects(); refresh(); toast.success(project.autopilot ? "Autopilot turned off" : "Autopilot turned on"); })}>
                {project.autopilot ? "Turn off" : "Turn on"}
              </Button>
            </div>
          </Section>
        )}

        {project && (
          <Section title="Members">
            <ul className="divide-y divide-line/70 rounded-lg border border-line">
              {(members.data ?? []).map((m) => (
                <li key={m.id} className="flex items-center gap-3 px-3 py-2.5">
                  <span className="min-w-0 flex-1"><span className="block truncate text-base">{m.name}{m.user_id === user?.id ? " (you)" : ""}</span><span className="block truncate text-xs text-ink-3">{m.email}</span></span>
                  <Badge>{label(m.role)}</Badge>
                  {isOwner && m.role !== "owner" && (
                    <Button variant="ghost" size="icon" aria-label={`Remove ${m.name}`} onClick={() => run("member", async () => { await api(`/projects/${project.id}/members/${m.id}`, { method: "DELETE" }); await members.mutate(); toast.success(`${m.name} removed`); })}><Trash /></Button>
                  )}
                </li>
              ))}
            </ul>
            {isOwner && (
              <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); void run("invite", async () => { await api(`/projects/${project.id}/members`, { method: "POST", json: invite }); await members.mutate(); setInvite({ ...invite, email: "" }); toast.success("Member added"); }); }}>
                <Field label="Add by email" className="min-w-[200px] flex-1"><Input required type="email" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} placeholder="teammate@example.com" /></Field>
                <Field label="Role"><Select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}><option value="editor">Editor</option><option value="viewer">Viewer</option></Select></Field>
                <Button type="submit" variant="secondary" loading={busy === "invite"}><UserPlus /> Add</Button>
              </form>
            )}
          </Section>
        )}

        <Section title="Install the app">
          {app.installed ? <p className="text-sm text-ink-2">You are using the installed app.</p> : app.canInstall ? (
            <Button variant="secondary" onClick={app.install}><DownloadSimple /> Install OxisTrack</Button>
          ) : (
            <ul className="space-y-1.5 text-sm leading-relaxed text-ink-3">
              <li><span className="text-ink-2">Windows or Mac (Chrome, Edge):</span> use the install icon at the right end of the address bar, or the browser menu, then Install OxisTrack.</li>
              <li><span className="text-ink-2">iPhone or iPad (Safari):</span> tap Share, then Add to Home Screen.</li>
              <li><span className="text-ink-2">Android (Chrome):</span> open the menu, then Install app.</li>
            </ul>
          )}
        </Section>

        <Section title="Sample project">
          <div className="flex flex-wrap gap-2">
            {!hasDemo ? (
              <Button variant="secondary" loading={busy === "demo"} onClick={() => run("demo", async () => { const p = await loadDemo(); await refreshProjects(); selectProject(p.id); toast.success("Sample project loaded"); router.push("/overview"); })}><Sparkle /> Load sample project</Button>
            ) : (
              <Button variant="secondary" onClick={() => setConfirm("reset")}><ArrowCounterClockwise /> Reset sample project</Button>
            )}
          </div>
        </Section>

        <Section title="System">
          {system.data ? (
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div className="rounded-lg border border-line p-3">
                <dt className="flex items-center gap-1.5 text-xs text-ink-3"><Cpu className="h-3.5 w-3.5" /> Analysis engine</dt>
                <dd className="mt-1 font-medium text-ink">{system.data.uses_llm ? `AI analyst: ${system.data.llm_model}` : system.data.ai_label}</dd>
                {system.data.uses_llm && (
                  <dd className="mt-0.5 font-medium text-ink">{system.data.reviewer_model ? `AI reviewer: ${system.data.reviewer_model}` : "AI reviewer: not configured"}</dd>
                )}
                <dd className="mt-1 text-xs leading-relaxed text-ink-3">{system.data.uses_llm
                  ? (system.data.reviewer_model ? "The analyst reads documents and proposes decisions. The reviewer is a second, independent model that checks every source choice and unclear requirement. When they disagree, the item goes to a person. " : "") + "Quotes from either model are verified against the source text before anything is stored."
                  : "No LLM key is configured, so extraction and checks run on the built-in deterministic engine. Set LLM_API_KEY on the server to add AI-assisted extraction and semantic checks."}</dd>
              </div>
              <div className="rounded-lg border border-line p-3">
                <dt className="flex items-center gap-1.5 text-xs text-ink-3"><Database className="h-3.5 w-3.5" /> Storage</dt>
                <dd className="mt-1 font-medium text-ink">{system.data.database === "mysql" ? "MySQL" : label(system.data.database)}</dd>
                <dd className="mt-1 text-xs leading-relaxed text-ink-3">Uploads up to {system.data.max_upload_mb} MB · {system.data.allowed_types.map((t) => t.toUpperCase()).join(", ")}</dd>
              </div>
            </dl>
          ) : <p className="text-sm text-ink-3">{system.error ? "System status is unavailable." : "Loading…"}</p>}
        </Section>
        <p className="text-xs text-ink-3">
          Some interface details adapted from <a href="https://skiper-ui.com" target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-ink">Skiper UI</a>.
        </p>
      </div>

      <ConfirmDialog open={confirm === "delete"} onOpenChange={(o) => !o && setConfirm(null)} danger confirmLabel="Delete project"
        title={`Delete “${project?.name ?? ""}”?`} description="Everything in this project is permanently removed."
        onConfirm={async () => {
          if (!project) return;
          try { await api(`/projects/${project.id}`, { method: "DELETE" }); await refreshProjects(); toast.success("Project deleted"); router.push("/overview"); }
          catch (e) { toast.error(errorMessage(e)); }
        }} />
      <ConfirmDialog open={confirm === "reset"} onOpenChange={(o) => !o && setConfirm(null)} confirmLabel="Reset sample project"
        title="Reset the sample project?" description="Rebuilds the sample from scratch."
        onConfirm={async () => {
          try { const p = await loadDemo(true); await refreshProjects(); selectProject(p.id); refresh(); toast.success("Sample project reset"); router.push("/overview"); }
          catch (e) { toast.error(errorMessage(e)); }
        }} />
    </>
  );
}
