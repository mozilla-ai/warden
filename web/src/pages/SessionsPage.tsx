import { usePolicyCheckSessions } from "../api/hooks"
import type { SessionSummary } from "../api/types"
import { GroupedRunsListPage } from "./GroupedRunsListPage"

export function SessionsPage() {
  const sessions = usePolicyCheckSessions()
  return (
    <GroupedRunsListPage<SessionSummary>
      title="Sessions"
      description="Every Claude Code session that has recorded a check, newest run first. Open a session to see its attempts in order: a Stop-hook retry loop's own story, converged or not."
      ariaLabel="Sessions"
      emptyContent="No sessions recorded yet. A check run without a session id does not appear here."
      rows={sessions.data ?? []}
      isLoading={sessions.isLoading}
      error={sessions.error}
      groupLabel="Session"
      getGroupValue={(row) => row.session_id}
      historySearchParam="session"
    />
  )
}
