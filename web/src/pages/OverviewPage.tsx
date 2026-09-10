import { Link, useNavigate } from "react-router"
import { usePolicyCheckHistory, usePolicyCheckHistoryCount, usePolicyCheckRepos } from "../api/hooks"
import type { PolicyCheckHistoryEntry, RepoSummary } from "../api/types"
import { DataTable, type DataTableColumn } from "../components/DataTable"
import { DocsLink } from "../components/DocsLink"
import { EmptyState } from "../components/EmptyState"
import { ErrorBanner } from "../components/ErrorBanner"
import { KpiCell, KpiStrip } from "../components/KpiStrip"
import { SectionHeading } from "../components/Section"
import { RunStatusChip } from "../components/StatusChip"
import { TabIntro } from "../components/TabIntro"
import { formatCost, formatPct, formatRelative } from "../helpers/format"

const README_URL = "https://github.com/mozilla-ai/otari-agent-gates#readme"

function ViewAll({ to }: { to: string }) {
  return (
    <Link to={to} className="text-sm text-link hover:text-link-hover">
      View all
    </Link>
  )
}

function RecentRuns({
  runs,
  isLoading,
  error,
}: {
  runs: PolicyCheckHistoryEntry[]
  isLoading: boolean
  error: unknown
}) {
  const columns: DataTableColumn<PolicyCheckHistoryEntry>[] = [
    { id: "when", header: "When", isRowHeader: true, cell: (row) => formatRelative(row.created_at) },
    { id: "policy", header: "Policy", cell: (row) => row.policy_name },
    { id: "repo", header: "Repo", cell: (row) => row.repo ?? <span className="text-subtle">—</span> },
    {
      id: "status",
      header: "Status",
      cell: (row) => (
        <RunStatusChip checked={row.checked} compliant={row.compliant} gaveUp={row.gave_up} dismissedAt={row.dismissed_at} />
      ),
    },
  ]
  return (
    <section className="flex flex-col gap-3">
      <SectionHeading title="Recent runs" trailing={<ViewAll to="/runs" />} />
      <ErrorBanner error={error} />
      <DataTable
        ariaLabel="Recent runs"
        columns={columns}
        rows={runs}
        getRowKey={(row) => row.id}
        isLoading={isLoading}
        emptyContent="No runs recorded yet."
      />
    </section>
  )
}

function TopReposByCost({ repos, isLoading, error }: { repos: RepoSummary[]; isLoading: boolean; error: unknown }) {
  const ranked = [...repos]
    .filter((repo) => repo.total_cost_usd != null)
    .sort((a, b) => (b.total_cost_usd ?? 0) - (a.total_cost_usd ?? 0))
    .slice(0, 5)
  const columns: DataTableColumn<RepoSummary>[] = [
    {
      id: "repo",
      header: "Repo",
      isRowHeader: true,
      cell: (row) => (
        <Link to={`/runs?group=repo&repo=${encodeURIComponent(row.repo)}`} className="text-link hover:text-link-hover">
          {row.repo}
        </Link>
      ),
    },
    {
      id: "cost",
      header: "Judge cost",
      align: "end",
      cell: (row) => <span className="text-mono-caption">{formatCost(row.total_cost_usd ?? 0)}</span>,
    },
  ]
  return (
    <section className="flex flex-col gap-3">
      <SectionHeading title="Top repos by cost" trailing={<ViewAll to="/runs?group=repo" />} />
      <ErrorBanner error={error} />
      <DataTable
        ariaLabel="Top repos by cost"
        columns={columns}
        rows={ranked}
        getRowKey={(row) => row.repo}
        isLoading={isLoading}
        emptyContent="No judge cost reported yet."
      />
      <p className="text-caption text-subtle">
        API-equivalent cost the claude CLI reports, not money spent: a subscription-backed judge gate runs on your
        existing Claude login.
      </p>
    </section>
  )
}

export function OverviewPage() {
  const navigate = useNavigate()
  const totalCount = usePolicyCheckHistoryCount({})
  const compliantCount = usePolicyCheckHistoryCount({ compliant: true })
  const repos = usePolicyCheckRepos()
  const recentRuns = usePolicyCheckHistory({}, 0, 5)

  const total = totalCount.data?.total ?? null
  const compliant = compliantCount.data?.total ?? null
  const passRate = total !== null && compliant !== null && total > 0 ? compliant / total : null
  const repoRows = repos.data ?? []
  const pricedRepos = repoRows.filter((repo) => repo.total_cost_usd != null)
  const judgeCost = pricedRepos.length > 0 ? pricedRepos.reduce((sum, repo) => sum + (repo.total_cost_usd ?? 0), 0) : null
  const nothingRecorded = total === 0

  return (
    <>
      <TabIntro>
        A reviewer for what your coding agent actually did, so you don't have to check its own work yourself.{" "}
        <DocsLink href={README_URL}>Set up .otari-gates.yml</DocsLink>
      </TabIntro>
      <ErrorBanner error={totalCount.error ?? compliantCount.error} />
      <KpiStrip>
        <KpiCell
          label="Pass rate"
          value={passRate !== null ? formatPct(passRate) : "—"}
          subline={total ? `${compliant ?? 0} of ${total} runs` : "No runs yet"}
        />
        <KpiCell
          label="Total runs"
          value={total !== null ? `${total}` : "—"}
          subline={repoRows.length === 1 ? "1 repo" : `${repoRows.length} repos`}
        />
        <KpiCell
          label="Judge cost"
          value={judgeCost !== null ? formatCost(judgeCost) : "—"}
          subline="API equivalent, not money spent"
        />
      </KpiStrip>
      {nothingRecorded ? (
        <EmptyState
          title="No runs yet"
          description="A run is one reviewed turn of a coding agent's session, judged against a policy's gates. Runs appear here once the Stop hook is installed and a policy exists, either a repo's own .otari-gates.yml or a policy stored on this gateway."
          actionLabel="New gate"
          onAction={() => void navigate("/gates")}
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <RecentRuns runs={recentRuns.data ?? []} isLoading={recentRuns.isLoading} error={recentRuns.error} />
          <TopReposByCost repos={repoRows} isLoading={repos.isLoading} error={repos.error} />
        </div>
      )}
    </>
  )
}
