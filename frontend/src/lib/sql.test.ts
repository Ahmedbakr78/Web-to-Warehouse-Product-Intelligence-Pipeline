import { describe, expect, it } from 'vitest'

import { formatSql } from '@/lib/sql'

describe('formatSql', () => {
  it('uppercases keywords and breaks clauses onto lines', () => {
    const out = formatSql('select a, b from t where x > 1 and y < 2 order by a limit 5')
    expect(out).toContain('SELECT')
    expect(out).toContain('\nFROM ')
    expect(out).toContain('\nWHERE ')
    expect(out).toContain('\nORDER BY ')
    expect(out).toContain('\nLIMIT ')
    expect(out.endsWith(';')).toBe(true)
  })

  it('breaks AND onto continuation lines', () => {
    const out = formatSql('SELECT a FROM t WHERE x = 1 AND y = 2')
    expect(out).toContain('\n  AND y = 2')
  })

  it('leaves string literals untouched', () => {
    const out = formatSql("select * from t where name = 'select from where' and x = 1")
    expect(out).toContain("'select from where'")
    expect(out).not.toContain("'SELECT")
  })

  it('returns an empty string for blank input', () => {
    expect(formatSql('   ')).toBe('')
  })

  it('is idempotent', () => {
    const once = formatSql('select a from t where x=1 group by a having count(*) > 2')
    expect(formatSql(once)).toBe(once)
  })
})
