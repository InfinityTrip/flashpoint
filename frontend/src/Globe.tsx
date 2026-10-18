import 'maplibre-gl/dist/maplibre-gl.css'

import * as maplibregl from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef } from 'react'

import type { FeatureCollection } from 'geojson'

import type { GridResponse, MapView } from './api'
import { BASEMAP_STYLE_URL } from './config'
import { colourByType } from './conflictTypes'

// MapLibre v6 finds its web worker relative to its own file, which bundling breaks.
// Importing the worker with ?url makes Vite ship it and hands MapLibre the real address.
maplibregl.setWorkerUrl(maplibreWorkerUrl)

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }
// Below this zoom most of the globe is visible, so the API is asked for the whole world.
const WHOLE_WORLD_BELOW_ZOOM = 3

/** The visible area as the API's bbox parameter, rounded so nearby views share a cache entry. */
function viewOf(map: maplibregl.Map): MapView {
  const zoom = map.getZoom()
  if (zoom < WHOLE_WORLD_BELOW_ZOOM) return { zoom, bbox: null }
  const bounds = map.getBounds()
  const span = bounds.getEast() - bounds.getWest()
  if (span >= 360) return { zoom, bbox: null }
  const wrap = (lng: number) => ((((lng + 180) % 360) + 360) % 360) - 180
  const parts = [
    wrap(bounds.getWest()),
    Math.max(bounds.getSouth(), -90),
    wrap(bounds.getEast()),
    Math.min(bounds.getNorth(), 90),
  ]
  return { zoom, bbox: parts.map((n) => n.toFixed(1)).join(',') }
}

/** Adds `size`: the cell's count relative to the busiest cell, as an area (hence the sqrt). */
function withRelativeSize(grid: GridResponse): FeatureCollection {
  const max = Math.max(1, ...grid.features.map((f) => f.properties.count))
  return {
    type: 'FeatureCollection',
    features: grid.features.map((f) => ({
      ...f,
      properties: { ...f.properties, size: Math.sqrt(f.properties.count / max) },
    })),
  }
}

type Props = {
  grid: GridResponse | undefined
  onViewChange: (view: MapView) => void
}

export function Globe({ grid, onViewChange }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const onViewChangeRef = useRef(onViewChange)
  useEffect(() => {
    onViewChangeRef.current = onViewChange
  }, [onViewChange])

  useEffect(() => {
    if (!container.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE_URL,
      center: [30, 20],
      zoom: 1.6,
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
    map.on('mouseenter', 'grid-cells', () => (map.getCanvas().style.cursor = 'pointer'))
    map.on('mouseleave', 'grid-cells', () => (map.getCanvas().style.cursor = ''))

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

  return <div ref={container} className="h-full w-full" data-testid="globe" />
}
