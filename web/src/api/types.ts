// Hand-written mirrors of the plugin's pydantic response and request models.

export type GateType =
  | "deterministic"
  | "command"
  | "scoped_guidance"
  | "edited_path"
  | "llm_judge"

export interface GateOutcome {
  name: string
  type: GateType
  passed: boolean
  skipped: boolean
  violations: string[]
  guidance: string
  total_cost_usd: number | null
  input_tokens: number | null
  output_tokens: number | null
}

export interface PolicyCheckHistoryEntry {
  id: string
  policy_name: string
  session_id: string | null
  turn_id: string | null
  repo: string | null
  branch: string | null
  checked: boolean
  compliant: boolean
  violations: string[]
  guidance: string
  gates: GateOutcome[] | null
  total_cost_usd: number | null
  total_input_tokens: number | null
  total_output_tokens: number | null
  gave_up: boolean
  dismissed_at: string | null
  created_at: string
}

export interface PolicyCheckHistoryCount {
  total: number
}

export interface GroupSummary {
  run_count: number
  total_cost_usd: number | null
  total_input_tokens: number | null
  total_output_tokens: number | null
  last_run_at: string
  last_compliant: boolean
  last_checked: boolean
  last_policy_name: string
}

export interface RepoSummary extends GroupSummary {
  repo: string
}

export interface BranchSummary extends GroupSummary {
  branch: string
}

export interface SessionSummary extends GroupSummary {
  session_id: string
  repo: string | null
  branch: string | null
}

export interface PolicyGateSummary {
  name: string
  type: GateType
  judge_backend: string | null
  judge_model: string | null
}

export interface ConfiguredPolicySummary {
  name: string
  on_unavailable: "block" | "monitor"
  gates: PolicyGateSummary[]
}

export interface DeterministicGateSpec {
  type: "deterministic"
  name: string
  pattern: string
  mode: "must_match" | "must_not_match"
  message: string
}

export interface CommandGateSpec {
  type: "command"
  name: string
  pattern: string
  mode: "must_run_and_succeed" | "must_not_run"
  paths: string[] | null
  message: string
}

export interface ScopedGuidanceGateSpec {
  type: "scoped_guidance"
  name: string
  directory: string
  message: string
}

export interface EditedPathGateSpec {
  type: "edited_path"
  name: string
  pattern: string
  mode: "must_not_edit" | "must_edit"
  message: string
}

export interface JudgeGateSpec {
  type: "llm_judge"
  name: string
  judge_backend: "provider" | "subscription"
  judge_model: string | null
  rules: string | null
  rules_file: string | null
  max_transcript_chars: number
  judge_max_tokens: number
}

export type PolicyGateSpec =
  | DeterministicGateSpec
  | CommandGateSpec
  | ScopedGuidanceGateSpec
  | EditedPathGateSpec
  | JudgeGateSpec

export interface PolicyCheckSpecInput {
  gates: PolicyGateSpec[]
  on_unavailable: "block" | "monitor"
}

export interface PolicyDetailResponse extends PolicyCheckSpecInput {
  name: string
  yaml: string
}

export type CreatePolicyRequest = PolicyCheckSpecInput & { name: string }

export interface DeleteHistoryResponse {
  deleted: number
}
