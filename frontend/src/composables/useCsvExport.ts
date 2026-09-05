export function useCsvExport() {
  function exportCsv(filename: string, headers: string[], rows: (string | number)[][]) {
    const BOM = '﻿' // UTF-8 BOM for Excel
    const lines = [
      headers.join(','),
      ...rows.map((row) =>
        row
          .map((cell) => {
            const str = String(cell)
            // 如果包含逗号、引号或换行，用引号包裹
            return str.includes(',') || str.includes('"') || str.includes('\n')
              ? `"${str.replace(/"/g, '""')}"`
              : str
          })
          .join(','),
      ),
    ]
    const csv = BOM + lines.join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return { exportCsv }
}
