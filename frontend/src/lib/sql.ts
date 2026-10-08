/**
 * Minimal client-side SQL formatter for the query lab.
 *
 * Deliberately dependency-free: it uppercases the major clause keywords, puts
 * each clause on its own line and indents the body. It is cosmetic only — the
 * statement sent to the API is byte-identical apart from whitespace.
 */

const CLAUSES = [
  'SELECT',
  'FROM',
  'WHERE',
  'GROUP BY',
  'HAVING',
  'ORDER BY',
  'LIMIT',
  'OFFSET',
  'WITH',
  'UNION',
  'EXCEPT',
  'INTERSECT',
  'VALUES',
]

const JOINERS = ['LEFT JOIN', 'RIGHT JOIN', 'FULL JOIN', 'INNER JOIN', 'CROSS JOIN', 'JOIN']

const KEYWORDS = [
  'AND',
  'OR',
  'ON',
  'AS',
  'ASC',
  'DESC',
  'DISTINCT',
  'COUNT',
  'SUM',
  'AVG',
  'MIN',
  'MAX',
  'NULLS LAST',
  'NULLS FIRST',
  'CASE',
  'WHEN',
  'THEN',
  'ELSE',
  'END',
  'BETWEEN',
  'IN',
  'IS',
  'NOT',
  'NULL',
  'LIKE',
  'EXISTS',
]

/** Split a statement into string-literal and code segments so keywords inside quotes survive. */
function segments(sql: string): { text: string; literal: boolean }[] {
  const out: { text: string; literal: boolean }[] = []
  let current = ''
  let quote: string | null = null
  for (let i = 0; i < sql.length; i += 1) {
    const char = sql[i]
    if (quote) {
      current += char
      if (char === quote) {
        // A doubled quote inside a literal is an escape, not the end.
        if (sql[i + 1] === quote) {
          current += sql[i + 1]
          i += 1
        } else {
          out.push({ text: current, literal: true })
          current = ''
          quote = null
        }
      }
    } else if (char === "'" || char === '"') {
      if (current) out.push({ text: current, literal: false })
      current = char
      quote = char
    } else {
      current += char
    }
  }
  if (current) out.push({ text: current, literal: quote !== null })
  return out
}

function upperKeywords(code: string): string {
  let result = code
  for (const keyword of [...JOINERS, ...CLAUSES, ...KEYWORDS]) {
    const pattern = new RegExp(`\\b${keyword.replace(/ /g, '\\s+')}\\b`, 'gi')
    result = result.replace(pattern, keyword)
  }
  return result
}

export function formatSql(sql: string): string {
  const input = sql.trim().replace(/;?\s*$/, '')
  if (!input) return ''

  // Uppercase keywords outside string literals, then work on the merged text.
  const merged = segments(input)
    .map((segment) => (segment.literal ? segment.text : upperKeywords(segment.text)))
    .join('')

  // One clause per line.
  let broken = merged
  for (const clause of [...JOINERS, ...CLAUSES]) {
    const pattern = new RegExp(`\\s*\\b${clause.replace(/ /g, '\\s+')}\\b\\s*`, 'g')
    broken = broken.replace(pattern, `\n${clause} `)
  }
  // AND/OR start a continuation line when they join conditions.
  broken = broken.replace(/\s*\b(AND|OR)\b\s*/g, '\n  $1 ')

  const lines = broken
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
  // Indent every line that does not open a clause.
  const clauseStart = new RegExp(`^(${[...JOINERS, ...CLAUSES].join('|')})\\b`)
  const formatted = lines.map((line) => (clauseStart.test(line) ? line : `  ${line}`))

  // Keep short statements compact: a single SELECT … FROM fits on one screen.
  const joined = formatted.join('\n')
  return `${joined};`
}
