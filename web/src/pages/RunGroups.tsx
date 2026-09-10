import { useState } from "react"
import {
  usePolicyCheckBranches,
  usePolicyCheckHistory,
  usePolicyCheckRepos,
  usePolicyCheckSessions,
} from "../api/hooks"
import type { BranchSummary, GroupSummary, RepoSummary, SessionSummary } from "../api/types"
import { DataTable, type DataTableColumn } from "../components/DataTable"
import { ErrorBanner } from "../components/ErrorBanner"
import { RunStatusChip } from "../components/StatusChip"
import { formatOptionalCost, formatOptionalTokens, formatRelative } from "../helpers/format"
import { type RunColumn, RunsTable, SessionTimeline } from "./RunsTable"

export type GroupKind = "session" | "repo" | "branch"

// One group's runs, under its row. A session is a retry loop and reads as a
// timeline; a repo or branch is a list, with the grouped column dropped.
function GroupRuns({ kind, value }: { kind: GroupKind; value: string }) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const filters = kind === "session" ? { sessionId: value } : kind === "repo" ? { repo: value } : { branch: value }
  const history = usePolicyCheckHistory(filters, 0, kind === "session" ? 200 : 50)
  const rows = history.data ?? []
  return (
    <div className="flex flex-col gap-3 px-4 py-4">
      <ErrorBanner error={history.error} />
      {kind === "session" ? (
        <SessionTimeline entries={rows} isLoading={history.isLoading} />
      ) : (
        <RunsTable
          rows={rows}
          isLoading={history.isLoading}
          hide={[kind as RunColumn]}
          expandedId={expandedId}
          onToggle={(id) => setExpandedId((current) => (current === id ? null : id))}
          emptyContent="No runs recorded."
        />
      )}
      {rows.length >= 50 && kind !== "session" ? (
        <p className="text-caption text-subtle">Showing the newest 50 runs. Filter the full list for the rest.</p>
      ) : null}
    </div>
  )
}

const LABEL: Record<GroupKind, string> = { session: "Session", repo: "Repo", branch: "Branch" }

const EMPTY: Record<GroupKind, string> = {
  session: "No sessions recorded yet. A check run without a session id does not appear here.",
  repo: "No repo-scoped runs recorded yet. A check run outside a git repo does not appear here.",
  branch: "No branch-scoped runs recorded yet. A check run outside a git repo does not appear here.",
}

function groupValue(kind: GroupKind, row: GroupSummary): string {
  if (kind === "session") return (row as SessionSummary).session_id
  if (kind === "repo") return (row as RepoSummary).repo
  return (row as BranchSummary).branch
}

export function RunGroups({ kind, initialOpen }: { kind: GroupKind; initialOpen?: string }) {
  const repos = usePolicyCheckRepos()
  const branches = usePolicyCheckBranches()
  const sessions = usePolicyCheckSessions()
  const query = kind === "session" ? sessions : kind === "repo" ? repos : branches
  const rows: GroupSummary[] = query.data ?? []
  const [expanded, setExpanded] = useState<string | null>(initialOpen ?? null)

  const columns: DataTableColumn<GroupSummary>[] = [
    {
      id: "group",
      header: LABEL[kind],
      isRowHeader: true,
      cell: (row) => {
        const value = groupValue(kind, row)
        return kind === "session" ? (
          <span className="block max-w-[10rem] truncate text-mono-caption" title={value}>
            {value}
          </span>
        ) : (
          <span className="text-emphasis">{value}</span>
        )
      },
    },
    ...(kind === "session"
      ? [
          {
            id: "repo",
            header: "Repo",
            cell: (row: GroupSummary) => (row as SessionSummary).repo ?? <span className="text-subtle">—</span>,
          },
          {
            id: "branch",
            header: "Branch",
            cell: (row: GroupSummary) => (row as SessionSummary).branch ?? <span className="text-subtle">—</span>,
          },
        ]
      : []),
    {
      id: "status",
      header: "Last run",
      cell: (row) => <RunStatusChip checked={row.last_checked} compliant={row.last_compliant} />,
    },
    { id: "last_policy_name", header: "Policy", cell: (row) => row.last_policy_name },
    { id: "run_count", header: "Runs", align: "end", cell: (row) => <span className="text-mono-caption">{row.run_count}</span> },
    {
      id: "total_cost_usd",
      header: (
        <span title="API-equivalent cost, not money spent: a subscription-backed judge gate runs on your existing Claude login.">
          Judge cost
        </span>
      ),
      align: "end",
      cell: (row) => <span className="text-mono-caption">{formatOptionalCost(row.total_cost_usd)}</span>,
    },
    {
      id: "tokens",
      header: <span title="Input / output tokens">Tokens</span>,
      align: "end",
      cell: (row) => (
        <span className="text-mono-caption">
          {formatOptionalTokens(row.total_input_tokens)} / {formatOptionalTokens(row.total_output_tokens)}
        </span>
      ),
    },
    { id: "last_run_at", header: "When", cell: (row) => <span className="whitespace-nowrap">{formatRelative(row.last_run_at)}</span> },
  ]

  return (
    <>
      <ErrorBanner error={query.error} />
      <DataTable
        ariaLabel={`Runs by ${LABEL[kind].toLowerCase()}`}
        columns={columns}
        rows={rows}
        getRowKey={(row) => groupValue(kind, row)}
        isLoading={query.isLoading}
        emptyContent={EMPTY[kind]}
        onRowAction={(key) => setExpanded((current) => (current === key ? null : key))}
        detailKey={expanded}
        renderDetail={(row) => <GroupRuns kind={kind} value={groupValue(kind, row)} />}
      />
    </>
  )
}
