import 'maplibre-gl/dist/maplibre-gl.css'

import * as maplibregl from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef } from 'react'

import type { FeatureCollection } from 'geojson'

import type { GridResponse, MapView, PointsResponse } from './api'
import { BASEMAP_STYLE_URL } from './config'
import { colourByMostCommonType, colourByType, typeCountProperties } from './conflictTypes'
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

// Nearby points merge into numbered clusters up to this zoom; beyond it every event is drawn.
const CLUSTER_MAX_ZOOM = 14

/** Event ids from point features, newest first. */
function newestFirst(features: { properties: Record<string, unknown> | null }[]): number[] {
  const byId = new Map(
    features.map((f) => [f.properties?.id as number, f.properties?.date_added as string]),
  )
  return [...byId].sort((a, b) => b[1].localeCompare(a[1])).map(([id]) => id)
}

// Past CLUSTER_MAX_ZOOM, events at the very same spot still overlap: 1 for a lone event,
// growing to 3 for a spot with 50 or more.
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

      map.addSource('points', {
        type: 'geojson',
        data: EMPTY,
        cluster: true,
        clusterRadius: 36,
        clusterMaxZoom: CLUSTER_MAX_ZOOM,
        clusterProperties: typeCountProperties(),
      })
      map.addLayer({
        id: 'event-clusters',
        type: 'circle',
        source: 'points',
        filter: ['has', 'point_count'],
        paint: {
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['get', 'point_count'],
            2,
            10,
            50,
            15,
            500,
            22,
            2000,
            28,
          ],
          'circle-color': colourByMostCommonType(),
          'circle-opacity': 0.75,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-opacity': 0.4,
          'circle-stroke-width': 1,
        },
      })
      map.addLayer({
        id: 'event-cluster-counts',
        type: 'symbol',
        source: 'points',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': ['get', 'point_count_abbreviated'],
          'text-font': ['Open Sans Bold'],
          'text-size': 11,
          'text-allow-overlap': true,
        },
        paint: { 'text-color': '#ffffff' },
      })
      map.addLayer({
        id: 'event-points',
        type: 'circle',
        source: 'points',
        filter: ['!', ['has', 'point_count']],
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
      onSelectEventsRef.current(newestFirst(hits))
    })
    map.on('click', 'event-clusters', async (event) => {
      const cluster = event.features?.[0]
      const source = map.getSource<maplibregl.GeoJSONSource>('points')
      if (cluster?.geometry.type !== 'Point' || !source) return
      const clusterId = cluster.properties.cluster_id as number
      const zoom = await source.getClusterExpansionZoom(clusterId)
      if (zoom <= CLUSTER_MAX_ZOOM) {
        map.easeTo({ center: cluster.geometry.coordinates as [number, number], zoom })
        return
      }
      // Events at one spot never separate by zooming, so open them all in the detail card.
      onSelectEventsRef.current(newestFirst(await source.getClusterLeaves(clusterId, 1000, 0)))
    })
    for (const layer of ['grid-cells', 'event-clusters', 'event-points']) {
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
