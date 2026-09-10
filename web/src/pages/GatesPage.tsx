import { Button } from "@heroui/react"
import { useState } from "react"
import {
  useDeletePolicyCheckPolicy,
  usePolicyCheckPolicies,
  usePolicyCheckPolicyDetail,
  useSaveGate,
} from "../api/hooks"
import type { ConfiguredPolicySummary, PolicyGateSummary } from "../api/types"
import { Chip } from "../components/Chip"
import { ConfirmDialog } from "../components/ConfirmDialog"
import { DataTable, type DataTableColumn } from "../components/DataTable"
import { EmptyState } from "../components/EmptyState"
import { ErrorBanner } from "../components/ErrorBanner"
import { RowAction, RowActionRow } from "../components/RowAction"
import { TabIntro } from "../components/TabIntro"
import { GateDialog } from "./GateDialog"

const DESCRIPTION =
  "Gates an agent's session gets judged against, grouped into policies. A repo's own .otari-gates.yml never appears here; it needs no registration at all. This page is for a policy with no repo to carry a file, or one meant to apply across many repos."

function GateRow({
  gate,
  onEdit,
  onDelete,
}: {
  gate: PolicyGateSummary
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
      <span className="text-emphasis">{gate.name}</span>
      <Chip>{gate.type}</Chip>
      {gate.judge_backend ? <Chip>{gate.judge_backend}</Chip> : null}
      {gate.judge_model ? <span className="text-mono-caption text-muted">{gate.judge_model}</span> : null}
      <div className="ml-auto">
        <RowActionRow>
          <RowAction onPress={onEdit}>Edit</RowAction>
          <RowAction isDanger onPress={onDelete}>
            Delete
          </RowAction>
        </RowActionRow>
      </div>
    </div>
  )
}

type FormState =
  | { kind: "closed" }
  | { kind: "new-gate" }
  | { kind: "add-gate"; policyName: string }
  | { kind: "edit-gate"; policyName: string; index: number }

type PendingDelete = { kind: "policy"; policyName: string } | { kind: "gate"; policyName: string; index: number; gateName: string }

// The full spec loads only once Edit is pressed; the list rows carry summaries.
function EditGateDialog({
  policyName,
  index,
  storedPolicyNames,
  onOpenChange,
}: {
  policyName: string
  index: number
  storedPolicyNames: string[]
  onOpenChange: (open: boolean) => void
}) {
  const detail = usePolicyCheckPolicyDetail(policyName)
  return (
    <GateDialog
      key={detail.data ? "loaded" : "loading"}
      isOpen
      onOpenChange={onOpenChange}
      storedPolicyNames={storedPolicyNames}
      fixedPolicyName={policyName}
      existingGate={detail.data?.gates[index]}
      existingGateIndex={index}
      isLoading={detail.isPending}
    />
  )
}

export function GatesPage() {
  const policies = usePolicyCheckPolicies()
  const deletePolicy = useDeletePolicyCheckPolicy()
  const saveGate = useSaveGate()
  const [expandedName, setExpandedName] = useState<string | null>(null)
  const [formState, setFormState] = useState<FormState>({ kind: "closed" })
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null)

  const rows = policies.data ?? []
  const storedPolicyNames = rows.map((row) => row.name)
  const closeForm = (open: boolean) => {
    if (!open) setFormState({ kind: "closed" })
  }
  const openDelete = (pending: PendingDelete) => {
    deletePolicy.reset()
    saveGate.reset()
    setPendingDelete(pending)
  }

  const columns: DataTableColumn<ConfiguredPolicySummary>[] = [
    { id: "name", header: "Policy", isRowHeader: true, cell: (row) => <span className="text-emphasis">{row.name}</span> },
    { id: "gates", header: "Gates", align: "end", cell: (row) => <span className="text-mono-caption">{row.gates.length}</span> },
    { id: "on_unavailable", header: "On unavailable", cell: (row) => <Chip>{row.on_unavailable}</Chip> },
    {
      id: "actions",
      header: "Actions",
      align: "end",
      cell: (row) => (
        <RowActionRow>
          <RowAction onPress={() => setFormState({ kind: "add-gate", policyName: row.name })}>Add gate</RowAction>
          <RowAction isDanger onPress={() => openDelete({ kind: "policy", policyName: row.name })}>
            Delete
          </RowAction>
        </RowActionRow>
      ),
    },
  ]

  const deleteBody =
    pendingDelete?.kind === "policy"
      ? `${pendingDelete.policyName} and every gate in it are removed from this gateway. Runs already recorded against it stay in the history.`
      : pendingDelete
        ? rows.find((row) => row.name === pendingDelete.policyName)?.gates.length === 1
          ? `${pendingDelete.gateName} is the only gate in ${pendingDelete.policyName}, so removing it deletes the policy too. Runs already recorded stay in the history.`
          : `${pendingDelete.gateName} is removed from ${pendingDelete.policyName}. Runs already recorded against it stay in the history.`
        : null

  const isDeleting = deletePolicy.isPending || saveGate.isPending

  return (
    <>
      <TabIntro
        action={
          <Button variant="primary" onPress={() => setFormState({ kind: "new-gate" })}>
            New gate
          </Button>
        }
      >
        {DESCRIPTION}
      </TabIntro>
      <ErrorBanner error={policies.error} />
      {!policies.isLoading && rows.length === 0 ? (
        <EmptyState
          title="No policies yet"
          description="A policy is a named list of gates, run in order against each reviewed turn. Add the first gate to create one."
          actionLabel="New gate"
          onAction={() => setFormState({ kind: "new-gate" })}
        />
      ) : (
        <DataTable
          ariaLabel="Configured policies"
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.name}
          isLoading={policies.isLoading}
          emptyContent="No policies yet."
          onRowAction={(key) => setExpandedName((current) => (current === key ? null : key))}
          detailKey={expandedName}
          renderDetail={(row) => (
            <div className="flex flex-col divide-y divide-border-subtle">
              {row.gates.map((gate, index) => (
                <GateRow
                  key={`${gate.name}-${index}`}
                  gate={gate}
                  onEdit={() => setFormState({ kind: "edit-gate", policyName: row.name, index })}
                  onDelete={() => openDelete({ kind: "gate", policyName: row.name, index, gateName: gate.name })}
                />
              ))}
            </div>
          )}
        />
      )}

      {formState.kind === "new-gate" ? (
        <GateDialog isOpen onOpenChange={closeForm} storedPolicyNames={storedPolicyNames} />
      ) : null}
      {formState.kind === "add-gate" ? (
        <GateDialog
          isOpen
          onOpenChange={closeForm}
          storedPolicyNames={storedPolicyNames}
          fixedPolicyName={formState.policyName}
        />
      ) : null}
      {formState.kind === "edit-gate" ? (
        <EditGateDialog
          key={`${formState.policyName}-${formState.index}`}
          policyName={formState.policyName}
          index={formState.index}
          storedPolicyNames={storedPolicyNames}
          onOpenChange={closeForm}
        />
      ) : null}

      <ConfirmDialog
        isOpen={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
        heading={pendingDelete?.kind === "policy" ? "Delete policy" : "Delete gate"}
        body={deleteBody}
        confirmLabel={pendingDelete?.kind === "policy" ? "Delete policy" : "Delete gate"}
        isPending={isDeleting}
        error={deletePolicy.error ?? saveGate.error}
        onConfirm={() => {
          if (!pendingDelete) return
          const onSuccess = () => setPendingDelete(null)
          if (pendingDelete.kind === "policy") {
            deletePolicy.mutate(pendingDelete.policyName, { onSuccess })
          } else {
            saveGate.mutate({ policyName: pendingDelete.policyName, gateIndex: pendingDelete.index, gate: null }, { onSuccess })
          }
        }}
      />
    </>
  )
}
