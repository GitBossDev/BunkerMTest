export type ExportFormat = 'csv' | 'txt'

export interface ExportColumn<T> {
  header: string
  value: (row: T) => unknown
}

/**
 * Export an array of records to CSV or TXT and trigger a browser download.
 *
 * CSV  — RFC 4180 with quoted fields; first row is the header.
 * TXT  — one entry per line; fields separated by " | ".
 */
export function exportLogs<T>(
  rows: T[],
  format: ExportFormat,
  columns: ExportColumn<T>[],
  filenameBase: string
): void {
  const ts = new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '-')
  const filename = `${filenameBase}-${ts}.${format}`

  let content: string
  if (format === 'csv') {
    const header = columns.map(c => csvCell(c.header)).join(',')
    const lines = rows.map(row =>
      columns.map(c => csvCell(String(c.value(row) ?? ''))).join(',')
    )
    content = [header, ...lines].join('\n')
  } else {
    content = rows
      .map(row => columns.map(c => `${c.header}: ${c.value(row) ?? ''}`).join(' | '))
      .join('\n')
  }

  download(content, filename, format === 'csv' ? 'text/csv;charset=utf-8' : 'text/plain;charset=utf-8')
}

function csvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`
}

function download(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
