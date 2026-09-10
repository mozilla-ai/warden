import { Button } from "@heroui/react"
import { Link, useNavigate } from "react-router"
import { usePolicyCheckHistory, usePolicyCheckHistoryCount, usePolicyCheckRepos } from "../api/hooks"
import type { PolicyCheckHistoryEntry, RepoSummary } from "../api/types"
import { DataTable, type DataTableColumn } from "../components/DataTable"
import { ErrorBanner } from "../components/ErrorBanner"
import { PageHeader } from "../components/PageHeader"
import { StatCard } from "../components/StatCard"
import { RunStatusMark } from "../components/StatusMark"
import { formatCost, formatPct, formatRelative } from "../helpers/format"

const README_URL = "https://github.com/mozilla-ai/otari-agent-gates#readme"

function PanelHeader({ title, to }: { title: string; to: string }) {
  return (
    <div className="flex items-center justify-between">
      <h2 className="text-lg font-semibold">{title}</h2>
      <Link to={to} className="text-sm text-link underline-offset-2 hover:underline">
        View all
      </Link>
    </div>
  )
}

function RecentRunsPanel({
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
    { id: "repo", header: "Repo", cell: (row) => row.repo ?? <span className="text-muted">—</span> },
    {
      id: "status",
      header: "Status",
      cell: (row) => <RunStatusMark checked={row.checked} compliant={row.compliant} />,
    },
  ]
  return (
    <div className="flex flex-col gap-3">
      <PanelHeader title="Recent runs" to="/runs" />
      <ErrorBanner error={error} />
      <DataTable
        ariaLabel="Recent runs"
        columns={columns}
        rows={runs}
        getRowKey={(row) => row.id}
        isLoading={isLoading}
        emptyContent="No runs recorded yet."
      />
    </div>
  )
}

function TopReposByCostPanel({
  repos,
  isLoading,
  error,
}: {
  repos: RepoSummary[]
  isLoading: boolean
  error: unknown
}) {
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
        <Link
          to={`/runs?repo=${encodeURIComponent(row.repo)}`}
          className="font-medium underline underline-offset-2"
        >
          {row.repo}
        </Link>
      ),
    },
    {
      id: "cost",
      header: (
        <span title="What the claude CLI reports these tokens would cost metered. Not money spent: subscription-backed judge gates run on your existing Claude login.">
          Judge cost (API equiv.)
        </span>
      ),
      align: "end",
      cell: (row) => formatCost(row.total_cost_usd ?? 0),
    },
  ]
  return (
    <div className="flex flex-col gap-3">
      <PanelHeader title="Top repos by cost" to="/repos" />
      <ErrorBanner error={error} />
      <DataTable
        ariaLabel="Top repos by cost"
        columns={columns}
        rows={ranked}
        getRowKey={(row) => row.repo}
        isLoading={isLoading}
        emptyContent="No subscription-backend judge cost reported yet."
      />
      <p className="text-xs text-muted">
        Not money spent. This is the API-equivalent cost the claude CLI reports for tokens that
        ran on your existing Claude login at no marginal cost.
      </p>
    </div>
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

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Overview"
        description="A reviewer for what your coding agent actually did, so you don't have to check its own work yourself."
      />
      <ErrorBanner error={totalCount.error ?? compliantCount.error} />
      <div className="grid grid-cols-2 gap-4">
        <StatCard
          label="Pass rate"
          value={passRate !== null ? formatPct(passRate) : "—"}
          hint={total !== null ? `${compliant ?? 0} of ${total} runs` : undefined}
          to="/runs"
        />
        <StatCard label="Total runs" value={total !== null ? `${total}` : "—"} to="/runs" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <RecentRunsPanel runs={recentRuns.data ?? []} isLoading={recentRuns.isLoading} error={recentRuns.error} />
        <TopReposByCostPanel repos={repos.data ?? []} isLoading={repos.isLoading} error={repos.error} />
      </div>
      <div className="flex flex-wrap gap-3">
        <Button variant="primary" onPress={() => navigate("/gates")}>
          Add a gate
        </Button>
        <Button variant="secondary" onPress={() => navigate("/runs")}>
          View all runs
        </Button>
        <Button variant="ghost" onPress={() => window.open(README_URL, "_blank", "noopener")}>
          Set up .otari-gates.yml
        </Button>
      </div>
    </div>
  )
}
