import { requestJSON } from "./backtest-api";

export type CandidateStatus =
  | "proposed"
  | "implemented"
  | "review_ready"
  | "approved"
  | "rejected";

export type CandidateRecord = {
  schema_version: "candidate-record.v1";
  proposal_id: string;
  created_at: string;
  updated_at: string;
  status: CandidateStatus;
  proposal: {
    schema_version: "candidate-proposal.v1";
    strategy_slug: string;
    title: string;
    hypothesis: string;
    rationale: string;
    category: "trend" | "mean_reversion" | "intraday";
    supported_intervals: Array<"5m" | "15m" | "1h" | "4h" | "1d">;
    parameters: Array<{
      key: string;
      kind: "integer" | "decimal";
      label: string;
      default: number | string;
      minimum: number | string;
      maximum: number | string;
    }>;
    implementation_plan: string[];
    research_plan: string[];
    sources: Array<{ title: string; url: string }>;
    proposed_by: { kind: "agent"; name: string; workflow_version: string };
  };
  implementation: {
    implementation_ref: string;
    test_ids: string[];
  } | null;
  robustness_review_id: string | null;
  robustness_sha256: string | null;
  transitions: Array<{
    from_status: CandidateStatus | null;
    to_status: CandidateStatus;
    actor_kind: "agent" | "system" | "human";
    actor_name: string;
    rationale: string;
    occurred_at: string;
    evidence_id: string | null;
  }>;
};

export async function listCandidates(signal?: AbortSignal): Promise<CandidateRecord[]> {
  const response = await requestJSON<{ candidates: CandidateRecord[] }>(
    "/api/v1/candidates",
    {},
    signal,
  );
  return response.candidates;
}
