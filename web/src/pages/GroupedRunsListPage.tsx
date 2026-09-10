import { Link } from "react-router"
import type { GroupSummary } from "../api/types"
import { DataTable, type DataTableColumn } from "../components/DataTable"
import { ErrorBanner } from "../components/ErrorBanner"
import { PageHeader } from "../components/PageHeader"
import { RunStatusMark } from "../components/StatusMark"
import { formatOptionalCost, formatOptionalTokens, formatRelative } from "../helpers/format"

// Repos, branches, and sessions are the same page grouped by a different
// column, so the columns and layout are defined once here.
export function GroupedRunsListPage<T extends GroupSummary>({
  title,
  description,
  ariaLabel,
  emptyContent,
  rows,
  isLoading,
  error,
  groupLabel,
  getGroupValue,
  historySearchParam,
}: {
  title: string
  description: string
  ariaLabel: string
  emptyContent: string
  rows: T[]
  isLoading: boolean
  error: unknown
  groupLabel: string
  getGroupValue: (row: T) => string
  historySearchParam: "repo" | "branch" | "session"
}) {
  const runsLink = (row: T) => `/runs?${historySearchParam}=${encodeURIComponent(getGroupValue(row))}`
  const columns: DataTableColumn<T>[] = [
    {
      id: "group",
      header: groupLabel,
      isRowHeader: true,
      cell: (row) => (
        <Link to={runsLink(row)} className="font-medium underline underline-offset-2">
          {getGroupValue(row)}
        </Link>
      ),
    },
    {
      id: "status",
      header: "Last run",
      cell: (row) => (
        <Link to={runsLink(row)} className="inline-block">
          <RunStatusMark checked={row.last_checked} compliant={row.last_compliant} />
        </Link>
      ),
    },
    { id: "last_policy_name", header: "Last policy", cell: (row) => row.last_policy_name },
    { id: "run_count", header: "Runs", align: "end", cell: (row) => `${row.run_count}` },
    {
      id: "total_cost_usd",
      header: (
        <span title="API-equivalent cost, not money spent: a subscription-backend judge gate runs on your existing Claude login.">
          Total cost
        </span>
      ),
      align: "end",
      cell: (row) => formatOptionalCost(row.total_cost_usd),
    },
    {
      id: "total_tokens",
      header: "Tokens (in / out)",
      align: "end",
      cell: (row) =>
        `${formatOptionalTokens(row.total_input_tokens)} / ${formatOptionalTokens(row.total_output_tokens)}`,
    },
    { id: "last_run_at", header: "Last run at", cell: (row) => formatRelative(row.last_run_at) },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={title} description={description} />
      <ErrorBanner error={error} />
      <DataTable
        ariaLabel={ariaLabel}
        columns={columns}
        rows={rows}
        getRowKey={getGroupValue}
        isLoading={isLoading}
        emptyContent={emptyContent}
      />
    </div>
  )
}
