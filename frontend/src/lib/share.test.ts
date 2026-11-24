import { beforeEach, describe, expect, it, vi } from 'vitest'

import { comparisonMarkdown, comparisonWinners, COMPARE_LIMIT, compareUrl, copyText, parseCompareIds } from './share'

describe('parseCompareIds', () => {
  it('parses a comma-separated list into positive integers', () => {
    expect(parseCompareIds('1, 2,3')).toEqual([1, 2, 3])
  })

  it('drops junk, duplicates and non-positive ids', () => {
    expect(parseCompareIds('4,abc,-2,0,4,7')).toEqual([4, 7])
  })

  it('enforces the comparison limit', () => {
    expect(parseCompareIds('1,2,3,4,5,6')).toEqual([1, 2, 3, 4])
    expect(COMPARE_LIMIT).toBe(4)
  })

  it('returns an empty list for missing input', () => {
    expect(parseCompareIds(null)).toEqual([])
    expect(parseCompareIds('')).toEqual([])
  })
})

describe('compareUrl', () => {
  it('builds a stable share URL', () => {
    expect(compareUrl([3, 1, 3])).toBe('/compare?ids=3,1')
  })
})

describe('comparisonMarkdown', () => {
  it('escapes pipes and renders every row', () => {
    const markdown = comparisonMarkdown(
      [{ name: 'A | B', price: '$10' }],
      [
        { key: 'name', label: 'Product' },
        { key: 'price', label: 'Price' },
      ],
    )
    expect(markdown).toContain('| Product | Price |')
    expect(markdown).toContain('A \\| B')
    expect(markdown).toContain('$10')
  })

  it('has an explicit empty state', () => {
    expect(comparisonMarkdown([], [{ key: 'name', label: 'Product' }])).toContain('No products')
  })
})

describe('comparisonWinners', () => {
  it('ignores missing prices and ratings instead of treating them as zero', () => {
    const result = comparisonWinners([
      { product_id: 91, price_usd: null, rating: null },
      { product_id: 92, price_usd: 12.5, rating: 4.4 },
      { product_id: 93, price_usd: 9.99, rating: 4.8 },
    ])
    expect(result).toEqual({ cheapestId: 93, topRatedId: 93 })
  })

  it('has no winners when every value is missing', () => {
    expect(comparisonWinners([{ product_id: 1, price_usd: null, rating: undefined }])).toEqual({
      cheapestId: null,
      topRatedId: null,
    })
  })
})

describe('copyText', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  it('uses the async clipboard when available', async () => {
    expect(await copyText('hello')).toBe(true)
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('hello')
  })
})
