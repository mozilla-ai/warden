import { Button, Chip, Spinner } from "@heroui/react"
import { useEffect, useRef, useState } from "react"
import {
  type PolicyCheckHistoryFilters,
  useDeleteOldPolicyCheckHistory,
  useDismissPolicyCheckHistoryEntry,
  usePolicyCheckHistory,
  usePolicyCheckHistoryCount,
  usePolicyCheckPolicyDetail,
} from "../api/hooks"
import type { GateOutcome, PolicyCheckHistoryEntry } from "../api/types"
import { ConfirmButton } from "../components/ConfirmButton"
import { DataTable, type DataTableColumn } from "../components/DataTable"
import { ErrorBanner } from "../components/ErrorBanner"
import { Field } from "../components/Field"
import { FilterSelect } from "../components/FilterSelect"
import { PageHeader } from "../components/PageHeader"
import { StatusMark } from "../components/StatusMark"
import { TablePagination } from "../components/TablePagination"
import { formatOptionalCost, formatOptionalTokens, formatRelative } from "../helpers/format"
import { useUrlState } from "../helpers/urlState"

const DEFAULT_PAGE_SIZE = 20

const URL_DEFAULTS = {
  policy: "",
  session: "",
  repo: "",
  branch: "",
  status: "all",
  page: "0",
  size: String(DEFAULT_PAGE_SIZE),
}

function ComplianceStatusMark({ row }: { row: PolicyCheckHistoryEntry }) {
  const mark = row.gave_up ? (
    <StatusMark
      state="failure"
      label="Gave up"
      title="The Stop hook's retry-attempt cap was reached; the session ended without a final passing check."
    />
  ) : !row.checked ? (
    <StatusMark
      state="neutral"
      label="Unverified"
      title="The judge was unreachable; reported passing only because the policy's on_unavailable is monitor."
    />
  ) : (
    <StatusMark state={row.compliant ? "success" : "failure"} label={row.compliant ? "Passed" : "Failed"} />
  )
  if (!row.dismissed_at) return mark
  return (
    <span className="inline-flex items-center gap-1.5">
      {mark}
      <Chip size="sm" color="default" title={`Dismissed ${formatRelative(row.dismissed_at)}`}>
        Dismissed
      </Chip>
    </span>
  )
}

// One gate's own result within a run, shown per gate so it is visible which
// gate caught something and which never ran because an earlier one failed.
function GateOutcomeRow({ gate }: { gate: GateOutcome }) {
  const state = gate.skipped ? "neutral" : gate.passed ? "success" : "failure"
  const label = gate.skipped ? "Skipped" : gate.passed ? "Passed" : "Failed"
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{gate.name}</span>
        <Chip size="sm" color="default">
          {gate.type}
        </Chip>
        <StatusMark state={state} label={label} />
      </div>
      {gate.violations.length > 0 ? (
        <ul className="ml-3.5 list-inside list-disc">
          {gate.violations.map((violation) => (
            <li key={violation}>{violation}</li>
          ))}
        </ul>
      ) : null}
      {gate.guidance ? <p className="ml-3.5">{gate.guidance}</p> : null}
    </div>
  )
}

// The policy's current definition. Nothing snapshots a policy per run, so this
// may differ from what the run actually checked against.
function GatesYamlView({ policyName }: { policyName: string }) {
  const detail = usePolicyCheckPolicyDetail(policyName)
  if (detail.isPending) {
    return (
      <div className="flex items-center gap-2">
        <Spinner size="sm" /> Loading {policyName}
      </div>
    )
  }
  if (detail.error || !detail.data) {
    return <ErrorBanner error={detail.error} />
  }
  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs text-muted">
        {policyName}'s current definition. It may differ from what this run checked against if
        the policy has changed since, and a repo's own .otari-gates.yml is never stored here.
      </p>
      <pre className="overflow-x-auto rounded-md border border-border bg-surface p-3 font-mono text-xs">
        {detail.data.yaml}
      </pre>
    </div>
  )
}

function DismissButton({ entry }: { entry: PolicyCheckHistoryEntry }) {
  const dismiss = useDismissPolicyCheckHistoryEntry()
  const isAProblem = entry.gave_up || !entry.compliant
  if (!isAProblem || entry.dismissed_at) return null
  return (
    <Button variant="ghost" size="sm" isDisabled={dismiss.isPending} onPress={() => dismiss.mutate(entry.id)}>
      Dismiss
    </Button>
  )
}

function HistoryDetail({ entry }: { entry: PolicyCheckHistoryEntry }) {
  const [showYaml, setShowYaml] = useState(false)
  const hasGateBreakdown = entry.gates != null && entry.gates.length > 0
  return (
    <div className="flex flex-col gap-3 px-4 py-3 text-sm">
      {hasGateBreakdown ? (
        <div className="flex flex-col gap-2">
          <span className="font-medium">Gates</span>
          {(entry.gates ?? []).map((gate) => (
            <GateOutcomeRow key={gate.name} gate={gate} />
          ))}
        </div>
      ) : entry.violations.length > 0 ? (
        <div className="flex flex-col gap-1">
          <span className="font-medium">What got caught</span>
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
          <span className="font-medium">Guidance given</span>
          <p>{entry.guidance}</p>
        </div>
      ) : null}
      {entry.session_id ? <div className="text-xs text-muted">Session: {entry.session_id}</div> : null}
      {entry.turn_id ? <div className="text-xs text-muted">Turn: {entry.turn_id}</div> : null}
      {entry.branch ? <div className="text-xs text-muted">Branch: {entry.branch}</div> : null}
      {entry.total_cost_usd != null || entry.total_input_tokens != null ? (
        <div
          className="text-xs text-muted"
          title="API-equivalent cost, not money spent: a subscription-backend judge gate runs on your existing Claude login."
        >
          Usage: {formatOptionalCost(entry.total_cost_usd)} ({formatOptionalTokens(entry.total_input_tokens)} in /{" "}
          {formatOptionalTokens(entry.total_output_tokens)} out)
        </div>
      ) : null}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onPress={() => setShowYaml((value) => !value)}>
            {showYaml ? "Hide" : "View"} gates YAML
          </Button>
          <DismissButton entry={entry} />
        </div>
        {showYaml ? <GatesYamlView policyName={entry.policy_name} /> : null}
      </div>
    </div>
  )
}

// Full literal class strings per tone: Tailwind only ships classes it can see
// written out in the source.
const OUTCOME_TONE_CLASSES = {
  success: "border-success bg-success-soft text-success",
  danger: "border-danger bg-danger-soft text-danger",
  warning: "border-warning bg-warning-soft text-warning",
} as const

function SessionOutcomeBanner({
  latest,
  attemptCount,
}: {
  latest: PolicyCheckHistoryEntry
  attemptCount: number
}) {
  const attemptWord = attemptCount === 1 ? "attempt" : "attempts"
  const tone = !latest.checked ? "warning" : latest.compliant ? "success" : "danger"
  const message = !latest.checked
    ? "the last attempt's judge was unreachable"
    : latest.compliant
      ? attemptCount > 1
        ? "converged to passing"
        : "passed on the first try"
      : "still failing"
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm font-medium ${OUTCOME_TONE_CLASSES[tone]}`}>
      {attemptCount} {attemptWord}, {message}
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
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-xs font-semibold">
          {attemptNumber}
        </span>
        {isLast ? null : <span className="w-px flex-1 bg-border" />}
      </div>
      <div className="flex flex-1 flex-col gap-2 pb-6">
        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          <span className="text-xs text-muted" title={entry.created_at}>
            {formatRelative(entry.created_at)}
          </span>
          <ComplianceStatusMark row={entry} />
          <span className="text-xs text-muted">{entry.policy_name}</span>
        </div>
        <div className="rounded-md border border-border bg-surface">
          <HistoryDetail entry={entry} />
        </div>
      </div>
    </div>
  )
}

// Scoped to one session, the page reads as a chronological story of a Stop-hook
// retry loop rather than a table: attempt 1 failed, attempt 2 fixed it.
function SessionTimeline({ entries, isLoading }: { entries: PolicyCheckHistoryEntry[]; isLoading: boolean }) {
  if (isLoading) return <Spinner size="sm" />
  if (entries.length === 0) {
    return <p className="text-muted">No attempts recorded yet for this session.</p>
  }
  const chronological = [...entries].reverse()
  return (
    <div className="flex flex-col gap-4">
      <SessionOutcomeBanner latest={entries[0]} attemptCount={entries.length} />
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

// A manual prune; nothing schedules one.
function RetentionControl() {
  const [days, setDays] = useState("90")
  const deleteOld = useDeleteOldPolicyCheckHistory()
  const parsedDays = Number.parseInt(days, 10)
  const isValidCutoff = Number.isInteger(parsedDays) && parsedDays >= 1
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-md border border-border p-3">
      <Field
        label="Delete records older than (days)"
        value={days}
        onChange={setDays}
        placeholder="90"
        isInvalid={!isValidCutoff}
        errorMessage={isValidCutoff ? undefined : "Enter a whole number of days, 1 or more."}
      />
      <ConfirmButton
        confirmLabel={isValidCutoff ? `Delete records older than ${days} days` : "Delete"}
        isPending={deleteOld.isPending}
        onConfirm={() => {
          if (isValidCutoff) deleteOld.mutate(parsedDays)
        }}
      >
        Clear old records
      </ConfirmButton>
      <ErrorBanner error={deleteOld.error} />
      {deleteOld.data ? (
        <span className="text-xs text-muted">
          Deleted {deleteOld.data.deleted} record{deleteOld.data.deleted === 1 ? "" : "s"}.
        </span>
      ) : null}
    </div>
  )
}

type ComplianceFilter = "all" | "compliant" | "non_compliant"

export function RunsPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const url = useUrlState(URL_DEFAULTS)

  const policyNameFilter = url.get("policy")
  const sessionIdFilter = url.get("session")
  const repoFilter = url.get("repo")
  const branchFilter = url.get("branch")
  const complianceFilter = url.get("status") as ComplianceFilter
  const page = Math.max(0, url.getNumber("page"))
  const pageSize = Math.max(1, url.getNumber("size"))

  function resetToFirstPage(updates: Partial<Record<keyof typeof URL_DEFAULTS, string>>) {
    url.patch({ ...updates, page: 0 })
  }

  const filters: PolicyCheckHistoryFilters = {
    policyName: policyNameFilter || undefined,
    sessionId: sessionIdFilter || undefined,
    repo: repoFilter || undefined,
    branch: branchFilter || undefined,
    compliant: complianceFilter === "all" ? undefined : complianceFilter === "compliant",
  }

  // One session's retry loop is small and bounded, so one large page covers it.
  const isSingleSessionView = Boolean(sessionIdFilter)
  const effectivePage = isSingleSessionView ? 0 : page
  const effectivePageSize = isSingleSessionView ? 200 : pageSize

  const history = usePolicyCheckHistory(filters, effectivePage, effectivePageSize)
  const count = usePolicyCheckHistoryCount(filters)
  const rows = history.data ?? []

  // Arriving from a repo or branch's "Last run" link means the point was to see
  // that run, so its detail opens at once; the ref keeps this to one time per load.
  const cameFromGroupFilter = Boolean(repoFilter || branchFilter)
  const hasAutoExpandedRef = useRef(false)
  useEffect(() => {
    if (cameFromGroupFilter && !hasAutoExpandedRef.current && !isSingleSessionView && rows.length > 0) {
      hasAutoExpandedRef.current = true
      setExpandedId(rows[0].id)
    }
  }, [cameFromGroupFilter, isSingleSessionView, rows])

  const columns: DataTableColumn<PolicyCheckHistoryEntry>[] = [
    { id: "created_at", header: "When", isRowHeader: true, cell: (row) => formatRelative(row.created_at) },
    { id: "repo", header: "Repo", cell: (row) => row.repo ?? <span className="text-muted">—</span> },
    { id: "branch", header: "Branch", cell: (row) => row.branch ?? <span className="text-muted">—</span> },
    { id: "policy_name", header: "Policy", cell: (row) => row.policy_name },
    {
      id: "session_id",
      header: "Session",
      cell: (row) => row.session_id ?? <span className="text-muted">—</span>,
    },
    { id: "status", header: "Status", cell: (row) => <ComplianceStatusMark row={row} /> },
    { id: "violations", header: "Violations", align: "end", cell: (row) => `${row.violations.length}` },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Runs"
        description="Every reviewed turn, newest first, judged against a policy's gates. Expand a run to see each gate's own result."
      />
      <ErrorBanner error={history.error ?? count.error} />
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Repo" value={repoFilter} onChange={(value) => resetToFirstPage({ repo: value })} placeholder="Filter by repo" />
        <Field label="Branch" value={branchFilter} onChange={(value) => resetToFirstPage({ branch: value })} placeholder="Filter by branch" />
        <Field label="Policy" value={policyNameFilter} onChange={(value) => resetToFirstPage({ policy: value })} placeholder="Filter by policy name" />
        <Field label="Session" value={sessionIdFilter} onChange={(value) => resetToFirstPage({ session: value })} placeholder="Filter by session id" />
        <FilterSelect
          label="Status"
          value={complianceFilter}
          onChange={(value) => resetToFirstPage({ status: value })}
          options={[
            { value: "all", label: "All statuses" },
            { value: "compliant", label: "Passed only" },
            { value: "non_compliant", label: "Failed only" },
          ]}
        />
      </div>
      <RetentionControl />
      {isSingleSessionView ? (
        <SessionTimeline entries={rows} isLoading={history.isLoading} />
      ) : (
        <>
          <DataTable
            ariaLabel="Policy check history"
            columns={columns}
            rows={rows}
            getRowKey={(row) => row.id}
            isLoading={history.isLoading}
            emptyContent="No policy checks recorded yet."
            onRowAction={(key) => setExpandedId((current) => (current === key ? null : key))}
            detailKey={expandedId}
            renderDetail={(row) => <HistoryDetail entry={row} />}
          />
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={count.data?.total ?? null}
            rowsOnPage={rows.length}
            onPageChange={(next) => url.patch({ page: next })}
            onPageSizeChange={(size) => url.patch({ size, page: 0 })}
            isFetching={history.isFetching}
            hasNextFallback={rows.length === pageSize}
          />
        </>
      )}
    </div>
  )
}
