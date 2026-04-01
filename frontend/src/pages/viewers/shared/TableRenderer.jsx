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
    <div className="rounded-lg overflow-hidden border border-[#1a3a1a]">
      {(table.caption || table.num_rows != null) && (
        <div className="px-3 py-1.5 bg-[#0a120a] border-b border-[#1a3a1a] flex items-center gap-2">
          {table.caption && (
            <span className="text-xs text-[#5a8a5a] italic truncate">{table.caption}</span>
          )}
          <span className="ml-auto flex gap-2 shrink-0">
            {table.num_rows != null && table.num_cols != null && (
              <Badge variant="outline" className="text-[#3d6b3d] border-[#1a3a1a] text-[10px]">
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
              <tr className="bg-[#0a120a]">
                {parsed.headers.map((h, i) => (
                  <th key={i} className="px-3 py-2 text-left text-[#5a8a5a] font-medium border-b border-[#1a3a1a] whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {parsed.rows.map((row, ri) => (
                <tr key={ri} className={ri % 2 === 0 ? 'bg-[#060d06]' : 'bg-[#0a120a]/50'}>
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-3 py-1.5 text-[#8ab88a] border-b border-[#0d2b0d] whitespace-nowrap">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <pre className="p-3 bg-[#0a120a] text-xs text-[#8ab88a] font-mono whitespace-pre leading-relaxed overflow-x-auto">
          {table.content_markdown}
        </pre>
      )}
    </div>
  )
}
