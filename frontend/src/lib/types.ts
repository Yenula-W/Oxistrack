export interface User { id: number; email: string; name: string; created_at: string }
export interface Project { id: number; name: string; description: string; is_demo: boolean; autopilot: boolean; owner_id: number; created_at: string; updated_at: string; role: string | null }
export interface Member { id: number; user_id: number; name: string; email: string; role: string }

export type DocStatus = "queued" | "processing" | "analyzed" | "failed";
export interface Doc {
  id: number; project_id: number; filename: string; file_type: string; kind: "source" | "deliverable"; status: DocStatus;
  error: string | null; size_bytes: number; current_version: number; document_date: string | null; is_sample: boolean;
  created_at: string; updated_at: string; fact_count: number;
}
export interface Fact {
  id: number; document_id: number; document_name: string; document_version: number; category: string; text: string;
  subject: string; subject_key: string; value_text: string | null; value_type: string; location: string | null;
  segment_index: number | null; confidence: number; extractor: string; created_at: string;
}
export interface DocDetail extends Doc {
  segments: { location: string | null; text: string }[]; facts: Fact[];
  versions: { version: number; size_bytes: number; sha256: string; created_at: string }[];
}
export interface UploadResult { documents: Doc[]; unchanged: string[]; errors: string[] }

export type ContradictionStatus = "open" | "under_review" | "resolved" | "superseded";
export interface ContradictionSource {
  id: number; fact_id: number | null; document_id: number | null; document_name: string; document_date: string | null;
  statement: string; value_text: string; location: string | null; role: "conflicting" | "authoritative" | "superseded";
}
export interface Contradiction {
  id: number; code: string; title: string; category: string; severity: "low" | "medium" | "high" | "critical";
  subject_key: string; status: ContradictionStatus; confidence: number; explanation: string; resolution_note: string | null;
  authoritative_fact_id: number | null; resolved_by_name: string | null; auto_resolved: boolean; resolved_at: string | null; created_at: string;
  updated_at: string; sources: ContradictionSource[];
}

export type ReqStatus = "not_checked" | "passed" | "failed" | "needs_review";
export type Method = "keyword" | "numeric" | "file_exists" | "semantic" | "manual";
export interface Evidence { id: number; document_id: number | null; document_name: string; location: string | null; snippet: string; polarity: "supports" | "contradicts" | "neutral" }
export interface Validation { id: number; requirement_id: number; run_id: string; status: ReqStatus; method: Method; checked: string; explanation: string; reviewed_by: number | null; created_at: string; evidence: Evidence[] }
export interface Requirement {
  id: number; code: string; title: string; description: string; category: string; priority: "low" | "medium" | "high";
  source_type: string; source_text: string | null; source_fact_id: number | null; source_document_id: number | null;
  source_document_name: string | null; subject_key: string; expected_value: string | null; verification_method: Method;
  keywords: string[] | null; status: ReqStatus; blocked_by_contradiction_id: number | null; created_at: string;
  updated_at: string; latest_validation: Validation | null;
}

export interface GraphNode { id: number; node_type: string; ref_key: string; label: string; detail: string; status: string | null }
export interface GraphEdge { id: number; source_id: number; target_id: number; relation: string }
export interface Graph { nodes: GraphNode[]; edges: GraphEdge[] }

export interface ImpactItem { id: number; item_type: string; item_ref: string; label: string; level: "direct" | "indirect"; distance: number; path: string; reason: string; recommended_action: string; confidence: number }
export interface ImpactReport {
  id: number; target_type: string; target_id: number | null; target_label: string; previous_value: string | null;
  new_value: string; source_of_change: string; summary: string; confidence: number; status: "draft" | "applied" | "discarded";
  created_at: string; applied_at: string | null; items: ImpactItem[];
}

export type TaskStatus = "suggested" | "active" | "completed" | "dismissed";
export interface Task {
  id: number; title: string; description: string; reason: string; origin: string; priority: "low" | "medium" | "high";
  status: TaskStatus; related_document_id: number | null; related_document_name: string | null;
  related_requirement_id: number | null; related_requirement_code: string | null; related_contradiction_id: number | null;
  related_contradiction_code: string | null; related_impact_report_id: number | null; due_date: string | null; auto_approved: boolean;
  created_at: string; completed_at: string | null;
}
export interface TimelineEvent {
  id: number; kind: "statement" | "disagreement" | "confirmed_change" | "superseded" | "info"; title: string;
  description: string; subject_key: string; previous_value: string | null; new_value: string | null;
  resolution: string | null; source: string; document_id: number | null; contradiction_id: number | null;
  event_date: string; date_source: "document" | "system"; created_at: string;
}
export interface Activity { id: number; action: string; message: string; entity_type: string | null; entity_id: number | null; created_at: string }

export interface Overview {
  project: Project;
  metrics: {
    documents_analyzed: number; documents_total: number; deliverables: number; facts: number; open_contradictions: number;
    contradictions_total: number; requirements_total: number; requirements_passed: number; requirements_failed: number;
    requirements_needs_review: number; requirements_not_checked: number; open_tasks: number; suggested_tasks: number;
    completed_tasks: number;
  };
  health: { score: number | null; label: string | null; factors: { label: string; impact: number }[] };
  document_activity: { date: string; documents: number; facts: number }[];
  fact_categories: { category: string; count: number }[];
  recent_contradictions: Contradiction[]; recent_changes: TimelineEvent[]; suggested_tasks: Task[]; recent_activity: Activity[];
}
export interface SearchHit { id: number; title: string; subtitle: string; document_id?: number }
export interface SearchResults { query: string; documents: SearchHit[]; facts: SearchHit[]; requirements: SearchHit[]; contradictions: SearchHit[]; decisions: SearchHit[]; tasks: SearchHit[] }
export interface Answer { mode: "rules" | "llm" | "none"; answer: string; uncertainty: string; interpretation: string | null; citations: { fact_id: number; document_id: number; document_name: string; location: string | null; text: string }[] }
export interface SystemStatus { ai_provider: string; ai_label: string; uses_llm: boolean; llm_model: string | null; reviewer_model: string | null; database: string; max_upload_mb: number; allowed_types: string[] }
export interface SampleFile { filename: string; size_bytes: number; kind: string }
