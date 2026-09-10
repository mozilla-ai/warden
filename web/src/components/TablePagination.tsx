import { Button, Spinner } from "@heroui/react"
import { useEffect, useId, useState } from "react"
import { FilterSelect } from "./FilterSelect"

export const PAGE_SIZE_OPTIONS = [25, 50, 100]

// Range, page size and bare arrows, the way the dashboard ends a table page.
export function TablePagination({
  page,
  pageSize,
  total,
  rowsOnPage,
  onPageChange,
  onPageSizeChange,
  isFetching = false,
  hasNextFallback = false,
}: {
  page: number
  pageSize: number
  total: number | null
  rowsOnPage: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
  isFetching?: boolean
  // Whether a next page may exist when the count has not loaded.
  hasNextFallback?: boolean
}) {
  const sizeSelectId = useId()
  const pageCount = total != null ? Math.max(1, Math.ceil(total / pageSize)) : null
  const isFirst = page === 0
  const isLast = pageCount != null ? page >= pageCount - 1 : !hasNextFallback

  const rangeStart = rowsOnPage > 0 ? page * pageSize + 1 : 0
  const rangeEnd = page * pageSize + rowsOnPage
  const summary =
    total != null
      ? total === 0
        ? "0 of 0"
        : `${rangeStart}–${rangeEnd} of ${total}`
      : rowsOnPage > 0
        ? `${rangeStart}–${rangeEnd}`
        : "0"

  const [pageText, setPageText] = useState(String(page + 1))
  useEffect(() => {
    setPageText(String(page + 1))
  }, [page])

  const commitPage = () => {
    const parsed = Number.parseInt(pageText, 10)
    if (Number.isNaN(parsed)) {
      setPageText(String(page + 1))
      return
    }
    const upper = pageCount ?? Number.MAX_SAFE_INTEGER
    const clamped = Math.min(Math.max(parsed, 1), upper)
    if (clamped - 1 !== page) {
      onPageChange(clamped - 1)
    } else {
      setPageText(String(page + 1))
    }
  }

  return (
    <div className="otari-pagination flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <label htmlFor={sizeSelectId} className="text-sm text-muted">
          Rows
        </label>
        <FilterSelect
          id={sizeSelectId}
          ariaLabel="Rows per page"
          value={String(pageSize)}
          onChange={(value) => onPageSizeChange(Number.parseInt(value, 10))}
          options={PAGE_SIZE_OPTIONS.map((size) => ({ value: String(size), label: String(size) }))}
        />
        {isFetching ? <Spinner size="sm" aria-hidden="true" /> : null}
      </div>
      <div className="flex items-center gap-3">
        <span role="status" aria-live="polite" className="text-sm text-muted tabular-nums">
          {summary}
        </span>
        <div className="otari-pagination__pager flex items-center gap-1">
          <Button size="sm" variant="ghost" aria-label="First page" isDisabled={isFirst} onPress={() => onPageChange(0)}>
            «
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label="Previous page"
            isDisabled={isFirst}
            onPress={() => onPageChange(page - 1)}
          >
            ‹
          </Button>
          <span className="inline-flex items-center gap-1 text-sm text-muted">
            <input
              aria-label="Page number"
              inputMode="numeric"
              value={pageText}
              onChange={(event) => setPageText(event.target.value.replace(/[^0-9]/g, ""))}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur()
              }}
              onBlur={commitPage}
              className="input input--primary min-h-10 w-12 text-center text-sm tabular-nums"
            />
            {pageCount != null ? <span className="tabular-nums">/ {pageCount}</span> : null}
          </span>
          <Button size="sm" variant="ghost" aria-label="Next page" isDisabled={isLast} onPress={() => onPageChange(page + 1)}>
            ›
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label="Last page"
            isDisabled={pageCount == null || isLast}
            onPress={() => pageCount != null && onPageChange(pageCount - 1)}
          >
            »
          </Button>
        </div>
      </div>
    </div>
  )
}
