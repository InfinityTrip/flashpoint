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

/** From this zoom the globe draws individual events instead of grid cells. */
export const POINTS_FROM_ZOOM = 5

/** The grid request for a map view and the view's filters, as a path (also the cache key). */
export function gridPath(map: MapView, view: ViewState): string {
  const params = filterParams(view)
  params.set('zoom', map.zoom.toFixed(1))
  if (map.bbox) params.set('bbox', map.bbox)
  return `/events/grid?${params}`
}

export const fetchGrid = (path: string) => getJson<GridResponse>(path)

export type EventPoint = Feature<Point, { id: number; root_code: number; date_added: string }>

export type PointsResponse = FeatureCollection<Point, EventPoint['properties']> & {
  /** More events matched than were returned; only the newest are included. */
  truncated: boolean
}

/** The individual-events request for a map view, as a path (also the cache key). */
export function pointsPath(map: MapView, view: ViewState): string {
  const params = filterParams(view)
  if (map.bbox) params.set('bbox', map.bbox)
  return `/events?${params}`
}

export const fetchPoints = (path: string) => getJson<PointsResponse>(path)

export type Actor = {
  name: string | null
  country_code: string | null
  country_name: string | null
}

export type EventDetail = {
  id: number
  date_added: string
  event_date: string
  conflict_type: ConflictType
  event_code: string
  /** The CAMEO action in plain words; null when the code isn't in the lookup. */
  action: string | null
  actor1: Actor
  actor2: Actor
  place: {
    name: string | null
    geo_type: number
    precision: 'country' | 'province' | 'city'
    country_code: string | null
    country_name: string | null
    region_id: string | null
    region_name: string | null
    lon: number
    lat: number
  }
  num_mentions: number | null
  num_sources: number | null
  num_articles: number | null
  goldstein: number | null
  avg_tone: number | null
  source_url: string | null
}

export const fetchEvent = (id: number) => getJson<EventDetail>(`/events/${id}`)
