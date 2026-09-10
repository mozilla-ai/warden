import { usePolicyCheckBranches } from "../api/hooks"
import type { BranchSummary } from "../api/types"
import { GroupedRunsListPage } from "./GroupedRunsListPage"

export function BranchesPage() {
  const branches = usePolicyCheckBranches()
  return (
    <GroupedRunsListPage<BranchSummary>
      title="Branches"
      description="Every git branch that has recorded a check, newest run first: what a feature branch's own checks are costing in tokens and nominal dollars. Open a branch to see its runs."
      ariaLabel="Branches"
      emptyContent="No branch-scoped runs recorded yet. A check run outside a git repo does not appear here."
      rows={branches.data ?? []}
      isLoading={branches.isLoading}
      error={branches.error}
      groupLabel="Branch"
      getGroupValue={(row) => row.branch}
      historySearchParam="branch"
    />
  )
}
