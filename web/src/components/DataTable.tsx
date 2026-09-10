import { Spinner, Table } from "@heroui/react"
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, ReactNode } from "react"
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { FiChevronRight } from "react-icons/fi"
import { EmptyMessage } from "./EmptyMessage"

export interface DataTableColumn<Row> {
  id: string
  header: ReactNode
  cell: (row: Row) => ReactNode
  align?: "start" | "end"
  isRowHeader?: boolean
  width?: number
  minWidth?: number
}

function hasTextSelectionIn(root: HTMLElement | null): boolean {
  if (!root) return false
  const selection = document.getSelection()
  if (!selection || selection.isCollapsed || selection.toString().trim() === "") return false
  return selection.anchorNode !== null && root.contains(selection.anchorNode)
}

// The dashboard's DataTable: a HeroUI table under the `.otari-table`
// treatment the dashboard stylesheet carries, with an expandable detail row.
// The detail row lives outside react-aria's collection (a plain <tr> inserted
// after the open row and filled through a portal), which is what lets it span
// every column without becoming a row the grid navigates.
export function DataTable<Row extends object>({
  ariaLabel,
  columns,
  rows,
  getRowKey,
  isLoading = false,
  emptyContent = "No rows.",
  onRowAction,
  detailKey = null,
  renderDetail,
}: {
  ariaLabel: string
  columns: DataTableColumn<Row>[]
  rows: Row[]
  getRowKey: (row: Row) => string
  isLoading?: boolean
  emptyContent?: ReactNode
  onRowAction?: (key: string) => void
  detailKey?: string | null
  renderDetail?: (row: Row) => ReactNode
}) {
  const expandable = Boolean(onRowAction && renderDetail)
  const allColumns = useMemo<DataTableColumn<Row>[]>(
    () =>
      expandable
        ? [
            ...columns,
            {
              id: "expand",
              header: <span className="sr-only">Details</span>,
              align: "end",
              width: 40,
              cell: (row) => (
                <FiChevronRight
                  aria-hidden="true"
                  className={`inline-block size-4 text-subtle transition-transform duration-150 ease-out motion-reduce:transition-none ${
                    getRowKey(row) === detailKey ? "rotate-90" : ""
                  }`}
                />
              ),
            },
          ]
        : columns,
    [columns, expandable, getRowKey, detailKey],
  )
  const columnCount = allColumns.length

  const rootRef = useRef<HTMLDivElement | null>(null)
  const [detailHost, setDetailHost] = useState<HTMLTableCellElement | null>(null)
  const detailRow = useMemo(
    () => (detailKey != null && renderDetail ? (rows.find((r) => getRowKey(r) === detailKey) ?? null) : null),
    [detailKey, renderDetail, rows, getRowKey],
  )

  const hostRef = useRef<{ row: HTMLTableRowElement; cell: HTMLTableCellElement } | null>(null)
  const ensureHost = useCallback(() => {
    if (!hostRef.current) {
      const row = document.createElement("tr")
      row.className = "otari-detail-row"
      row.setAttribute("role", "presentation")
      const cell = document.createElement("td")
      row.appendChild(cell)
      hostRef.current = { row, cell }
    }
    return hostRef.current
  }, [])

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root || detailKey == null || !detailRow) {
      hostRef.current?.row.remove()
      setDetailHost(null)
      return
    }
    const { row: hostRow, cell: hostCell } = ensureHost()
    hostCell.colSpan = columnCount

    const tryInsert = (): boolean => {
      const target = root.querySelector(`tbody tr[data-key="${CSS.escape(detailKey)}"]`)
      if (!target) return false
      for (const el of root.querySelectorAll(".otari-detail-opening")) el.classList.remove("otari-detail-opening")
      if (target.nextSibling !== hostRow) target.after(hostRow)
      setDetailHost(hostCell)
      return true
    }

    let observer: MutationObserver | null = null
    if (!tryInsert()) {
      observer = new MutationObserver(() => {
        if (tryInsert()) {
          observer?.disconnect()
          observer = null
        }
      })
      observer.observe(root, { childList: true, subtree: true })
    }
    return () => observer?.disconnect()
  }, [detailKey, detailRow, columnCount, ensureHost])

  useEffect(() => () => hostRef.current?.row.remove(), [])

  const fireRowAction = useCallback(
    (key: string) => {
      if (!onRowAction) return
      if (renderDetail && key !== detailKey) {
        const target = rootRef.current?.querySelector(`tbody tr[data-key="${CSS.escape(key)}"]`)
        target?.classList.add("otari-detail-opening")
        setTimeout(() => target?.classList.remove("otari-detail-opening"), 1500)
      }
      onRowAction(key)
    },
    [onRowAction, renderDetail, detailKey],
  )

  // A click on a control inside a cell, or anywhere inside the detail row, is
  // not a row press. Everything else on a data row is.
  const dataCellRowKey = useCallback(
    (e: { target: EventTarget | null }): string | null => {
      if (!onRowAction) return null
      const target = e.target instanceof Element ? e.target : null
      if (!target) return null
      if (target.closest("button, a, input, select, textarea, label, .otari-detail-row")) return null
      return target.closest("tbody tr[data-key]")?.getAttribute("data-key") ?? null
    },
    [onRowAction],
  )

  const renderRow = useCallback(
    (row: Row) => {
      const key = getRowKey(row)
      return (
        <Table.Row key={key} id={key}>
          {allColumns.map((col) => (
            <Table.Cell key={col.id} className={col.align === "end" ? "text-right tabular-nums" : undefined}>
              {col.cell(row)}
            </Table.Cell>
          ))}
        </Table.Row>
      )
    },
    [getRowKey, allColumns],
  )

  return (
    <Table.Root ref={rootRef} className="otari-table">
      <Table.ScrollContainer
        className="overflow-x-auto"
        onPointerDownCapture={(e: ReactPointerEvent) => {
          if (dataCellRowKey(e) != null) e.stopPropagation()
        }}
        onMouseDownCapture={(e: ReactMouseEvent) => {
          if (dataCellRowKey(e) != null) e.stopPropagation()
        }}
        onClickCapture={(e: ReactMouseEvent) => {
          const key = dataCellRowKey(e)
          if (key == null) return
          e.stopPropagation()
          if (!hasTextSelectionIn(rootRef.current)) fireRowAction(key)
        }}
      >
        <Table.Content
          aria-label={ariaLabel}
          className="w-full text-sm"
          selectionMode="none"
          onRowAction={onRowAction ? (key) => fireRowAction(String(key)) : undefined}
        >
          <Table.Header>
            {allColumns.map((col) => (
              <Table.Column
                key={col.id}
                id={col.id}
                isRowHeader={col.isRowHeader}
                width={col.width}
                minWidth={col.minWidth}
                className={col.align === "end" ? "text-right" : undefined}
              >
                <div className={`flex items-center gap-1 whitespace-nowrap ${col.align === "end" ? "justify-end" : ""}`}>
                  <span>{col.header}</span>
                </div>
              </Table.Column>
            ))}
          </Table.Header>
          <Table.Body
            items={isLoading && rows.length === 0 ? [] : rows}
            dependencies={[renderRow]}
            renderEmptyState={() => (
              <EmptyMessage>
                {isLoading ? (
                  <span className="inline-flex items-center gap-2">
                    <Spinner size="sm" aria-hidden="true" /> Loading…
                  </span>
                ) : (
                  emptyContent
                )}
              </EmptyMessage>
            )}
          >
            {renderRow}
          </Table.Body>
        </Table.Content>
      </Table.ScrollContainer>
      {detailHost && detailRow && renderDetail
        ? createPortal(
            <div key={detailKey} className="otari-detail-reveal">
              <div>{renderDetail(detailRow)}</div>
            </div>,
            detailHost,
          )
        : null}
    </Table.Root>
  )
}
