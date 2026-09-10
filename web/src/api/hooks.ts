import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import { apiFetch } from "./client"
import type {
  BranchSummary,
  ConfiguredPolicySummary,
  CreatePolicyRequest,
  DeleteHistoryResponse,
  PolicyCheckHistoryCount,
  PolicyCheckHistoryEntry,
  PolicyCheckSpecInput,
  PolicyDetailResponse,
  PolicyGateSpec,
  RepoSummary,
  SessionSummary,
} from "./types"

const POLICY_CHECKS = "policy-checks"

function policyPath(name: string): string {
  return `/policy-checks/policies/${encodeURIComponent(name)}`
}

export function usePolicyCheckPolicies() {
  return useQuery({
    queryKey: [POLICY_CHECKS, "policies"],
    queryFn: () => apiFetch<ConfiguredPolicySummary[]>("/policy-checks/policies"),
    staleTime: 5 * 60_000,
  })
}

// The full spec (pattern, message, rules) is fetched only when an editor or
// YAML view actually opens; the list rows carry summaries.
export function usePolicyCheckPolicyDetail(name: string | null) {
  return useQuery({
    queryKey: [POLICY_CHECKS, "policy-detail", name],
    queryFn: () => apiFetch<PolicyDetailResponse>(policyPath(name ?? "")),
    enabled: name !== null,
  })
}

function invalidatePolicies(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: [POLICY_CHECKS, "policies"] })
  void queryClient.invalidateQueries({ queryKey: [POLICY_CHECKS, "policy-detail"] })
}

export function useCreatePolicyCheckPolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CreatePolicyRequest) =>
      apiFetch<ConfiguredPolicySummary>("/policy-checks/policies", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidatePolicies(queryClient),
  })
}

export function useUpdatePolicyCheckPolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ name, body }: { name: string; body: PolicyCheckSpecInput }) =>
      apiFetch<ConfiguredPolicySummary>(policyPath(name), {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidatePolicies(queryClient),
  })
}

export function useDeletePolicyCheckPolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => apiFetch<void>(policyPath(name), { method: "DELETE" }),
    onSuccess: () => invalidatePolicies(queryClient),
  })
}

// The editor's unit is one gate, but the API writes whole gate lists (the
// short-circuit order is a property of the list). Read the current list,
// splice one gate in, out, or replaced, and write it back. Removing the last
// gate would fail validation, so that case deletes the policy instead.
export function useSaveGate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      policyName,
      gateIndex,
      gate,
    }: {
      policyName: string
      gateIndex?: number
      gate: PolicyGateSpec | null
    }) => {
      const detail = await apiFetch<PolicyDetailResponse>(policyPath(policyName))
      const gates = [...detail.gates]
      if (gate === null) {
        if (gateIndex === undefined) {
          throw new Error("gateIndex is required to delete a gate")
        }
        gates.splice(gateIndex, 1)
      } else if (gateIndex !== undefined) {
        gates[gateIndex] = gate
      } else {
        gates.push(gate)
      }
      if (gates.length === 0) {
        await apiFetch<void>(policyPath(policyName), { method: "DELETE" })
        return { policyDeleted: true as const }
      }
      const policy = await apiFetch<ConfiguredPolicySummary>(policyPath(policyName), {
        method: "PUT",
        body: JSON.stringify({ gates, on_unavailable: detail.on_unavailable }),
      })
      return { policyDeleted: false as const, policy }
    },
    onSuccess: () => invalidatePolicies(queryClient),
  })
}

export interface PolicyCheckHistoryFilters {
  policyName?: string
  compliant?: boolean
  sessionId?: string
  repo?: string
  branch?: string
}

function historyParams(filters: PolicyCheckHistoryFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.policyName) params.set("policy_name", filters.policyName)
  if (filters.compliant !== undefined) params.set("compliant", String(filters.compliant))
  if (filters.sessionId) params.set("session_id", filters.sessionId)
  if (filters.repo) params.set("repo", filters.repo)
  if (filters.branch) params.set("branch", filters.branch)
  return params
}

export function usePolicyCheckRepos() {
  return useQuery({
    queryKey: [POLICY_CHECKS, "repos"],
    queryFn: () => apiFetch<RepoSummary[]>("/policy-checks/repos"),
    staleTime: 10_000,
  })
}

export function usePolicyCheckBranches() {
  return useQuery({
    queryKey: [POLICY_CHECKS, "branches"],
    queryFn: () => apiFetch<BranchSummary[]>("/policy-checks/branches"),
    staleTime: 10_000,
  })
}

export function usePolicyCheckSessions() {
  return useQuery({
    queryKey: [POLICY_CHECKS, "sessions"],
    queryFn: () => apiFetch<SessionSummary[]>("/policy-checks/sessions"),
    staleTime: 10_000,
  })
}

// A queried snapshot: it refetches on mount and when the key changes, not on
// its own, so a page an operator is reading does not reshuffle under them.
export function usePolicyCheckHistory(
  filters: PolicyCheckHistoryFilters,
  page: number,
  pageSize: number,
) {
  return useQuery({
    queryKey: [POLICY_CHECKS, "history", filters, page, pageSize],
    queryFn: () => {
      const params = historyParams(filters)
      params.set("skip", String(page * pageSize))
      params.set("limit", String(pageSize))
      return apiFetch<PolicyCheckHistoryEntry[]>(`/policy-checks/history?${params.toString()}`)
    },
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  })
}

export function usePolicyCheckHistoryCount(filters: PolicyCheckHistoryFilters) {
  return useQuery({
    queryKey: [POLICY_CHECKS, "history-count", filters],
    queryFn: () =>
      apiFetch<PolicyCheckHistoryCount>(
        `/policy-checks/history/count?${historyParams(filters).toString()}`,
      ),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  })
}

export function useDismissPolicyCheckHistoryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (recordId: string) =>
      apiFetch<PolicyCheckHistoryEntry>(
        `/policy-checks/history/${encodeURIComponent(recordId)}/dismiss`,
        { method: "POST" },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [POLICY_CHECKS, "history"] })
      void queryClient.invalidateQueries({ queryKey: [POLICY_CHECKS, "history-count"] })
    },
  })
}

// Repo, branch, and session summaries aggregate over the same rows this
// deletes, so every policy-check query is invalidated.
export function useDeleteOldPolicyCheckHistory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (olderThanDays: number) =>
      apiFetch<DeleteHistoryResponse>(`/policy-checks/history?older_than_days=${olderThanDays}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [POLICY_CHECKS] })
    },
  })
}
