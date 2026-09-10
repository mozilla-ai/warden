import { Button } from "@heroui/react"
import { useEffect, useRef, useState } from "react"
import {
  type PolicyCheckHistoryFilters,
  useDeleteOldPolicyCheckHistory,
  usePolicyCheckBranches,
  usePolicyCheckHistory,
  usePolicyCheckHistoryCount,
  usePolicyCheckRepos,
} from "../api/hooks"
import { ConfirmDialog } from "../components/ConfirmDialog"
import { ErrorBanner } from "../components/ErrorBanner"
import { Field } from "../components/Field"
import { FilterInput } from "../components/FilterInput"
import { FilterSelect } from "../components/FilterSelect"
import { RowAction } from "../components/RowAction"
import { Segmented } from "../components/Segmented"
import { TabIntro } from "../components/TabIntro"
import { PAGE_SIZE_OPTIONS, TablePagination } from "../components/TablePagination"
import { useUrlState } from "../helpers/urlState"
import { type GroupKind, RunGroups } from "./RunGroups"
import { RunsTable, SessionTimeline } from "./RunsTable"

const URL_DEFAULTS = {
  policy: "",
  session: "",
  repo: "",
  branch: "",
  status: "all",
  group: "none",
  page: "0",
  size: String(PAGE_SIZE_OPTIONS[0]),
}

const GROUP_OPTIONS = [
  { value: "none", label: "None" },
  { value: "session", label: "Session" },
  { value: "repo", label: "Repo" },
  { value: "branch", label: "Branch" },
]

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "compliant", label: "Passed" },
  { value: "non_compliant", label: "Failed" },
]

type ComplianceFilter = "all" | "compliant" | "non_compliant"

// A manual prune; nothing schedules one. Kept at the foot of the page as a
// quiet action, since it is the one thing here that destroys data.
function RetentionAction() {
  const [isOpen, setIsOpen] = useState(false)
  const [days, setDays] = useState("90")
  const deleteOld = useDeleteOldPolicyCheckHistory()
  const parsedDays = Number.parseInt(days, 10)
  const isValidCutoff = Number.isInteger(parsedDays) && parsedDays >= 1
  return (
    <div className="flex items-center justify-end gap-4">
      {deleteOld.data ? (
        <span className="text-caption text-subtle">
          Deleted {deleteOld.data.deleted} record{deleteOld.data.deleted === 1 ? "" : "s"}.
        </span>
      ) : null}
      <RowAction
        onPress={() => {
          deleteOld.reset()
          setIsOpen(true)
        }}
      >
        Delete old records
      </RowAction>
      <ConfirmDialog
        isOpen={isOpen}
        onOpenChange={setIsOpen}
        heading="Delete old records"
        body={
          <div className="flex flex-col gap-3">
            <p>
              Removes every run older than the cutoff, along with its share of the repo, branch and session
              summaries. Nothing schedules this; it runs once, now.
            </p>
            <Field
              label="Older than (days)"
              value={days}
              onChange={setDays}
              isInvalid={!isValidCutoff}
              errorMessage={isValidCutoff ? undefined : "Enter a whole number of days, 1 or more."}
              autoFocus
            />
          </div>
        }
        confirmLabel={isValidCutoff ? `Delete records older than ${days} days` : "Delete"}
        isConfirmDisabled={!isValidCutoff}
        isPending={deleteOld.isPending}
        error={deleteOld.error}
        onConfirm={() => {
          if (!isValidCutoff) return
          deleteOld.mutate(parsedDays, { onSuccess: () => setIsOpen(false) })
        }}
      />
    </div>
  )
}

export function RunsPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const url = useUrlState(URL_DEFAULTS)

  const policyNameFilter = url.get("policy")
  const sessionIdFilter = url.get("session")
  const repoFilter = url.get("repo")
  const branchFilter = url.get("branch")
  const complianceFilter = url.get("status") as ComplianceFilter
  const group = url.get("group")
  const page = Math.max(0, url.getNumber("page"))
  const pageSize = Math.max(1, url.getNumber("size"))

  const repos = usePolicyCheckRepos()
  const branches = usePolicyCheckBranches()

  function resetToFirstPage(updates: Partial<Record<keyof typeof URL_DEFAULTS, string>>) {
    url.patch({ ...updates, page: 0 })
  }

  const hasFilters = Boolean(policyNameFilter || sessionIdFilter || repoFilter || branchFilter || complianceFilter !== "all")
  const filters: PolicyCheckHistoryFilters = {
    policyName: policyNameFilter || undefined,
    sessionId: sessionIdFilter || undefined,
    repo: repoFilter || undefined,
    branch: branchFilter || undefined,
    compliant: complianceFilter === "all" ? undefined : complianceFilter === "compliant",
  }

  // One session's retry loop is small and bounded, so one large page covers it.
  const isSingleSessionView = Boolean(sessionIdFilter)
  const isGrouped = group !== "none"
  const history = usePolicyCheckHistory(filters, isSingleSessionView ? 0 : page, isSingleSessionView ? 200 : pageSize)
  const count = usePolicyCheckHistoryCount(filters)
  const rows = history.data ?? []

  // Arriving with a repo or branch filter means the point was to see that
  // run, so its detail opens at once; the ref keeps this to one time per load.
  const cameFromGroupFilter = Boolean(repoFilter || branchFilter)
  const hasAutoExpandedRef = useRef(false)
  useEffect(() => {
    if (cameFromGroupFilter && !hasAutoExpandedRef.current && !isSingleSessionView && !isGrouped && rows.length > 0) {
      hasAutoExpandedRef.current = true
      setExpandedId(rows[0].id)
    }
  }, [cameFromGroupFilter, isSingleSessionView, isGrouped, rows])

  const groupOpen = group === "repo" ? repoFilter : group === "branch" ? branchFilter : group === "session" ? sessionIdFilter : ""

  return (
    <>
      <TabIntro>
        Every reviewed turn, newest first, judged against a policy's gates. Expand a run to see each gate's own
        result, or group the runs to read a session's retry loop in order.
      </TabIntro>
      <ErrorBanner error={history.error ?? count.error} />
      <div className="otari-toolbar flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-caption">Group by</span>
          <Segmented
            label="Group by"
            value={group}
            onChange={(value) => resetToFirstPage({ group: value })}
            options={GROUP_OPTIONS}
          />
        </div>
        {isGrouped ? null : (
          <>
            <FilterSelect
              label="Repo"
              value={repoFilter}
              onChange={(value) => resetToFirstPage({ repo: value })}
              options={[{ value: "", label: "All repos" }, ...(repos.data ?? []).map((row) => ({ value: row.repo, label: row.repo }))]}
            />
            <FilterSelect
              label="Branch"
              value={branchFilter}
              onChange={(value) => resetToFirstPage({ branch: value })}
              options={[
                { value: "", label: "All branches" },
                ...(branches.data ?? []).map((row) => ({ value: row.branch, label: row.branch })),
              ]}
            />
            <FilterInput
              label="Policy"
              value={policyNameFilter}
              onChange={(value) => resetToFirstPage({ policy: value })}
              placeholder="Any policy"
            />
            <FilterInput
              label="Session"
              value={sessionIdFilter}
              onChange={(value) => resetToFirstPage({ session: value })}
              placeholder="Any session"
            />
            <FilterSelect
              label="Status"
              value={complianceFilter}
              onChange={(value) => resetToFirstPage({ status: value })}
              options={STATUS_OPTIONS}
            />
            {hasFilters ? (
              <Button
                size="sm"
                variant="ghost"
                onPress={() => resetToFirstPage({ policy: "", session: "", repo: "", branch: "", status: "all" })}
              >
                Clear
              </Button>
            ) : null}
          </>
        )}
      </div>
      {isGrouped ? (
        <RunGroups key={group} kind={group as GroupKind} initialOpen={groupOpen || undefined} />
      ) : isSingleSessionView ? (
        <SessionTimeline entries={rows} isLoading={history.isLoading} />
      ) : (
        <>
          <RunsTable
            rows={rows}
            isLoading={history.isLoading}
            expandedId={expandedId}
            onToggle={(id) => setExpandedId((current) => (current === id ? null : id))}
            emptyContent={hasFilters ? "No runs match these filters." : "No runs recorded yet."}
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
      <RetentionAction />
    </>
  )
}
