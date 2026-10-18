import { useQuery } from '@tanstack/react-query'

import { fetchHealth } from './api'
import { Globe } from './Globe'

function ApiStatus() {
  const health = useQuery({ queryKey: ['health'], queryFn: fetchHealth, refetchInterval: 60_000 })

  if (health.isPending) return <span className="text-gray-400">Connecting to API…</span>
  if (health.isError || health.data.status !== 'ok') {
    return <span className="text-red-400">API unavailable</span>
  }
  return <span className="text-emerald-400">API connected</span>
}

export default function App() {
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
        <Globe />
      </main>
      <footer className="border-t border-white/10 px-4 py-1.5 text-xs">
        <ApiStatus />
      </footer>
    </div>
  )
}
