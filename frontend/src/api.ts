import type { Feature, FeatureCollection, Point } from 'geojson'

import { API_URL } from './config'
import { type Camera, filterParams, type ViewState } from './viewState'

export type Health = {
  /** degraded: the API works but the newest data is over an hour old. */
  status: 'ok' | 'degraded' | 'down'
  database: 'ok' | 'unreachable'
  latest_data_at: string | null
  minutes_since_update: number | null
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}/v1${path}`)
  // /v1/health answers 503 with a JSON body when the database is down.
  if (!response.ok && response.status !== 503) {
    throw new Error(`${path} failed with HTTP ${response.status}`)
  }
  return (await response.json()) as T
}

export const fetchHealth = () => getJson<Health>('/health')

export type Region = { id: string; name: string }
export type Country = { fips_code: string; name: string; region_id: string | null; event_count: number }
export type ConflictType = { root_code: number; name: string; colour: string }

export type Filters = {
  regions: Region[]
  countries: Country[]
  conflict_types: ConflictType[]
  date_range: { first: string | null; last: string | null }
}

export const fetchFilters = () => getJson<Filters>('/filters')

export type GridCell = Feature<Point, { count: number; top_type: number }>

export type GridResponse = FeatureCollection<Point, GridCell['properties']> & {
  cell_size: number
  total: number
}

export type MapView = {
  zoom: number
  /** west,south,east,north, or null when the whole globe is in view. */
  bbox: string | null
  camera: Camera
}

/** The grid request for a map view and the view's filters, as a path (also the cache key). */
export function gridPath(map: MapView, view: ViewState): string {
  const params = filterParams(view)
  params.set('zoom', map.zoom.toFixed(1))
  if (map.bbox) params.set('bbox', map.bbox)
  return `/events/grid?${params}`
}

export const fetchGrid = (path: string) => getJson<GridResponse>(path)
