import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'

import { fetchFilters, fetchGrid, fetchHealth, gridPath, type MapView } from './api'
import { FilterBar } from './FilterBar'
import { Globe } from './Globe'
import { parseView, serializeView, type ViewState } from './viewState'

function ApiStatus() {
  const health = useQuery({ queryKey: ['health'], queryFn: fetchHealth, refetchInterval: 60_000 })

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

  const filters = useQuery({ queryKey: ['filters'], queryFn: fetchFilters, staleTime: 5 * 60_000 })
  const path = map ? gridPath(map, view) : null
  const grid = useQuery({
    queryKey: ['grid', path],
    queryFn: () => fetchGrid(path!),
    enabled: path !== null,
    // Keep the old cells on screen while the next view loads, instead of flashing empty.
    placeholderData: keepPreviousData,
  })

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
        <Globe initialCamera={view.camera} grid={grid.data} onViewChange={onMapChange} />
        {grid.isFetching && (
          <div className="pointer-events-none absolute top-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-3 py-1 text-xs text-gray-300">
            Loading…
          </div>
        )}
      </main>
      <footer className="flex gap-4 border-t border-white/10 px-4 py-1.5 text-xs">
        <ApiStatus />
        {grid.data && (
          <span className="text-gray-400">
            {grid.data.total.toLocaleString()} news-reported events in view
          </span>
        )}
      </footer>
    </div>
  )
}
