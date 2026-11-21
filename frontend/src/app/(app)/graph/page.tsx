"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ImpactPanel } from "@/components/impact-panel";
import { KnowledgeGraph } from "@/components/knowledge-graph";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { PageHeader } from "@/components/ui/primitives";

function GraphInner() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = params.get("tab") === "impact" ? "impact" : "graph";
  return (
    <>
      <PageHeader title="Knowledge Graph" />
      <Tabs value={tab} onValueChange={(v) => router.replace(v === "graph" ? "/graph" : "/graph?tab=impact")}>
        <TabsList>
          <TabsTrigger value="graph">Graph</TabsTrigger>
          <TabsTrigger value="impact">Ripple impact</TabsTrigger>
        </TabsList>
        <TabsContent value="graph"><KnowledgeGraph /></TabsContent>
        <TabsContent value="impact"><ImpactPanel presetRequirement={Number(params.get("requirement")) || null} /></TabsContent>
      </Tabs>
    </>
  );
}

export default function GraphPage() {
  return <Suspense><GraphInner /></Suspense>;
}
