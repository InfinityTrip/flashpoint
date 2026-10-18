import 'maplibre-gl/dist/maplibre-gl.css'

import * as maplibregl from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef } from 'react'

import { BASEMAP_STYLE_URL } from './config'

// MapLibre v6 finds its web worker relative to its own file, which bundling breaks.
// Importing the worker with ?url makes Vite ship it and hands MapLibre the real address.
maplibregl.setWorkerUrl(maplibreWorkerUrl)

export function Globe() {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE_URL,
      center: [20, 20],
      zoom: 1.6,
      attributionControl: { compact: true },
    })
    // The style resets the projection, so switch to the 3D globe once it has loaded.
    map.on('style.load', () => {
      map.setProjection({ type: 'globe' })
      // A faint blue atmosphere separates the dark globe from the dark page when zoomed out.
      map.setSky({
        'sky-color': '#0b0d12',
        'horizon-color': '#1e3a5f',
        'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0],
      })
    })
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right')
    return () => map.remove()
  }, [])

  return <div ref={container} className="h-full w-full" data-testid="globe" />
}
