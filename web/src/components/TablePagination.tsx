import { Button } from "@heroui/react"
import { FilterSelect } from "./FilterSelect"

const PAGE_SIZES = ["10", "20", "50", "100"]

export function TablePagination({
  page,
  pageSize,
  total,
  rowsOnPage,
  onPageChange,
  onPageSizeChange,
  isFetching,
  hasNextFallback,
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
  const first = total === 0 ? 0 : page * pageSize + 1
  const last = page * pageSize + rowsOnPage
  const hasNext = total === null ? Boolean(hasNextFallback) : last < total
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <span className="text-sm text-muted">
        {total === null ? `Rows ${first} to ${last}` : `${first} to ${last} of ${total}`}
        {isFetching ? " (updating)" : ""}
      </span>
      <div className="flex items-end gap-2">
        <div className="w-32">
          <FilterSelect
            label="Per page"
            value={String(pageSize)}
            onChange={(value) => onPageSizeChange(Number.parseInt(value, 10))}
            options={PAGE_SIZES.map((size) => ({ value: size, label: size }))}
          />
        </div>
        <Button variant="secondary" size="sm" isDisabled={page === 0} onPress={() => onPageChange(page - 1)}>
          Previous
        </Button>
        <Button variant="secondary" size="sm" isDisabled={!hasNext} onPress={() => onPageChange(page + 1)}>
          Next
        </Button>
      </div>
    </div>
  )
}
