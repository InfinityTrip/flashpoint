import { describe, expect, it } from 'vitest'

import { normaliseApiUrl } from './config'

describe('normaliseApiUrl', () => {
  it('adds https:// to a bare host', () => {
    expect(normaliseApiUrl('api.up.railway.app')).toBe('https://api.up.railway.app')
  })

  it('keeps a full URL and drops trailing slashes', () => {
    expect(normaliseApiUrl('https://api.up.railway.app/')).toBe('https://api.up.railway.app')
    expect(normaliseApiUrl('http://localhost:8000')).toBe('http://localhost:8000')
  })

  it('falls back to the local API when unset', () => {
    expect(normaliseApiUrl(undefined)).toBe('http://localhost:8000')
    expect(normaliseApiUrl('  ')).toBe('http://localhost:8000')
  })
})
