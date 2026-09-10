import { Button, Chip, Spinner } from "@heroui/react"
import { useState } from "react"
import {
  useDeletePolicyCheckPolicy,
  usePolicyCheckPolicies,
  usePolicyCheckPolicyDetail,
  useSaveGate,
} from "../api/hooks"
import type { ConfiguredPolicySummary, PolicyGateSummary } from "../api/types"
import { ConfirmButton } from "../components/ConfirmButton"
import { DataTable, type DataTableColumn } from "../components/DataTable"
import { ErrorBanner } from "../components/ErrorBanner"
import { PageHeader } from "../components/PageHeader"
import { GateForm } from "./GateForm"

function GateRow({
  gate,
  onEdit,
  onDelete,
  isDeleting,
}: {
  gate: PolicyGateSummary
  onEdit: () => void
  onDelete: () => void
  isDeleting: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 py-1.5 text-sm">
      <span className="font-medium">{gate.name}</span>
      <Chip size="sm" color="default">
        {gate.type}
      </Chip>
      {gate.judge_backend ? (
        <Chip size="sm" color="default">
          {gate.judge_backend}
        </Chip>
      ) : null}
      {gate.judge_model ? <span className="text-muted">{gate.judge_model}</span> : null}
      <div className="ml-auto flex items-center gap-1.5">
        <Button variant="ghost" size="sm" onPress={onEdit}>
          Edit
        </Button>
        <ConfirmButton confirmLabel="Delete" isPending={isDeleting} onConfirm={onDelete}>
          Delete
        </ConfirmButton>
      </div>
    </div>
  )
}

function PolicyDetail({
  policy,
  onEditGate,
  onDeleteGate,
  isDeletingGate,
}: {
  policy: ConfiguredPolicySummary
  onEditGate: (index: number) => void
  onDeleteGate: (index: number) => void
  isDeletingGate: boolean
}) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3">
      {policy.gates.map((gate, index) => (
        <GateRow
          key={`${gate.name}-${index}`}
          gate={gate}
          onEdit={() => onEditGate(index)}
          onDelete={() => onDeleteGate(index)}
          isDeleting={isDeletingGate}
        />
      ))}
    </div>
  )
}

// The full spec loads only once Edit is pressed; the list rows carry summaries.
function EditGateForm({
  policyName,
  index,
  storedPolicyNames,
  onClose,
}: {
  policyName: string
  index: number
  storedPolicyNames: string[]
  onClose: () => void
}) {
  const detail = usePolicyCheckPolicyDetail(policyName)
  if (detail.isPending) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-border p-4">
        <Spinner size="sm" /> Loading {policyName}
      </div>
    )
  }
  if (detail.error || !detail.data) {
    return <ErrorBanner error={detail.error} />
  }
  return (
    <GateForm
      storedPolicyNames={storedPolicyNames}
      fixedPolicyName={policyName}
      existingGate={detail.data.gates[index]}
      existingGateIndex={index}
      onClose={onClose}
    />
  )
}

type FormState =
  | { kind: "closed" }
  | { kind: "new-gate" }
  | { kind: "add-gate"; policyName: string }
  | { kind: "edit-gate"; policyName: string; index: number }

export function GatesPage() {
  const policies = usePolicyCheckPolicies()
  const deletePolicy = useDeletePolicyCheckPolicy()
  const saveGate = useSaveGate()
  const [expandedName, setExpandedName] = useState<string | null>(null)
  const [formState, setFormState] = useState<FormState>({ kind: "closed" })

  const rows = policies.data ?? []
  const storedPolicyNames = rows.map((row) => row.name)

  function closeForm() {
    setFormState({ kind: "closed" })
  }

  const columns: DataTableColumn<ConfiguredPolicySummary>[] = [
    { id: "name", header: "Policy", isRowHeader: true, cell: (row) => <span className="font-medium">{row.name}</span> },
    { id: "gates", header: "Gates", cell: (row) => `${row.gates.length}` },
    {
      id: "on_unavailable",
      header: "On unavailable",
      cell: (row) => (
        <Chip size="sm" color="default">
          {row.on_unavailable}
        </Chip>
      ),
    },
    {
      id: "actions",
      header: "Actions",
      cell: (row) => (
        <div className="flex items-center gap-1.5" onClick={(event) => event.stopPropagation()}>
          <Button variant="ghost" size="sm" onPress={() => setFormState({ kind: "add-gate", policyName: row.name })}>
            Add gate
          </Button>
          <ConfirmButton
            confirmLabel="Delete"
            isPending={deletePolicy.isPending}
            onConfirm={() => deletePolicy.mutate(row.name)}
          >
            Delete
          </ConfirmButton>
        </div>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Gates"
        description="Gates an agent's session gets judged against, grouped into policies. A repo's own .otari-gates.yml never appears here; it needs no registration at all. This page is for a policy with no repo to carry a file, or one meant to apply across many repos."
        action={
          <Button variant="primary" onPress={() => setFormState({ kind: "new-gate" })}>
            New gate
          </Button>
        }
      />
      <ErrorBanner error={policies.error ?? deletePolicy.error ?? saveGate.error} />
      {formState.kind === "new-gate" ? (
        <GateForm storedPolicyNames={storedPolicyNames} onClose={closeForm} />
      ) : null}
      {formState.kind === "add-gate" ? (
        <GateForm storedPolicyNames={storedPolicyNames} fixedPolicyName={formState.policyName} onClose={closeForm} />
      ) : null}
      {formState.kind === "edit-gate" ? (
        <EditGateForm
          key={`${formState.policyName}-${formState.index}`}
          policyName={formState.policyName}
          index={formState.index}
          storedPolicyNames={storedPolicyNames}
          onClose={closeForm}
        />
      ) : null}
      <DataTable
        ariaLabel="Configured policies"
        columns={columns}
        rows={rows}
        getRowKey={(row) => row.name}
        isLoading={policies.isLoading}
        emptyContent="No policies yet. Add a gate above to create one."
        onRowAction={(key) => setExpandedName((current) => (current === key ? null : key))}
        detailKey={expandedName}
        renderDetail={(row) => (
          <PolicyDetail
            policy={row}
            onEditGate={(index) => setFormState({ kind: "edit-gate", policyName: row.name, index })}
            onDeleteGate={(index) => saveGate.mutate({ policyName: row.name, gateIndex: index, gate: null })}
            isDeletingGate={saveGate.isPending}
          />
        )}
      />
    </div>
  )
}
