import { Badge } from '@/components/ui/badge'

function parseMarkdownTable(markdown) {
  if (!markdown) return null
  const lines = markdown.trim().split('\n').filter(l => l.trim())
  if (lines.length < 2) return null

  const parseRow = (line) =>
    line.split('|').map(cell => cell.trim()).filter((_, i, arr) =>
      // Remove empty first/last cells from leading/trailing pipes
      !(i === 0 && arr[0] === '') && !(i === arr.length - 1 && arr[arr.length - 1] === '')
    )

  const headers = parseRow(lines[0])
  // Skip separator line (line with dashes)
  const startIdx = lines[1]?.match(/^[\s|:-]+$/) ? 2 : 1
  const rows = lines.slice(startIdx).map(parseRow)

  return { headers, rows }
}

export default function TableRenderer({ table }) {
  const parsed = parseMarkdownTable(table.content_markdown)

  return (
    <div className="rounded-lg overflow-x-auto border border-warm-200">
      {(table.caption || table.num_rows != null) && (
        <div className="px-3 py-1.5 bg-warm-100 border-b border-warm-200 flex items-center gap-2">
          {table.caption && (
            <span className="text-xs text-warm-600 italic truncate">{table.caption}</span>
          )}
          <span className="ml-auto flex gap-2 shrink-0">
            {table.num_rows != null && table.num_cols != null && (
              <Badge variant="outline" className="text-warm-500 border-warm-200 text-[10px]">
                {table.num_rows} × {table.num_cols}
              </Badge>
            )}
          </span>
        </div>
      )}

      {parsed ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-warm-100">
                {parsed.headers.map((h, i) => (
                  <th key={i} className="px-3 py-2 text-left text-warm-600 font-medium border-b border-warm-200 whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {parsed.rows.map((row, ri) => (
                <tr key={ri} className={ri % 2 === 0 ? 'bg-white' : 'bg-warm-100/50'}>
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-3 py-1.5 text-warm-900 border-b border-warm-200 whitespace-nowrap">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <pre className="p-3 bg-warm-100 text-xs text-warm-900 font-mono whitespace-pre leading-relaxed overflow-x-auto">
          {table.content_markdown}
        </pre>
      )}
    </div>
  )
}
