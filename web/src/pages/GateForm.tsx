import { Button, Description, Label, TextArea, TextField } from "@heroui/react"
import { useState } from "react"
import { useCreatePolicyCheckPolicy, useSaveGate } from "../api/hooks"
import type {
  CommandGateSpec,
  DeterministicGateSpec,
  EditedPathGateSpec,
  JudgeGateSpec,
  PolicyGateSpec,
  ScopedGuidanceGateSpec,
} from "../api/types"
import { ErrorBanner } from "../components/ErrorBanner"
import { Field } from "../components/Field"
import { FilterSelect } from "../components/FilterSelect"

const NEW_POLICY = "__new__"

function newDeterministicGate(): DeterministicGateSpec {
  return { type: "deterministic", name: "", pattern: "", mode: "must_not_match", message: "" }
}

function newCommandGate(): CommandGateSpec {
  return { type: "command", name: "", pattern: "", mode: "must_run_and_succeed", paths: null, message: "" }
}

// `paths` is edited as one comma-separated string; the wire shape is a list.
function parsePathsInput(value: string): string[] | null {
  const patterns = value
    .split(",")
    .map((pattern) => pattern.trim())
    .filter((pattern) => pattern !== "")
  return patterns.length > 0 ? patterns : null
}

function newScopedGuidanceGate(): ScopedGuidanceGateSpec {
  return { type: "scoped_guidance", name: "", directory: "", message: "" }
}

function newEditedPathGate(): EditedPathGateSpec {
  return { type: "edited_path", name: "", pattern: "", mode: "must_not_edit", message: "" }
}

function newJudgeGate(): JudgeGateSpec {
  return {
    type: "llm_judge",
    name: "",
    judge_backend: "subscription",
    judge_model: null,
    rules: "",
    rules_file: null,
    max_transcript_chars: 24_000,
    judge_max_tokens: 600,
  }
}

function newGateOfType(type: string): PolicyGateSpec {
  switch (type) {
    case "deterministic":
      return newDeterministicGate()
    case "command":
      return newCommandGate()
    case "scoped_guidance":
      return newScopedGuidanceGate()
    case "edited_path":
      return newEditedPathGate()
    default:
      return newJudgeGate()
  }
}

// `rules_file` has no field on purpose: it resolves against the gateway
// process's working directory, which a browser cannot mean anything by.
function isGateValid(gate: PolicyGateSpec): boolean {
  if (gate.type === "deterministic" || gate.type === "command" || gate.type === "edited_path") {
    return gate.name.trim() !== "" && gate.pattern.trim() !== "" && gate.message.trim() !== ""
  }
  if (gate.type === "scoped_guidance") {
    return gate.name.trim() !== "" && gate.directory.trim() !== "" && gate.message.trim() !== ""
  }
  const hasModel = gate.judge_backend === "subscription" || Boolean(gate.judge_model?.trim())
  return gate.name.trim() !== "" && Boolean(gate.rules?.trim()) && hasModel
}

function MessageField({ gate, onChange }: { gate: PolicyGateSpec; onChange: (next: PolicyGateSpec) => void }) {
  if (gate.type === "llm_judge") return null
  return (
    <Field
      label="Violation message"
      value={gate.message}
      onChange={(value) => onChange({ ...gate, message: value })}
      isRequired
    />
  )
}

function GateFields({ gate, onChange }: { gate: PolicyGateSpec; onChange: (next: PolicyGateSpec) => void }) {
  return (
    <>
      <FilterSelect
        label="Gate type"
        value={gate.type}
        onChange={(value) => onChange(newGateOfType(value))}
        options={[
          { value: "deterministic", label: "Deterministic (transcript text)" },
          { value: "command", label: "Command (executed, not just discussed)" },
          { value: "scoped_guidance", label: "Scoped guidance (AGENTS.md loaded before editing)" },
          { value: "edited_path", label: "Edited path (which files changed)" },
          { value: "llm_judge", label: "LLM judge" },
        ]}
      />
      <Field label="Gate name" value={gate.name} onChange={(value) => onChange({ ...gate, name: value })} isRequired />
      {gate.type === "deterministic" ? (
        <>
          <Field
            label="Pattern (regex)"
            value={gate.pattern}
            onChange={(value) => onChange({ ...gate, pattern: value })}
            isRequired
            placeholder="git push --force"
          />
          <FilterSelect
            label="Mode"
            value={gate.mode}
            onChange={(value) => onChange({ ...gate, mode: value as DeterministicGateSpec["mode"] })}
            options={[
              { value: "must_not_match", label: "Fails when the pattern is found" },
              { value: "must_match", label: "Fails when the pattern is absent" },
            ]}
          />
        </>
      ) : gate.type === "command" ? (
        <>
          <Field
            label="Pattern (regex)"
            value={gate.pattern}
            onChange={(value) => onChange({ ...gate, pattern: value })}
            isRequired
            placeholder="make lint"
            description="Matched against commands the transcript's own tool calls actually ran, not the rendered text. A command merely mentioned does not trip this gate."
          />
          <FilterSelect
            label="Mode"
            value={gate.mode}
            onChange={(value) => onChange({ ...gate, mode: value as CommandGateSpec["mode"] })}
            options={[
              { value: "must_run_and_succeed", label: "Fails unless a matching command ran and succeeded" },
              { value: "must_not_run", label: "Fails if a matching command ran at all" },
            ]}
          />
          <Field
            label="Only when these paths changed (optional)"
            value={gate.paths?.join(", ") ?? ""}
            onChange={(value) => onChange({ ...gate, paths: parsePathsInput(value) })}
            placeholder="web/*"
            description="Leave blank to require the command every turn. Comma-separated shell-style globs matched against repo-relative paths; 'web/*' means anywhere under web/."
          />
        </>
      ) : gate.type === "scoped_guidance" ? (
        <Field
          label="Directory"
          value={gate.directory}
          onChange={(value) => onChange({ ...gate, directory: value })}
          isRequired
          placeholder="web/"
          description="Matched against an edited file's repo-relative path and against a loaded AGENTS.md or CLAUDE.md's path, for example 'web/' or 'src/gateway/'."
        />
      ) : gate.type === "edited_path" ? (
        <>
          <Field
            label="Pattern (regex)"
            value={gate.pattern}
            onChange={(value) => onChange({ ...gate, pattern: value })}
            isRequired
            placeholder="CHANGELOG.md"
            description="Matched against the paths this turn's own Edit, Write, and NotebookEdit calls touched."
          />
          <FilterSelect
            label="Mode"
            value={gate.mode}
            onChange={(value) => onChange({ ...gate, mode: value as EditedPathGateSpec["mode"] })}
            options={[
              { value: "must_not_edit", label: "Fails if a matching path was edited" },
              { value: "must_edit", label: "Fails unless a matching path was edited" },
            ]}
          />
        </>
      ) : (
        <>
          <FilterSelect
            label="Judge backend"
            value={gate.judge_backend}
            onChange={(value) => onChange({ ...gate, judge_backend: value as JudgeGateSpec["judge_backend"] })}
            options={[
              { value: "subscription", label: "Subscription: your logged-in claude CLI, free" },
              { value: "provider", label: "Provider: Otari's own provider credentials" },
            ]}
          />
          {gate.judge_backend === "provider" ? (
            <Field
              label="Judge model"
              value={gate.judge_model ?? ""}
              onChange={(value) => onChange({ ...gate, judge_model: value })}
              isRequired
              placeholder="e.g. ollama:llama3.1"
            />
          ) : (
            <Field
              label="Model (optional)"
              value={gate.judge_model ?? ""}
              onChange={(value) => onChange({ ...gate, judge_model: value || null })}
              placeholder="Default: a small model (haiku)"
              description="Passed as the local claude CLI's own --model flag. Judging one rule rarely needs the full model."
            />
          )}
          <TextField
            value={gate.rules ?? ""}
            onChange={(value) => onChange({ ...gate, rules: value })}
            isRequired
            className="flex w-full max-w-md flex-col gap-1"
          >
            <Label className="text-sm text-foreground">Rules</Label>
            <TextArea rows={4} placeholder="What must this turn have done to comply?" />
            <Description className="text-xs text-muted">
              Free text the judge reads as the standard to check against.
            </Description>
          </TextField>
        </>
      )}
      <MessageField gate={gate} onChange={onChange} />
    </>
  )
}

export function GateForm({
  storedPolicyNames,
  fixedPolicyName,
  existingGate,
  existingGateIndex,
  onClose,
}: {
  storedPolicyNames: string[]
  fixedPolicyName?: string
  existingGate?: PolicyGateSpec
  existingGateIndex?: number
  onClose: () => void
}) {
  const [target, setTarget] = useState(fixedPolicyName ?? storedPolicyNames[0] ?? NEW_POLICY)
  const [newPolicyName, setNewPolicyName] = useState("")
  const [gate, setGate] = useState<PolicyGateSpec>(existingGate ?? newDeterministicGate())

  const isNewPolicy = fixedPolicyName === undefined && target === NEW_POLICY
  const targetName = isNewPolicy ? newPolicyName : target

  const create = useCreatePolicyCheckPolicy()
  const saveGate = useSaveGate()
  const mutation = isNewPolicy ? create : saveGate
  const canSubmit = targetName.trim() !== "" && isGateValid(gate)

  function submit() {
    if (isNewPolicy) {
      create.mutate({ name: newPolicyName, gates: [gate], on_unavailable: "block" }, { onSuccess: onClose })
    } else {
      saveGate.mutate({ policyName: targetName, gateIndex: existingGateIndex, gate }, { onSuccess: onClose })
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-md border border-border bg-surface p-4">
      {fixedPolicyName === undefined ? (
        <>
          <FilterSelect
            label="Policy"
            value={target}
            onChange={setTarget}
            options={[
              ...storedPolicyNames.map((name) => ({ value: name, label: name })),
              { value: NEW_POLICY, label: "Create a new policy" },
            ]}
          />
          {isNewPolicy ? (
            <Field label="New policy name" value={newPolicyName} onChange={setNewPolicyName} isRequired autoFocus />
          ) : null}
        </>
      ) : null}
      <GateFields gate={gate} onChange={setGate} />
      <ErrorBanner error={mutation.error} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" isDisabled={mutation.isPending} onPress={onClose}>
          Cancel
        </Button>
        <Button variant="primary" isDisabled={!canSubmit} isPending={mutation.isPending} onPress={submit}>
          {existingGate ? "Save gate" : "Add gate"}
        </Button>
      </div>
    </div>
  )
}
