/**
 * The page's view state (filters and globe position) and its encoding in the URL.
 *
 * Every component reads and writes view state through this module, so any view can be shared
 * as a link: ?region=SSF&country=SU&type=18,19&window=24h&map=4.25/15.5/32.5
 */

export type TimeWindow = '24h' | '7d' | '30d'

export type DateRange = { start: string; end: string } // inclusive ISO dates, UTC

export type Camera = { lng: number; lat: number; zoom: number }

export type ViewState = {
  region: string | null // World Bank region id
  country: string | null // GDELT FIPS code
  types: number[] // CAMEO root codes 14–20, sorted; empty means all
  window: TimeWindow // used when there is no date range
  range: DateRange | null
  camera: Camera
}

export const TIME_WINDOWS: TimeWindow[] = ['24h', '7d', '30d']

export const DEFAULT_VIEW: ViewState = {
  region: null,
  country: null,
  types: [],
  window: '7d',
  range: null,
  camera: { lng: 30, lat: 20, zoom: 1.6 },
}

const CODE = /^[A-Z]{2,3}$/
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

function validDate(value: string | null): string | null {
  if (!value || !ISO_DATE.test(value)) return null
  const parsed = new Date(`${value}T00:00:00Z`)
  // Rejects impossible dates such as 2026-13-40, which Date would otherwise roll over.
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().startsWith(value) ? value : null
}

function parseTypes(value: string | null): number[] {
  if (!value) return []
  const codes = value
    .split(',')
    .map(Number)
    .filter((n) => Number.isInteger(n) && n >= 14 && n <= 20)
  return [...new Set(codes)].sort((a, b) => a - b)
}

function parseCamera(value: string | null): Camera {
  const parts = value?.split('/').map(Number)
  if (!parts || parts.length !== 3 || parts.some(Number.isNaN)) return DEFAULT_VIEW.camera
  const [zoom, lat, lng] = parts
  if (zoom < 0 || zoom > 22 || lat < -90 || lat > 90 || lng < -180 || lng > 180) {
    return DEFAULT_VIEW.camera
  }
  return { lng, lat, zoom }
}

export function parseView(search: string): ViewState {
  const params = new URLSearchParams(search)
  const region = params.get('region')
  const country = params.get('country')
  const window = params.get('window') as TimeWindow | null
  const start = validDate(params.get('start'))
  const end = validDate(params.get('end'))
  return {
    region: region && CODE.test(region) ? region : null,
    country: country && CODE.test(country) ? country : null,
    types: parseTypes(params.get('type')),
    window: window && TIME_WINDOWS.includes(window) ? window : DEFAULT_VIEW.window,
    range: start && end && start <= end ? { start, end } : null,
    camera: parseCamera(params.get('map')),
  }
}

/** The query string for a view ('' for the default view), leaving defaults out. */
export function serializeView(view: ViewState): string {
  const parts: string[] = []
  if (view.region) parts.push(`region=${view.region}`)
  if (view.country) parts.push(`country=${view.country}`)
  if (view.types.length) parts.push(`type=${view.types.join(',')}`)
  if (view.range) parts.push(`start=${view.range.start}`, `end=${view.range.end}`)
  else if (view.window !== DEFAULT_VIEW.window) parts.push(`window=${view.window}`)
  const { camera } = view
  const isDefaultCamera =
    camera.lng === DEFAULT_VIEW.camera.lng &&
    camera.lat === DEFAULT_VIEW.camera.lat &&
    camera.zoom === DEFAULT_VIEW.camera.zoom
  if (!isDefaultCamera) {
    // Rounded so the URL stays short: 0.0001° is about 11 m.
    const round = (n: number, digits: number) => Number(n.toFixed(digits))
    parts.push(`map=${round(camera.zoom, 2)}/${round(camera.lat, 4)}/${round(camera.lng, 4)}`)
  }
  return parts.length ? `?${parts.join('&')}` : ''
}

/** The API's shared filter parameters for a view. */
export function filterParams(view: ViewState): URLSearchParams {
  const params = new URLSearchParams()
  if (view.region) params.set('region', view.region)
  if (view.country) params.set('country', view.country)
  for (const type of view.types) params.append('type', String(type))
  if (view.range) {
    params.set('start', view.range.start)
    params.set('end', view.range.end)
  } else {
    params.set('window', view.window)
  }
  return params
}
