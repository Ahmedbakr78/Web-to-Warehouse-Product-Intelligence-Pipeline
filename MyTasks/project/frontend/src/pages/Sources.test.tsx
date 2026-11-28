/**
 * Add-source payload assembly.
 *
 * The modal posts a nested mapping body; a malformed body fails server-side
 * validation with a generic 422. These pin the client-side contract instead:
 * blank fields are dropped (never sent as empty strings), pagination travels
 * with its parameter names, and invalid extra-params JSON throws before any
 * request leaves the browser.
 */

import { describe, expect, it } from 'vitest'

import { buildSourcePayload, type SourceForm } from '@/pages/Sources'

function form(overrides: Partial<SourceForm> = {}): SourceForm {
  return {
    code: 'demo_shop',
    name: 'Demo Shop',
    baseUrl: 'https://demo.example.com/products.json',
    termsUrl: '',
    licenseNote: '',
    itemsPath: 'products',
    idField: 'id',
    fields: { name: 'title', price: 'price', brand: '' },
    pagination: 'skip_limit',
    pageSize: '50',
    limitParam: 'limit',
    offsetParam: 'skip',
    pageParam: 'page',
    perPageParam: 'per_page',
    totalPath: 'total',
    extraParams: '',
    urlTemplate: '',
    currency: 'usd',
    rateLimit: '30',
    minDelay: '1.0',
    ...overrides,
  }
}

describe('buildSourcePayload', () => {
  it('drops blank mappings and normalises the envelope', () => {
    const body = buildSourcePayload(form()) as any
    expect(body.code).toBe('demo_shop')
    expect(body.terms_confirmed).toBe(true)
    expect(body.mapping.fields).toEqual({ name: 'title', price: 'price' })
    expect(body.mapping.pagination).toMatchObject({
      style: 'skip_limit',
      page_size: 50,
      limit_param: 'limit',
      offset_param: 'skip',
      total_path: 'total',
    })
    expect(body.mapping.currency).toBe('USD')
    expect(body.terms_url).toBeNull()
  })

  it('parses extra params and the URL template through', () => {
    const body = buildSourcePayload(
      form({ extraParams: '{"q": "boots"}', urlTemplate: '{origin}/products/{handle}' }),
    ) as any
    expect(body.mapping.params).toEqual({ q: 'boots' })
    expect(body.mapping.url_template).toBe('{origin}/products/{handle}')
  })

  it('throws on invalid extra-params JSON instead of posting', () => {
    expect(() => buildSourcePayload(form({ extraParams: '{oops' }))).toThrow(/valid JSON/)
    expect(() => buildSourcePayload(form({ extraParams: '[1,2]' }))).toThrow(/valid JSON/)
  })
})
