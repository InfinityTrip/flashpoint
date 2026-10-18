import { describe, expect, it } from 'vitest'

import { DEFAULT_VIEW, filterParams, parseView, serializeView, type ViewState } from './viewState'

const full: ViewState = {
  region: 'SSF',
  country: 'SU',
  types: [18, 19],
  window: '24h',
  range: null,
  camera: { lng: 32.5, lat: 15.5, zoom: 4.25 },
}

describe('parseView / serializeView', () => {
  it('round-trips every field', () => {
    expect(parseView(serializeView(full))).toEqual(full)
    // A date range replaces the window, so the window isn't written alongside it.
    const withRange: ViewState = {
      ...full,
      window: '7d',
      range: { start: '2026-10-01', end: '2026-10-07' },
    }
    expect(parseView(serializeView(withRange))).toEqual(withRange)
  })

  it('writes nothing for the default view, so the plain URL is the default', () => {
    expect(serializeView(DEFAULT_VIEW)).toBe('')
    expect(parseView('')).toEqual(DEFAULT_VIEW)
  })

  it('writes a short, readable query string', () => {
    expect(serializeView(full)).toBe('?region=SSF&country=SU&type=18,19&window=24h&map=4.25/15.5/32.5')
  })

  it('accepts a leading ? or none', () => {
    expect(parseView('?country=SU').country).toBe('SU')
    expect(parseView('country=SU').country).toBe('SU')
  })

  it('falls back to defaults for invalid values, field by field', () => {
    const view = parseView(
      '?region=atlantis!&country=12&type=13,19,abc,19&window=2w&map=99/200/x&start=2026-13-40&end=2026-10-07',
    )
    expect(view.region).toBeNull()
    expect(view.country).toBeNull()
    expect(view.types).toEqual([19])
    expect(view.window).toBe('7d')
    expect(view.camera).toEqual(DEFAULT_VIEW.camera)
    expect(view.range).toBeNull()
  })

  it('needs both ends of a date range, in order', () => {
    expect(parseView('?start=2026-10-01').range).toBeNull()
    expect(parseView('?start=2026-10-07&end=2026-10-01').range).toBeNull()
    expect(parseView('?start=2026-10-01&end=2026-10-01').range).toEqual({
      start: '2026-10-01',
      end: '2026-10-01',
    })
  })

  it('keeps types sorted and unique', () => {
    expect(parseView('?type=20,14,20').types).toEqual([14, 20])
  })
})

describe('filterParams', () => {
  it('turns filters into API parameters, repeating type', () => {
    expect(filterParams(full).toString()).toBe('region=SSF&country=SU&type=18&type=19&window=24h')
  })

  it('sends a date range instead of the window', () => {
    const params = filterParams({ ...DEFAULT_VIEW, range: { start: '2026-10-01', end: '2026-10-07' } })
    expect(params.toString()).toBe('start=2026-10-01&end=2026-10-07')
  })

  it('sends the default window explicitly', () => {
    expect(filterParams(DEFAULT_VIEW).toString()).toBe('window=7d')
  })
})
