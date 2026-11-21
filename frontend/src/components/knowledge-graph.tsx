"use client";

import * as React from "react";
import Link from "next/link";
import dagre from "@dagrejs/dagre";
import {
  Background, BackgroundVariant, Controls, Handle, MiniMap, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState,
  useReactFlow, type Edge, type Node, type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { CheckCircle, CheckSquare, ClipboardText, FileText, GitDiff, Graph as GraphIcon, Lightbulb, MagnifyingGlass, Quotes, ShieldCheck, Tag, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, EmptyState, ErrorState, Input, Skeleton } from "@/components/ui/primitives";
import { useProjectData } from "@/lib/session";
import type { Graph, GraphNode } from "@/lib/types";
import { cn, label } from "@/lib/utils";

const TYPES: Record<string, { name: string; icon: React.ComponentType<{ className?: string }>; color: string; w: number }> = {
  document: { name: "Documents", icon: FileText, color: "#EDEDEF", w: 220 },
  deliverable: { name: "Deliverables", icon: ClipboardText, color: "#22B8CF", w: 220 },
  fact: { name: "Facts", icon: Quotes, color: "#A1A1AA", w: 230 },
  topic: { name: "Topics", icon: Tag, color: "#D4A72C", w: 160 },
  requirement: { name: "Requirements", icon: ShieldCheck, color: "#E4E4E7", w: 210 },
  contradiction: { name: "Contradictions", icon: GitDiff, color: "#F0616D", w: 200 },
  decision: { name: "Decisions", icon: Lightbulb, color: "#2FBF8A", w: 210 },
  task: { name: "Tasks", icon: CheckSquare, color: "#E58A4E", w: 210 },
};
const NODE_H = 46;

type FlowData = { node: GraphNode; dim: boolean; hit: boolean };

function EntityNode({ data, selected }: NodeProps<Node<FlowData>>) {
  const t = TYPES[data.node.node_type] ?? TYPES.fact;
  return (
    <div style={{ width: t.w, borderColor: selected || data.hit ? t.color : undefined }}
      className={cn("flex h-[46px] items-center gap-2 rounded-lg border border-line-strong bg-surface-2 px-2.5 shadow-sm transition-opacity",
        data.node.node_type === "topic" && "rounded-full", data.dim && "opacity-20", selected && "ring-2 ring-offset-0")}
      title={data.node.label}>
      <Handle type="target" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-line-strong" />
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md" style={{ background: `${t.color}22`, color: t.color }}>
        <t.icon className="h-3.5 w-3.5" />
      </span>
      <span className="line-clamp-2 min-w-0 text-[11px] font-medium leading-tight text-ink">{data.node.label}</span>
      <Handle type="source" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-line-strong" />
    </div>
  );
}

/** A quiet resident of the graph. The picture is an illustration asset, not an icon. */
function CapybaraNode() {
  return (
    <button aria-label="A small capybara" onClick={() => toast("You've uncovered the ultimate source of truth.", { duration: 6000 })}
      className="block cursor-pointer opacity-[0.16] transition-opacity duration-300 hover:opacity-90 focus-visible:opacity-90">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/capybara.svg" alt="" width={38} height={24} draggable={false} />
    </button>
  );
}

const nodeTypes = { entity: EntityNode, capybara: CapybaraNode };

function layout(graph: Graph, hidden: Set<string>) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 14, ranksep: 90, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  const visible = graph.nodes.filter((n) => !hidden.has(n.node_type));
  const ids = new Set(visible.map((n) => n.id));
  visible.forEach((n) => g.setNode(String(n.id), { width: (TYPES[n.node_type] ?? TYPES.fact).w, height: NODE_H }));
  type E = { id: string; source_id: number; target_id: number; relation: string };
  const edges: E[] = graph.edges.filter((e) => ids.has(e.source_id) && ids.has(e.target_id)).map((e) => ({ ...e, id: `e${e.id}` }));
  if (hidden.has("fact")) {
    // Facts are collapsed: connect each fact's owners straight to the topics it is about or mentions.
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    const seen = new Set<string>();
    for (const f of graph.nodes.filter((n) => n.node_type === "fact")) {
      const out = graph.edges.filter((e) => e.source_id === f.id && byId.get(e.target_id)?.node_type === "topic");
      const owners = graph.edges.filter((e) => e.target_id === f.id && ["contains", "confirms"].includes(e.relation));
      for (const o of owners) for (const t of out) {
        const relation = o.relation === "confirms" ? "confirms" : t.relation === "about" ? "states" : "references";
        const key = `${o.source_id}-${t.target_id}-${relation}`;
        if (ids.has(o.source_id) && ids.has(t.target_id) && !seen.has(key)) { seen.add(key); edges.push({ id: `c${key}`, source_id: o.source_id, target_id: t.target_id, relation }); }
      }
    }
  }
  edges.forEach((e) => g.setEdge(String(e.source_id), String(e.target_id)));
  dagre.layout(g);
  let maxX = 0, maxY = 0;
  const nodes: Node<FlowData>[] = visible.map((n) => {
    const p = g.node(String(n.id));
    const w = (TYPES[n.node_type] ?? TYPES.fact).w;
    maxX = Math.max(maxX, p.x + w / 2); maxY = Math.max(maxY, p.y + NODE_H / 2);
    return { id: String(n.id), type: "entity", position: { x: p.x - w / 2, y: p.y - NODE_H / 2 }, data: { node: n, dim: false, hit: false } };
  });
  const flowEdges: Edge[] = edges.map((e) => ({
    id: e.id, source: String(e.source_id), target: String(e.target_id), label: e.relation.replace(/_/g, " "),
    labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 4,
    style: e.relation === "fails" ? { stroke: "#F0616D" } : e.relation === "satisfies" ? { stroke: "#2FBF8A" } : e.relation === "references" ? { strokeDasharray: "4 4" } : undefined,
  }));
  return { nodes, edges: flowEdges, corner: { x: maxX + 60, y: maxY + 46 } };
}

function hrefFor(n: GraphNode): string | null {
  switch (n.node_type) {
    case "document": case "deliverable": return `/documents/${n.ref_key}`;
    case "requirement": return `/verification?tab=requirements&focus=${n.ref_key}`;
    case "contradiction": return `/verification?tab=contradictions&focus=${n.ref_key}`;
    case "task": return "/actions";
    case "decision": return "/overview?tab=timeline";
    default: return null;
  }
}

function GraphCanvas({ graph }: { graph: Graph }) {
  const [hidden, setHidden] = React.useState<Set<string>>(new Set(["fact"]));
  const [query, setQuery] = React.useState("");
  const [selected, setSelected] = React.useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const flow = useReactFlow();
  const present = React.useMemo(() => Object.keys(TYPES).filter((t) => graph.nodes.some((n) => n.node_type === t)), [graph]);

  React.useEffect(() => {
    const l = layout(graph, hidden);
    setNodes([...l.nodes, { id: "capybara", type: "capybara", position: l.corner, data: {}, selectable: false, draggable: false, focusable: false }]);
    setEdges(l.edges);
    setSelected(null);
    requestAnimationFrame(() => {
      void flow.fitView({ padding: 0.1, nodes: l.nodes.map((n) => ({ id: n.id })) });
      // Large graphs would be unreadable when fully fitted: keep text legible and let the user pan.
      requestAnimationFrame(() => { if (flow.getZoom() < 0.72) void flow.setViewport({ x: 24, y: 16, zoom: 0.72 }); });
    });
  }, [graph, hidden, setNodes, setEdges, flow]);

  const neighbours = React.useMemo(() => {
    if (!selected) return null;
    const set = new Set<string>([selected]);
    edges.forEach((e) => { if (e.source === selected) set.add(e.target); if (e.target === selected) set.add(e.source); });
    return set;
  }, [selected, edges]);
  const q = query.trim().toLowerCase();

  const shownNodes = React.useMemo(() => nodes.map((n) => {
    if (n.type !== "entity") return n;
    const d = n.data as FlowData;
    const hit = !!q && (d.node.label.toLowerCase().includes(q) || d.node.detail.toLowerCase().includes(q));
    const dim = neighbours ? !neighbours.has(n.id) : !!q && !hit;
    return d.dim === dim && d.hit === hit ? n : { ...n, data: { ...d, dim, hit } };
  }), [nodes, neighbours, q]);
  const shownEdges = React.useMemo(() => edges.map((e) => {
    const on = !selected || e.source === selected || e.target === selected;
    return { ...e, animated: !!selected && on, style: { ...e.style, opacity: on ? 1 : 0.12 }, labelStyle: { opacity: selected && on ? 1 : 0 }, labelBgStyle: { opacity: selected && on ? 1 : 0 } };
  }), [edges, selected]);

  const matches = q ? shownNodes.filter((n) => n.type === "entity" && (n.data as FlowData).hit) : [];
  const sel = selected ? graph.nodes.find((n) => String(n.id) === selected) ?? null : null;
  const connected = sel ? graph.edges.filter((e) => e.source_id === sel.id || e.target_id === sel.id).map((e) => {
    const outgoing = e.source_id === sel.id;
    const other = graph.nodes.find((n) => n.id === (outgoing ? e.target_id : e.source_id));
    return other ? { other, relation: e.relation, outgoing } : null;
  }).filter((x): x is { other: GraphNode; relation: string; outgoing: boolean } => !!x) : [];

  const focusNode = (id: string) => {
    setSelected(id);
    const n = flow.getNode(id);
    if (n) flow.setCenter(n.position.x + 110, n.position.y + 23, { zoom: 1.15, duration: 400 });
  };

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-64">
          <MagnifyingGlass className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-3" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search the graph" className="pl-9" aria-label="Search graph"
            onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) focusNode(matches[0].id); }} />
        </div>
        {q && <span className="text-xs text-ink-3">{matches.length} match{matches.length === 1 ? "" : "es"}{matches.length ? " · Enter to jump" : ""}</span>}
        <div className="flex flex-wrap gap-1.5 sm:ml-auto" role="group" aria-label="Filter node types">
          {present.map((t) => {
            const on = !hidden.has(t);
            return (
              <button key={t} aria-pressed={on} onClick={() => { const n = new Set(hidden); if (on) n.add(t); else n.delete(t); setHidden(n); }}
                className={cn("flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors", on ? "border-line-strong bg-surface-2 text-ink" : "border-line text-ink-3 line-through")}>
                <span className="h-2 w-2 rounded-full" style={{ background: on ? TYPES[t].color : "#3F3F46" }} />
                {TYPES[t].name}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <Card className="h-[66vh] min-h-[420px] overflow-hidden">
          <ReactFlow nodes={shownNodes} edges={shownEdges} nodeTypes={nodeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            onNodeClick={(_, n) => n.type === "entity" && setSelected(n.id)} onPaneClick={() => setSelected(null)}
            nodesConnectable={false} minZoom={0.15} maxZoom={2} proOptions={{ hideAttribution: false }} colorMode="dark">
            <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1F1F23" />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable nodeStrokeWidth={0} className="hidden md:block"
              nodeColor={(n) => (n.type === "entity" ? TYPES[(n.data as FlowData).node.node_type]?.color ?? "#A1A1AA" : "transparent")} />
          </ReactFlow>
        </Card>

        <Card className="max-h-[62vh] overflow-y-auto p-4 scroll-thin">
          {!sel ? (
            <div className="text-sm leading-relaxed text-ink-3">
              <div className="mb-1 text-base font-semibold text-ink">Select a node</div>
              <div className="tabular text-xs">{graph.nodes.length} nodes · {graph.edges.length} relationships</div>
            </div>
          ) : (
            <div>
              <div className="flex items-start justify-between gap-2">
                <Badge className="shrink-0"><span className="h-2 w-2 rounded-full" style={{ background: TYPES[sel.node_type]?.color }} />{label(sel.node_type)}</Badge>
                <button onClick={() => setSelected(null)} className="rounded p-1 text-ink-3 hover:bg-surface-2 hover:text-ink" aria-label="Clear selection"><X className="h-3.5 w-3.5" /></button>
              </div>
              <div className="mt-2 text-base font-semibold leading-snug">{sel.label}</div>
              {sel.detail && <p className="mt-1 text-sm leading-relaxed text-ink-3">{sel.detail}</p>}
              {sel.status && sel.node_type !== "fact" && <div className="mt-2"><StatusBadge status={sel.status} /></div>}
              {hrefFor(sel) && <Button asChild variant="secondary" size="sm" className="mt-3"><Link href={hrefFor(sel) as string}>Open {label(sel.node_type).toLowerCase()}</Link></Button>}
              <div className="mt-4 text-[11px] font-medium uppercase tracking-wider text-ink-3">Relationships ({connected.length})</div>
              <ul className="mt-1.5 space-y-1">
                {connected.map((c, i) => (
                  <li key={i}>
                    <button onClick={() => focusNode(String(c.other.id))} className="w-full rounded-lg px-2 py-1.5 text-left hover:bg-surface-2">
                      <span className="block text-[11px] text-ink-3">{c.outgoing ? `${c.relation.replace(/_/g, " ")} →` : `← ${c.relation.replace(/_/g, " ")}`}</span>
                      <span className="flex items-center gap-1.5 text-sm text-ink-2">
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: TYPES[c.other.node_type]?.color }} />
                        <span className="line-clamp-2">{c.other.label}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

export function KnowledgeGraph() {
  const { data, error, isLoading, mutate } = useProjectData<Graph>("/graph");
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (isLoading || !data) return <Skeleton className="h-[62vh] w-full" />;
  if (!data.nodes.length) {
    return <Card><EmptyState icon={GraphIcon} title="The graph is empty" description="Analyze documents to build it." >
      <Button asChild><Link href="/documents"><CheckCircle /> Go to documents</Link></Button></EmptyState></Card>;
  }
  return <ReactFlowProvider><GraphCanvas graph={data} /></ReactFlowProvider>;
}
