// Every call is same-origin and rides the dashboard session cookie: the page
// is iframed by the dashboard, so no token is ever handled here.
const API_PREFIX = "/api/v1/plugins/warden"

export class ApiError extends Error {
  readonly status: number
  readonly detail: string | null

  constructor(status: number, detail: string | null) {
    super(detail ?? `Request failed with HTTP ${status}`)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

async function readDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json()
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail
      if (typeof detail === "string") return detail
      return JSON.stringify(detail)
    }
  } catch {
    // A non-JSON error body has nothing to quote.
  }
  return null
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set("Accept", "application/json")
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  })
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}
