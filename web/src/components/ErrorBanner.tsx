import { ApiError } from "../api/client"

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail ?? `Request failed with HTTP ${error.status}`
  }
  if (error instanceof Error) return error.message
  return "Something went wrong."
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (error == null) return null
  return (
    <div role="alert" className="border border-danger bg-danger-subtle px-4 py-3 text-sm text-danger">
      {describe(error)}
    </div>
  )
}
