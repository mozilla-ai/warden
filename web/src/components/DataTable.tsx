import { Spinner } from "@heroui/react"
import { Fragment, type ReactNode } from "react"

export interface DataTableColumn<T> {
  id: string
  header: ReactNode
  cell: (row: T) => ReactNode
  align?: "start" | "end"
  isRowHeader?: boolean
}

export function DataTable<T>({
  ariaLabel,
  columns,
  rows,
  getRowKey,
  isLoading,
  emptyContent,
  onRowAction,
  detailKey,
  renderDetail,
}: {
  ariaLabel: string
  columns: DataTableColumn<T>[]
  rows: T[]
  getRowKey: (row: T) => string
  isLoading?: boolean
  emptyContent?: ReactNode
  onRowAction?: (key: string) => void
  detailKey?: string | null
  renderDetail?: (row: T) => ReactNode
}) {
  const expandable = Boolean(onRowAction && renderDetail)
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table aria-label={ariaLabel} className="w-full text-sm">
        <thead className="bg-surface-secondary text-xs uppercase tracking-wide text-muted">
          <tr>
            {columns.map((column) => (
              <th
                key={column.id}
                scope="col"
                className={`px-4 py-2 font-medium ${column.align === "end" ? "text-right" : "text-left"}`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-6 text-center">
                <Spinner size="sm" />
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-6 text-center text-muted">
                {emptyContent ?? "Nothing to show."}
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const key = getRowKey(row)
              const expanded = expandable && detailKey === key
              return (
                <Fragment key={key}>
                  <tr
                    className={`border-t border-border ${expandable ? "cursor-pointer hover:bg-surface-secondary" : ""} ${expanded ? "bg-surface-secondary" : ""}`}
                    onClick={expandable ? () => onRowAction?.(key) : undefined}
                    onKeyDown={
                      expandable
                        ? (event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault()
                              onRowAction?.(key)
                            }
                          }
                        : undefined
                    }
                    tabIndex={expandable ? 0 : undefined}
                    aria-expanded={expandable ? expanded : undefined}
                  >
                    {columns.map((column) => {
                      const className = `px-4 py-2 align-top ${column.align === "end" ? "text-right" : "text-left"}`
                      return column.isRowHeader ? (
                        <th key={column.id} scope="row" className={`${className} font-normal`}>
                          {column.cell(row)}
                        </th>
                      ) : (
                        <td key={column.id} className={className}>
                          {column.cell(row)}
                        </td>
                      )
                    })}
                  </tr>
                  {expanded ? (
                    <tr className="border-t border-border">
                      <td colSpan={columns.length} className="p-0">
                        {renderDetail?.(row)}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
