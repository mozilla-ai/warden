import { Spinner } from "@heroui/react"
import { useState } from "react"
import { useDismissPolicyCheckHistoryEntry, usePolicyCheckPolicyDetail } from "../api/hooks"
import type { GateOutcome, PolicyCheckHistoryEntry } from "../api/types"
import { Chip } from "../components/Chip"
import { DataTable, type DataTableColumn } from "../components/DataTable"
import { ErrorBanner } from "../components/ErrorBanner"
import { RowAction, RowActionRow } from "../components/RowAction"
import { GateStatusChip, RunStatusChip, runStatus } from "../components/StatusChip"
import { formatOptionalCost, formatOptionalTokens, formatRelative } from "../helpers/format"

function Missing() {
  return <span className="text-subtle">—</span>
}

function Identifier({ value }: { value: string }) {
  return (
    <span className="block max-w-[10rem] truncate text-mono-caption" title={value}>
      {value}
    </span>
  )
}

// One gate's own result within a run, shown per gate so it is visible which
// gate caught something and which never ran because an earlier one failed.
function GateOutcomeRow({ gate }: { gate: GateOutcome }) {
  return (
    <div className="flex flex-col gap-1.5 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-emphasis">{gate.name}</span>
        <Chip>{gate.type}</Chip>
        <GateStatusChip passed={gate.passed} skipped={gate.skipped} />
      </div>
      {gate.violations.length > 0 ? (
        <ul className="list-inside list-disc text-sm">
          {gate.violations.map((violation) => (
            <li key={violation}>{violation}</li>
          ))}
        </ul>
      ) : null}
      {gate.guidance ? <p className="text-sm text-muted">{gate.guidance}</p> : null}
    </div>
  )
}

// The policy's current definition. Nothing snapshots a policy per run, so this
// may differ from what the run actually checked against.
function GatesYamlView({ policyName }: { policyName: string }) {
  const detail = usePolicyCheckPolicyDetail(policyName)
  if (detail.isPending) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted">
        <Spinner size="sm" aria-hidden="true" /> Loading {policyName}
      </div>
    )
  }
  if (detail.error || !detail.data) {
    return <ErrorBanner error={detail.error} />
  }
  return (
    <div className="flex flex-col gap-1">
      <p className="text-caption">
        {policyName}'s current definition. It may differ from what this run checked against if the policy has
        changed since, and a repo's own .otari-gates.yml is never stored here.
      </p>
      <pre className="overflow-x-auto border border-code-border bg-code-surface p-3 font-mono text-xs">
        {detail.data.yaml}
      </pre>
    </div>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex min-w-0 items-baseline gap-1">
      <span className="text-caption text-subtle">{label}</span>
      <span className="truncate text-mono-caption text-muted" title={value}>
        {value}
      </span>
    </span>
  )
}

export function HistoryDetail({ entry }: { entry: PolicyCheckHistoryEntry }) {
  const [showYaml, setShowYaml] = useState(false)
  const dismiss = useDismissPolicyCheckHistoryEntry()
  const hasGateBreakdown = entry.gates != null && entry.gates.length > 0
  const canDismiss = (entry.gave_up || !entry.compliant) && !entry.dismissed_at
  return (
    <div className="flex flex-col gap-4 px-4 py-4 text-sm">
      {hasGateBreakdown ? (
        <div className="flex flex-col gap-2">
          <span className="text-overline">Gates</span>
          <div className="flex flex-col divide-y divide-border-subtle border border-border bg-surface">
            {(entry.gates ?? []).map((gate) => (
              <GateOutcomeRow key={gate.name} gate={gate} />
            ))}
          </div>
        </div>
      ) : entry.violations.length > 0 ? (
        <div className="flex flex-col gap-1">
          <span className="text-overline">What got caught</span>
          <ul className="list-inside list-disc">
            {entry.violations.map((violation) => (
              <li key={violation}>{violation}</li>
            ))}
          </ul>
        </div>
      ) : (
        <span className="text-muted">No violations.</span>
      )}
      {!hasGateBreakdown && entry.guidance ? (
        <div className="flex flex-col gap-1">
          <span className="text-overline">Guidance given</span>
          <p>{entry.guidance}</p>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-x-6 gap-y-1">
        {entry.session_id ? <Meta label="Session" value={entry.session_id} /> : null}
        {entry.turn_id ? <Meta label="Turn" value={entry.turn_id} /> : null}
        {entry.branch ? <Meta label="Branch" value={entry.branch} /> : null}
        {entry.total_cost_usd != null || entry.total_input_tokens != null ? (
          <span
            className="inline-flex items-baseline gap-1"
            title="API-equivalent cost, not money spent: a subscription-backed judge gate runs on your existing Claude login."
          >
            <span className="text-caption text-subtle">Usage</span>
            <span className="text-mono-caption text-muted">
              {formatOptionalCost(entry.total_cost_usd)} ({formatOptionalTokens(entry.total_input_tokens)} in /{" "}
              {formatOptionalTokens(entry.total_output_tokens)} out)
            </span>
          </span>
        ) : null}
      </div>
      <ErrorBanner error={dismiss.error} />
      <div className="flex flex-col gap-3">
        <RowActionRow>
          {canDismiss ? (
            <RowAction isDisabled={dismiss.isPending} onPress={() => dismiss.mutate(entry.id)}>
              Dismiss
            </RowAction>
          ) : null}
          <RowAction onPress={() => setShowYaml((value) => !value)}>
            {showYaml ? "Hide gates YAML" : "View gates YAML"}
          </RowAction>
        </RowActionRow>
        {showYaml ? <GatesYamlView policyName={entry.policy_name} /> : null}
      </div>
    </div>
  )
}

export type RunColumn = "repo" | "branch" | "policy" | "session"

export function RunsTable({
  rows,
  isLoading,
  hide = [],
  expandedId,
  onToggle,
  emptyContent,
}: {
  rows: PolicyCheckHistoryEntry[]
  isLoading: boolean
  hide?: RunColumn[]
  expandedId: string | null
  onToggle: (id: string) => void
  emptyContent: string
}) {
  const hidden = new Set<RunColumn>(hide)
  const allColumns: DataTableColumn<PolicyCheckHistoryEntry>[] = [
    {
      id: "created_at",
      header: "When",
      isRowHeader: true,
      cell: (row) => <span className="whitespace-nowrap">{formatRelative(row.created_at)}</span>,
    },
    { id: "repo", header: "Repo", cell: (row) => row.repo ?? <Missing /> },
    { id: "branch", header: "Branch", cell: (row) => row.branch ?? <Missing /> },
    { id: "policy", header: "Policy", cell: (row) => row.policy_name },
    { id: "session", header: "Session", cell: (row) => (row.session_id ? <Identifier value={row.session_id} /> : <Missing />) },
    {
      id: "status",
      header: "Status",
      cell: (row) => (
        <RunStatusChip checked={row.checked} compliant={row.compliant} gaveUp={row.gave_up} dismissedAt={row.dismissed_at} />
      ),
    },
    {
      id: "violations",
      header: "Violations",
      align: "end",
      cell: (row) => <span className="text-mono-caption">{row.violations.length}</span>,
    },
  ]
  const columns = allColumns.filter((column) => !hidden.has(column.id as RunColumn))
  return (
    <DataTable
      ariaLabel="Policy check history"
      columns={columns}
      rows={rows}
      getRowKey={(row) => row.id}
      isLoading={isLoading}
      emptyContent={emptyContent}
      onRowAction={onToggle}
      detailKey={expandedId}
      renderDetail={(row) => <HistoryDetail entry={row} />}
    />
  )
}

function SessionOutcome({ latest, attemptCount }: { latest: PolicyCheckHistoryEntry; attemptCount: number }) {
  const status = runStatus({ checked: latest.checked, compliant: latest.compliant, gaveUp: latest.gave_up })
  const attemptWord = attemptCount === 1 ? "attempt" : "attempts"
  const message = latest.gave_up
    ? "the Stop hook gave up"
    : !latest.checked
      ? "the last attempt's judge was unreachable"
      : latest.compliant
        ? attemptCount > 1
          ? "converged to passing"
          : "passed on the first try"
        : "still failing"
  return (
    <div className="flex items-center gap-3 text-sm">
      <Chip tone={status.tone} title={status.title}>
        {status.label}
      </Chip>
      <span>
        {attemptCount} {attemptWord}, {message}
      </span>
    </div>
  )
}

function SessionTimelineStep({
  entry,
  attemptNumber,
  isLast,
}: {
  entry: PolicyCheckHistoryEntry
  attemptNumber: number
  isLast: boolean
}) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center border border-border bg-surface text-xs font-semibold">
          {attemptNumber}
        </span>
        {isLast ? null : <span className="w-px flex-1 bg-border" />}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2 pb-6">
        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          <span className="text-caption" title={entry.created_at}>
            {formatRelative(entry.created_at)}
          </span>
          <RunStatusChip
            checked={entry.checked}
            compliant={entry.compliant}
            gaveUp={entry.gave_up}
            dismissedAt={entry.dismissed_at}
          />
          <span className="text-caption">{entry.policy_name}</span>
        </div>
        <div className="border border-border bg-surface">
          <HistoryDetail entry={entry} />
        </div>
      </div>
    </div>
  )
}

// Scoped to one session, the runs read as the chronological story of a
// Stop-hook retry loop rather than a table: attempt 1 failed, attempt 2 fixed it.
export function SessionTimeline({ entries, isLoading }: { entries: PolicyCheckHistoryEntry[]; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted">
        <Spinner size="sm" aria-hidden="true" /> Loading…
      </div>
    )
  }
  if (entries.length === 0) {
    return <p className="py-4 text-sm text-muted">No attempts recorded yet for this session.</p>
  }
  const chronological = [...entries].reverse()
  return (
    <div className="flex flex-col gap-4">
      <SessionOutcome latest={entries[0]} attemptCount={entries.length} />
      <div className="flex flex-col">
        {chronological.map((entry, index) => (
          <SessionTimelineStep
            key={entry.id}
            entry={entry}
            attemptNumber={index + 1}
            isLast={index === chronological.length - 1}
          />
        ))}
      </div>
    </div>
  )
}
