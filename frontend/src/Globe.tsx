import 'maplibre-gl/dist/maplibre-gl.css'

import * as maplibregl from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef } from 'react'

import type { FeatureCollection } from 'geojson'

import type { GridResponse, MapView, PointsResponse } from './api'
import { BASEMAP_STYLE_URL } from './config'
import { colourByType } from './conflictTypes'
import type { Camera } from './viewState'

// MapLibre v6 finds its web worker relative to its own file, which bundling breaks.
// Importing the worker with ?url makes Vite ship it and hands MapLibre the real address.
maplibregl.setWorkerUrl(maplibreWorkerUrl)

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }
// Below this zoom most of the globe is visible, so the API is asked for the whole world.
const WHOLE_WORLD_BELOW_ZOOM = 3

/** The visible area as the API's bbox parameter, rounded so nearby views share a cache entry. */
function viewOf(map: maplibregl.Map): MapView {
  const zoom = map.getZoom()
  const { lng, lat } = map.getCenter()
  const camera = { lng, lat, zoom }
  if (zoom < WHOLE_WORLD_BELOW_ZOOM) return { zoom, bbox: null, camera }
  const bounds = map.getBounds()
  const span = bounds.getEast() - bounds.getWest()
  if (span >= 360) return { zoom, bbox: null, camera }
  const wrap = (lng: number) => ((((lng + 180) % 360) + 360) % 360) - 180
  const parts = [
    wrap(bounds.getWest()),
    Math.max(bounds.getSouth(), -90),
    wrap(bounds.getEast()),
    Math.min(bounds.getNorth(), 90),
  ]
  return { zoom, bbox: parts.map((n) => n.toFixed(1)).join(','), camera }
}

/** Adds `size`: the cell's count relative to the busiest cell, as an area (hence the sqrt). */
function withRelativeSize(grid: GridResponse): FeatureCollection {
  const max = Math.max(1, ...grid.features.map((f) => f.properties.count))
  return {
    type: 'FeatureCollection',
    features: grid.features.map((f) => ({
      ...f,
      properties: {
        ...f.properties,
        size: Math.sqrt(f.properties.count / max),
      },
    })),
  }
}

/** Adds `stack`: how many events share the point's exact spot (GDELT reuses city centres). */
function withStackSize(points: PointsResponse): FeatureCollection {
  const key = (f: PointsResponse['features'][number]) => f.geometry.coordinates.join(',')
  const counts = new Map<string, number>()
  for (const f of points.features) counts.set(key(f), (counts.get(key(f)) ?? 0) + 1)
  return {
    type: 'FeatureCollection',
    features: points.features.map((f) => ({
      ...f,
      properties: { ...f.properties, stack: counts.get(key(f)) },
    })),
  }
}

// 1 for a lone event, growing to 3 for a spot with 50 or more.
const STACK_SCALE: maplibregl.ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['sqrt', ['get', 'stack']],
  1,
  1,
  7,
  3,
]

/** Point radius in pixels plus `extra`: larger when zoomed in and for stacked spots. */
function pointRadius(extra: number): maplibregl.ExpressionSpecification {
  // MapLibre only allows ['zoom'] in a top-level interpolate, so the stack scale goes inside it.
  return [
    'interpolate',
    ['linear'],
    ['zoom'],
    5,
    ['+', extra, ['*', 3.5, STACK_SCALE]],
    10,
    ['+', extra, ['*', 6, STACK_SCALE]],
  ]
}

type Props = {
  /** Where the globe starts; later camera moves are reported through onViewChange. */
  initialCamera: Camera
  grid: GridResponse | undefined
  points: PointsResponse | undefined
  /** The event whose detail card is open, outlined on the map. */
  selectedId: number | null
  onViewChange: (view: MapView) => void
  /** Called with the events under a clicked point (newest first), or [] for a click elsewhere. */
  onSelectEvents: (ids: number[]) => void
}

export function Globe({
  initialCamera,
  grid,
  points,
  selectedId,
  onViewChange,
  onSelectEvents,
}: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const initialCameraRef = useRef(initialCamera)
  const onViewChangeRef = useRef(onViewChange)
  const onSelectEventsRef = useRef(onSelectEvents)
  useEffect(() => {
    onViewChangeRef.current = onViewChange
    onSelectEventsRef.current = onSelectEvents
  }, [onViewChange, onSelectEvents])

  useEffect(() => {
    if (!container.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE_URL,
      center: [initialCameraRef.current.lng, initialCameraRef.current.lat],
      zoom: initialCameraRef.current.zoom,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right')

    map.on('style.load', () => {
      map.setProjection({ type: 'globe' })
      // A faint blue atmosphere separates the dark globe from the dark page when zoomed out.
      map.setSky({
        'sky-color': '#0b0d12',
        'horizon-color': '#1e3a5f',
        'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0],
      })

      map.addSource('grid', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'grid-cells',
        type: 'circle',
        source: 'grid',
        paint: {
          // `size` is 0-1 relative to the busiest cell in view (see below), so the map stays
          // readable whether it shows one day or a month.
          'circle-radius': ['interpolate', ['linear'], ['get', 'size'], 0, 2, 1, 26],
          'circle-color': colourByType('top_type'),
          'circle-opacity': 0.5,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-opacity': 0.35,
          'circle-stroke-width': 0.5,
        },
      })

      map.addSource('points', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'event-points',
        type: 'circle',
        source: 'points',
        paint: {
          'circle-radius': pointRadius(0),
          'circle-color': colourByType('root_code'),
          'circle-opacity': 0.85,
          'circle-stroke-color': '#0b0d12',
          'circle-stroke-width': 1,
        },
      })
      map.addLayer({
        id: 'selected-point',
        type: 'circle',
        source: 'points',
        filter: ['==', ['get', 'id'], -1],
        paint: {
          'circle-radius': pointRadius(4),
          'circle-color': 'rgba(0, 0, 0, 0)',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
        },
      })
      onViewChangeRef.current(viewOf(map))
    })

    // Report the view after the camera settles; the parent fetches data for it.
    let timer: number | undefined
    map.on('moveend', () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => onViewChangeRef.current(viewOf(map)), 250)
    })

    map.on('click', 'grid-cells', (event) => {
      const cell = event.features?.[0]
      if (cell?.geometry.type !== 'Point') return
      const [lng, lat] = cell.geometry.coordinates
      map.flyTo({ center: [lng, lat], zoom: Math.min(map.getZoom() + 2, 8) })
    })
    // GDELT places many events at the same city centre, so one click can hit a stack of them.
    map.on('click', (event) => {
      const hits = map.getLayer('event-points')
        ? map.queryRenderedFeatures(event.point, { layers: ['event-points'] })
        : []
      const byId = new Map(
        hits.map((f) => [f.properties.id as number, f.properties.date_added as string]),
      )
      const ids = [...byId].sort((a, b) => b[1].localeCompare(a[1])).map(([id]) => id)
      onSelectEventsRef.current(ids)
    })
    for (const layer of ['grid-cells', 'event-points']) {
      map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
    }

    return () => {
      window.clearTimeout(timer)
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const source = mapRef.current?.getSource<maplibregl.GeoJSONSource>('grid')
    source?.setData(grid ? withRelativeSize(grid) : EMPTY)
  }, [grid])

  useEffect(() => {
    mapRef.current
      ?.getSource<maplibregl.GeoJSONSource>('points')
      ?.setData(points ? withStackSize(points) : EMPTY)
  }, [points])

  useEffect(() => {
    const map = mapRef.current
    if (map?.getLayer('selected-point')) {
      map.setFilter('selected-point', ['==', ['get', 'id'], selectedId ?? -1])
    }
  }, [selectedId])

  return <div ref={container} className="h-full w-full" data-testid="globe" />
}
