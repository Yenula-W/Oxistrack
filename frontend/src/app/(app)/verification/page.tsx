"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ContradictionsPanel } from "@/components/contradictions-panel";
import { RequirementsPanel } from "@/components/requirements-panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { PageHeader } from "@/components/ui/primitives";
import { useProjectData } from "@/lib/session";
import type { Overview } from "@/lib/types";

function Count({ n, tone }: { n?: number; tone?: "bad" }) {
  if (!n) return null;
  return <span className={`tabular text-xs ${tone === "bad" ? "font-medium text-ink" : "text-ink-3"}`}>{n}</span>;
}

function VerificationInner() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = params.get("tab") === "requirements" ? "requirements" : "contradictions";
  const focus = Number(params.get("focus")) || null;
  const { data } = useProjectData<Overview>("/overview");
  return (
    <>
      <PageHeader title="Verification" />
      <Tabs value={tab} onValueChange={(v) => router.replace(`/verification?tab=${v}`)}>
        <TabsList>
          <TabsTrigger value="contradictions">Contradictions <Count n={data?.metrics.open_contradictions} tone="bad" /></TabsTrigger>
          <TabsTrigger value="requirements">Requirements <Count n={data?.metrics.requirements_total} /></TabsTrigger>
        </TabsList>
        <TabsContent value="contradictions"><ContradictionsPanel focus={tab === "contradictions" ? focus : null} /></TabsContent>
        <TabsContent value="requirements"><RequirementsPanel focus={tab === "requirements" ? focus : null} /></TabsContent>
      </Tabs>
    </>
  );
}

export default function VerificationPage() {
  return <Suspense><VerificationInner /></Suspense>;
}
