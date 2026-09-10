import { ApiError } from "../api/client"

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail ?? `Request failed with HTTP ${error.status}`
  }
  if (error instanceof Error) return error.message
  return String(error)
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (error == null) return null
  return (
    <div
      role="alert"
      className="rounded-md border border-danger bg-danger-soft px-4 py-3 text-sm text-danger"
    >
      {describe(error)}
    </div>
  )
}
