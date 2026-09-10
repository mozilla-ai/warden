import { Spinner } from "@heroui/react"
import { useState } from "react"
import { useCreatePolicyCheckPolicy, useSaveGate } from "../api/hooks"
import type {
  CommandGateSpec,
  DeterministicGateSpec,
  EditedPathGateSpec,
  JudgeGateSpec,
  PolicyGateSpec,
} from "../api/types"
import { Field } from "../components/Field"
import { FormDialog } from "../components/FormDialog"
import { Select } from "../components/Select"
import { TextArea } from "../components/TextArea"

const NEW_POLICY = "__new__"

const GATE_TYPES = [
  { value: "deterministic", label: "Deterministic (transcript text)" },
  { value: "command", label: "Command (executed, not just discussed)" },
  { value: "scoped_guidance", label: "Scoped guidance (AGENTS.md loaded before editing)" },
  { value: "edited_path", label: "Edited path (which files changed)" },
  { value: "llm_judge", label: "LLM judge" },
]

function newGateOfType(type: string): PolicyGateSpec {
  switch (type) {
    case "deterministic":
      return { type: "deterministic", name: "", pattern: "", mode: "must_not_match", message: "" }
    case "command":
      return { type: "command", name: "", pattern: "", mode: "must_run_and_succeed", paths: null, message: "" }
    case "scoped_guidance":
      return { type: "scoped_guidance", name: "", directory: "", message: "" }
    case "edited_path":
      return { type: "edited_path", name: "", pattern: "", mode: "must_not_edit", message: "" }
    default:
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
}

// `paths` is edited as one comma-separated string; the wire shape is a list.
function parsePathsInput(value: string): string[] | null {
  const patterns = value
    .split(",")
    .map((pattern) => pattern.trim())
    .filter((pattern) => pattern !== "")
  return patterns.length > 0 ? patterns : null
}

const REQUIRED = "Required."

// Which fields are missing, keyed by field name. `rules_file` has no field on
// purpose: it resolves against the gateway process's working directory,
// which a browser cannot mean anything by.
function gateProblems(gate: PolicyGateSpec): Record<string, string> {
  const problems: Record<string, string> = {}
  if (gate.name.trim() === "") problems.name = REQUIRED
  if (gate.type === "deterministic" || gate.type === "command" || gate.type === "edited_path") {
    if (gate.pattern.trim() === "") problems.pattern = REQUIRED
  }
  if (gate.type === "scoped_guidance" && gate.directory.trim() === "") problems.directory = REQUIRED
  if (gate.type !== "llm_judge" && gate.message.trim() === "") problems.message = REQUIRED
  if (gate.type === "llm_judge") {
    if (!gate.rules?.trim()) problems.rules = REQUIRED
    if (gate.judge_backend === "provider" && !gate.judge_model?.trim()) problems.judge_model = REQUIRED
  }
  return problems
}

type Touched = Record<string, boolean>

function GateFields({
  gate,
  onChange,
  problems,
  touched,
  touch,
}: {
  gate: PolicyGateSpec
  onChange: (next: PolicyGateSpec) => void
  problems: Record<string, string>
  touched: Touched
  touch: (field: string) => void
}) {
  const error = (field: string) => (touched[field] ? problems[field] : undefined)
  const invalid = (field: string) => Boolean(error(field))
  return (
    <>
      <Select
        label="Gate type"
        value={gate.type}
        onChange={(value) => onChange(newGateOfType(value))}
        options={GATE_TYPES}
        reserveMessage={false}
      />
      <Field
        label="Gate name"
        value={gate.name}
        onChange={(value) => onChange({ ...gate, name: value })}
        onBlur={() => touch("name")}
        isRequired
        isInvalid={invalid("name")}
        errorMessage={error("name")}
        reserveMessage={false}
      />
      {gate.type === "deterministic" ? (
        <>
          <Field
            label="Pattern (regex)"
            value={gate.pattern}
            onChange={(value) => onChange({ ...gate, pattern: value })}
            onBlur={() => touch("pattern")}
            isRequired
            isInvalid={invalid("pattern")}
            errorMessage={error("pattern")}
            placeholder="git push --force"
            reserveMessage={false}
          />
          <Select
            label="Mode"
            value={gate.mode}
            onChange={(value) => onChange({ ...gate, mode: value as DeterministicGateSpec["mode"] })}
            options={[
              { value: "must_not_match", label: "Fails when the pattern is found" },
              { value: "must_match", label: "Fails when the pattern is absent" },
            ]}
            reserveMessage={false}
          />
        </>
      ) : gate.type === "command" ? (
        <>
          <Field
            label="Pattern (regex)"
            value={gate.pattern}
            onChange={(value) => onChange({ ...gate, pattern: value })}
            onBlur={() => touch("pattern")}
            isRequired
            isInvalid={invalid("pattern")}
            errorMessage={error("pattern")}
            placeholder="make lint"
            description="Matched against commands the transcript's own tool calls actually ran, not the rendered text. A command merely mentioned does not trip this gate."
          />
          <Select
            label="Mode"
            value={gate.mode}
            onChange={(value) => onChange({ ...gate, mode: value as CommandGateSpec["mode"] })}
            options={[
              { value: "must_run_and_succeed", label: "Fails unless a matching command ran and succeeded" },
              { value: "must_not_run", label: "Fails if a matching command ran at all" },
            ]}
            reserveMessage={false}
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
          onBlur={() => touch("directory")}
          isRequired
          isInvalid={invalid("directory")}
          errorMessage={error("directory")}
          placeholder="web/"
          description="Matched against an edited file's repo-relative path and against a loaded AGENTS.md or CLAUDE.md's path, for example 'web/' or 'src/gateway/'."
        />
      ) : gate.type === "edited_path" ? (
        <>
          <Field
            label="Pattern (regex)"
            value={gate.pattern}
            onChange={(value) => onChange({ ...gate, pattern: value })}
            onBlur={() => touch("pattern")}
            isRequired
            isInvalid={invalid("pattern")}
            errorMessage={error("pattern")}
            placeholder="CHANGELOG.md"
            description="Matched against the paths this turn's own Edit, Write, and NotebookEdit calls touched."
          />
          <Select
            label="Mode"
            value={gate.mode}
            onChange={(value) => onChange({ ...gate, mode: value as EditedPathGateSpec["mode"] })}
            options={[
              { value: "must_not_edit", label: "Fails if a matching path was edited" },
              { value: "must_edit", label: "Fails unless a matching path was edited" },
            ]}
            reserveMessage={false}
          />
        </>
      ) : (
        <>
          <Select
            label="Judge backend"
            value={gate.judge_backend}
            onChange={(value) => onChange({ ...gate, judge_backend: value as JudgeGateSpec["judge_backend"] })}
            options={[
              { value: "subscription", label: "Subscription: your logged-in claude CLI, free" },
              { value: "provider", label: "Provider: Otari's own provider credentials" },
            ]}
            reserveMessage={false}
          />
          {gate.judge_backend === "provider" ? (
            <Field
              label="Judge model"
              value={gate.judge_model ?? ""}
              onChange={(value) => onChange({ ...gate, judge_model: value })}
              onBlur={() => touch("judge_model")}
              isRequired
              isInvalid={invalid("judge_model")}
              errorMessage={error("judge_model")}
              placeholder="e.g. ollama:llama3.1"
              reserveMessage={false}
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
          <TextArea
            label="Rules"
            value={gate.rules ?? ""}
            onChange={(value) => onChange({ ...gate, rules: value })}
            onBlur={() => touch("rules")}
            isRequired
            isInvalid={invalid("rules")}
            errorMessage={error("rules")}
            placeholder="What must this turn have done to comply?"
            description="Free text the judge reads as the standard to check against."
          />
        </>
      )}
      {gate.type === "llm_judge" ? null : (
        <Field
          label="Violation message"
          value={gate.message}
          onChange={(value) => onChange({ ...gate, message: value })}
          onBlur={() => touch("message")}
          isRequired
          isInvalid={invalid("message")}
          errorMessage={error("message")}
          reserveMessage={false}
        />
      )}
    </>
  )
}

export function GateDialog({
  isOpen,
  onOpenChange,
  storedPolicyNames,
  fixedPolicyName,
  existingGate,
  existingGateIndex,
  isLoading = false,
}: {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  storedPolicyNames: string[]
  fixedPolicyName?: string
  existingGate?: PolicyGateSpec
  existingGateIndex?: number
  isLoading?: boolean
}) {
  const [target, setTarget] = useState(fixedPolicyName ?? storedPolicyNames[0] ?? NEW_POLICY)
  const [newPolicyName, setNewPolicyName] = useState("")
  const [gate, setGate] = useState<PolicyGateSpec>(existingGate ?? newGateOfType("deterministic"))
  const [touched, setTouched] = useState<Touched>({})

  const isNewPolicy = fixedPolicyName === undefined && target === NEW_POLICY
  const targetName = isNewPolicy ? newPolicyName : target
  const isEdit = existingGate !== undefined

  const create = useCreatePolicyCheckPolicy()
  const saveGate = useSaveGate()
  const mutation = isNewPolicy ? create : saveGate

  const problems = gateProblems(gate)
  if (isNewPolicy && newPolicyName.trim() === "") problems.policy = REQUIRED
  const isValid = Object.keys(problems).length === 0
  const touch = (field: string) => setTouched((current) => ({ ...current, [field]: true }))

  function submit() {
    if (!isValid) {
      // A submit with a missing field shows every message at once rather than
      // one per blur.
      setTouched(Object.fromEntries(Object.keys(problems).map((field) => [field, true])))
      return
    }
    if (isNewPolicy) {
      create.mutate(
        { name: newPolicyName.trim(), gates: [gate], on_unavailable: "block" },
        { onSuccess: () => onOpenChange(false) },
      )
    } else {
      saveGate.mutate(
        { policyName: targetName, gateIndex: existingGateIndex, gate },
        { onSuccess: () => onOpenChange(false) },
      )
    }
  }

  const isDirty = isEdit ? JSON.stringify(gate) !== JSON.stringify(existingGate) : gate.name !== "" || newPolicyName !== ""

  return (
    <FormDialog
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      title={isEdit ? `Edit ${existingGate.name}` : "New gate"}
      description={
        fixedPolicyName
          ? `In policy ${fixedPolicyName}. Gates run in order and the first failure stops the run.`
          : "A gate is one check a reviewed turn has to pass. Gates run in the order they were added, and the first failure stops the run."
      }
      submitLabel={isEdit ? "Save gate" : "Add gate"}
      onSubmit={submit}
      isPending={mutation.isPending}
      error={mutation.error}
      isDirty={isDirty}
    >
      {isLoading ? (
        <div className="flex items-center gap-2 py-6 text-sm text-muted">
          <Spinner size="sm" aria-hidden="true" /> Loading the gate…
        </div>
      ) : (
        <>
          {fixedPolicyName === undefined ? (
            <>
              <Select
                label="Policy"
                value={target}
                onChange={setTarget}
                options={[
                  ...storedPolicyNames.map((name) => ({ value: name, label: name })),
                  { value: NEW_POLICY, label: "Create a new policy" },
                ]}
                reserveMessage={false}
              />
              {isNewPolicy ? (
                <Field
                  label="Policy name"
                  value={newPolicyName}
                  onChange={setNewPolicyName}
                  onBlur={() => touch("policy")}
                  isRequired
                  isInvalid={touched.policy ? Boolean(problems.policy) : false}
                  errorMessage={touched.policy ? problems.policy : undefined}
                  autoFocus
                  reserveMessage={false}
                />
              ) : null}
            </>
          ) : null}
          <GateFields gate={gate} onChange={setGate} problems={problems} touched={touched} touch={touch} />
        </>
      )}
    </FormDialog>
  )
}
