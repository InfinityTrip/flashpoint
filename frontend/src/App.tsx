import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'

import {
  fetchFilters,
  fetchGrid,
  fetchHealth,
  fetchPoints,
  gridPath,
  type MapView,
  POINTS_FROM_ZOOM,
  pointsPath,
} from './api'
import { EventCard } from './EventCard'
import { FilterBar } from './FilterBar'
import { Globe } from './Globe'
import { Legend } from './Legend'
import { parseView, serializeView, type ViewState } from './viewState'

function ApiStatus() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 60_000,
  })

  if (health.isPending) return <span className="text-gray-400">Connecting to API…</span>
  if (health.isError || health.data.status === 'down') {
    return <span className="text-red-400">API unavailable</span>
  }
  if (health.data.status === 'degraded') {
    return <span className="text-amber-400">Data delayed</span>
  }
  return <span className="text-emerald-400">API connected</span>
}

export default function App() {
  // The URL is the source of truth on load; after that, every change is written back to it.
  const [view, setView] = useState<ViewState>(() => parseView(window.location.search))
  const [map, setMap] = useState<MapView | null>(null)
  // The events under the last clicked point; the detail card is open while this isn't empty.
  const [selected, setSelected] = useState<number[]>([])
  const closeCard = useCallback(() => setSelected([]), [])

  useEffect(() => {
    // replaceState, not pushState: panning shouldn't fill the back button with history.
    const url = `${window.location.pathname}${serializeView(view)}`
    window.history.replaceState(null, '', url)
  }, [view])

  const updateView = useCallback((next: Partial<ViewState>) => {
    setView((current) => ({ ...current, ...next }))
  }, [])

  const onMapChange = useCallback((next: MapView) => {
    setMap(next)
    setView((current) => ({ ...current, camera: next.camera }))
  }, [])

  const filters = useQuery({
    queryKey: ['filters'],
    queryFn: fetchFilters,
    staleTime: 5 * 60_000,
  })
  // Zoomed out the globe shows grid cells; zoomed in, individual events. Only one is fetched.
  const wantPoints = map !== null && map.zoom >= POINTS_FROM_ZOOM
  const gridKey = map && !wantPoints ? gridPath(map, view) : null
  const pointsKey = map && wantPoints ? pointsPath(map, view) : null
  const grid = useQuery({
    queryKey: ['grid', gridKey],
    queryFn: () => fetchGrid(gridKey!),
    enabled: gridKey !== null,
    // Keep the old cells on screen while the next view loads, instead of flashing empty.
    placeholderData: keepPreviousData,
  })
  const points = useQuery({
    queryKey: ['points', pointsKey],
    queryFn: () => fetchPoints(pointsKey!),
    enabled: pointsKey !== null,
    placeholderData: keepPreviousData,
  })
  // Crossing the threshold, keep drawing the grid until the first points arrive.
  const showPoints = wantPoints && points.data !== undefined
  const loading = showPoints ? points.isFetching : grid.isFetching

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-white/10 px-4 py-2">
        <h1 className="text-lg font-semibold tracking-tight">
          <span className="text-orange-500">Flash</span>point
        </h1>
        <p className="hidden text-sm text-gray-400 sm:block">
          News-reported conflict events worldwide, from GDELT 2.0
        </p>
      </header>
      <FilterBar filters={filters.data} view={view} onChange={updateView} />
      <main className="relative min-h-0 flex-1">
        <Globe
          initialCamera={view.camera}
          grid={showPoints ? undefined : grid.data}
          points={showPoints ? points.data : undefined}
          selectedId={selected[0] ?? null}
          onViewChange={onMapChange}
          onSelectEvents={setSelected}
        />
        <div className="pointer-events-none absolute top-3 left-1/2 flex -translate-x-1/2 flex-col items-center gap-1.5 text-xs">
          {loading && (
            <div className="rounded-full bg-black/60 px-3 py-1 text-gray-300">Loading…</div>
          )}
          {showPoints && points.data?.truncated && (
            <div className="rounded-full bg-black/70 px-3 py-1 text-center text-amber-200">
              Showing the newest {points.data.features.length.toLocaleString()} events here. Zoom in
              or narrow the filters to see the rest.
            </div>
          )}
        </div>
        <Legend types={filters.data?.conflict_types} showingPoints={showPoints} />
        {selected.length > 0 && (
          <EventCard key={selected.join(',')} ids={selected} onClose={closeCard} />
        )}
      </main>
      <footer className="flex gap-4 border-t border-white/10 px-4 py-1.5 text-xs">
        <ApiStatus />
        {showPoints && points.data ? (
          <span className="text-gray-400">
            {points.data.features.length.toLocaleString()} news-reported events shown
          </span>
        ) : (
          grid.data && (
            <span className="text-gray-400">
              {grid.data.total.toLocaleString()} news-reported events in view
            </span>
          )
        )}
      </footer>
    </div>
  )
}
