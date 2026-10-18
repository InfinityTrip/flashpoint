import type { Feature, FeatureCollection, Point } from 'geojson'

import { API_URL } from './config'

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

export type GridCell = Feature<Point, { count: number; top_type: number }>

export type GridResponse = FeatureCollection<Point, GridCell['properties']> & {
  cell_size: number
  total: number
}

export type MapView = {
  zoom: number
  /** west,south,east,north, or null when the whole globe is in view. */
  bbox: string | null
}

export const fetchGrid = (view: MapView) => {
  const params = new URLSearchParams({ zoom: view.zoom.toFixed(1) })
  if (view.bbox) params.set('bbox', view.bbox)
  return getJson<GridResponse>(`/events/grid?${params}`)
}
