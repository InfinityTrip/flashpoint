import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { fetchGrid, fetchHealth, type MapView } from './api'
import { Globe } from './Globe'

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
  const [view, setView] = useState<MapView | null>(null)
  const grid = useQuery({
    queryKey: ['grid', view],
    queryFn: () => fetchGrid(view!),
    enabled: view !== null,
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
      <main className="relative min-h-0 flex-1">
        <Globe grid={grid.data} onViewChange={setView} />
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
