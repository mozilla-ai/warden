import { usePolicyCheckRepos } from "../api/hooks"
import type { RepoSummary } from "../api/types"
import { GroupedRunsListPage } from "./GroupedRunsListPage"

export function ReposPage() {
  const repos = usePolicyCheckRepos()
  return (
    <GroupedRunsListPage<RepoSummary>
      title="Repos"
      description="Every repo that has recorded a check, newest run first. Open a repo to see its runs."
      ariaLabel="Repos"
      emptyContent="No repo-scoped runs recorded yet. A check run outside a git repo does not appear here."
      rows={repos.data ?? []}
      isLoading={repos.isLoading}
      error={repos.error}
      groupLabel="Repo"
      getGroupValue={(row) => row.repo}
      historySearchParam="repo"
    />
  )
}
