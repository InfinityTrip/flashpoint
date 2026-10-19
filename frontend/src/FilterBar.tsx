import type { Filters } from './api'
import { MAJOR_EVENT_TYPES } from './conflictTypes'
import { DEFAULT_VIEW, type Scope, TIME_WINDOWS, type TimeWindow, type ViewState } from './viewState'

const WINDOW_LABELS: Record<TimeWindow, string> = { '24h': '24h', '7d': '7 days', '30d': '30 days' }

const SCOPE_OPTIONS: { scope: Scope; label: string; title: string }[] = [
  {
    scope: 'major',
    label: 'Major events',
    title:
      'Violent events (assault, fighting, mass violence, violent protest or repression) reported by at least 2 news sources, one per article',
  },
  { scope: 'all', label: 'All events', title: 'Every news-reported conflict event GDELT coded' },
]

type Props = {
  filters: Filters | undefined
  view: ViewState
  onChange: (next: Partial<ViewState>) => void
}

const selectClass =
  'rounded border border-white/15 bg-white/5 px-2 py-1 text-sm text-gray-100 focus:border-orange-400 focus:outline-none'

function chipClass(active: boolean) {
  return `rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap transition-colors ${
    active
      ? 'border-orange-400 bg-orange-400/15 text-orange-100'
      : 'border-white/15 text-gray-300 hover:border-white/40'
  }`
}

export function FilterBar({ filters, view, onChange }: Props) {
  const countries = (filters?.countries ?? []).filter(
    (c) => !view.region || c.region_id === view.region,
  )
  const types = (filters?.conflict_types ?? []).filter(
    (t) => view.scope === 'all' || MAJOR_EVENT_TYPES.includes(t.root_code),
  )
  const lastDay = filters?.date_range.last?.slice(0, 10)
  const firstDay = filters?.date_range.first?.slice(0, 10)

  function toggleType(code: number) {
    const types = view.types.includes(code)
      ? view.types.filter((t) => t !== code)
      : [...view.types, code].sort((a, b) => a - b)
    onChange({ types })
  }

  function setRegion(region: string | null) {
    // Keep the country only if it belongs to the newly chosen region.
    const country = filters?.countries.find((c) => c.fips_code === view.country)
    const keepCountry = !region || country?.region_id === region
    onChange({ region, country: keepCountry ? view.country : null })
  }

  function startCustomRange() {
    if (!lastDay) return
    const weekBefore = new Date(`${lastDay}T00:00:00Z`)
    weekBefore.setUTCDate(weekBefore.getUTCDate() - 6)
    onChange({ range: { start: weekBefore.toISOString().slice(0, 10), end: lastDay } })
  }

  const isDefault =
    view.scope === DEFAULT_VIEW.scope &&
    !view.region &&
    !view.country &&
    !view.types.length &&
    !view.range &&
    view.window === DEFAULT_VIEW.window

  return (
    // One sideways-scrolling row on phones; wraps onto a second line on wider screens.
    <div className="flex items-center gap-x-3 gap-y-2 overflow-x-auto border-b border-white/10 px-4 py-2 sm:flex-wrap sm:overflow-visible">
      <div className="flex shrink-0 rounded border border-white/15 p-0.5" role="group" aria-label="Scope">
        {SCOPE_OPTIONS.map((option) => (
          <button
            key={option.scope}
            type="button"
            title={option.title}
            aria-pressed={view.scope === option.scope}
            onClick={() =>
              onChange({
                scope: option.scope,
                // Drop type chips that the major scope hides, so they can't filter invisibly.
                types:
                  option.scope === 'major'
                    ? view.types.filter((t) => MAJOR_EVENT_TYPES.includes(t))
                    : view.types,
              })
            }
            className={`rounded px-2 py-0.5 text-xs whitespace-nowrap transition-colors ${
              view.scope === option.scope ? 'bg-orange-400/20 text-orange-100' : 'text-gray-400 hover:text-gray-100'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <select
        aria-label="Region"
        className={`${selectClass} max-w-44`}
        value={view.region ?? ''}
        onChange={(e) => setRegion(e.target.value || null)}
      >
        <option value="">All regions</option>
        {filters?.regions.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </select>

      <select
        aria-label="Country"
        className={`${selectClass} max-w-48`}
        value={view.country ?? ''}
        onChange={(e) => onChange({ country: e.target.value || null })}
      >
        <option value="">All countries</option>
        {countries.map((c) => (
          <option key={c.fips_code} value={c.fips_code}>
            {c.name} ({c.event_count.toLocaleString()})
          </option>
        ))}
      </select>

      <div className="flex shrink-0 gap-1.5 sm:flex-wrap" role="group" aria-label="Conflict types">
        {types.map((t) => (
          <button
            key={t.root_code}
            type="button"
            className={chipClass(view.types.includes(t.root_code))}
            aria-pressed={view.types.includes(t.root_code)}
            onClick={() => toggleType(t.root_code)}
          >
            <span className="mr-1.5 inline-block size-2 rounded-full" style={{ background: t.colour }} />
            {t.name}
          </button>
        ))}
      </div>

      <div className="flex shrink-0 items-center gap-1.5 sm:ml-auto" role="group" aria-label="Date">
        {TIME_WINDOWS.map((w) => (
          <button
            key={w}
            type="button"
            className={chipClass(!view.range && view.window === w)}
            aria-pressed={!view.range && view.window === w}
            onClick={() => onChange({ window: w, range: null })}
          >
            {WINDOW_LABELS[w]}
          </button>
        ))}
        {view.range ? (
          <>
            <input
              type="date"
              aria-label="From"
              className={selectClass}
              min={firstDay}
              max={view.range.end}
              value={view.range.start}
              onChange={(e) => e.target.value && onChange({ range: { ...view.range!, start: e.target.value } })}
            />
            <span className="text-gray-500">–</span>
            <input
              type="date"
              aria-label="To"
              className={selectClass}
              min={view.range.start}
              max={lastDay}
              value={view.range.end}
              onChange={(e) => e.target.value && onChange({ range: { ...view.range!, end: e.target.value } })}
            />
          </>
        ) : (
          <button type="button" className={chipClass(false)} onClick={startCustomRange} disabled={!lastDay}>
            Custom
          </button>
        )}
      </div>

      {!isDefault && (
        <button
          type="button"
          className="text-xs whitespace-nowrap text-gray-400 underline-offset-2 hover:text-gray-100 hover:underline"
          onClick={() =>
            onChange({
              scope: DEFAULT_VIEW.scope,
              region: null,
              country: null,
              types: [],
              window: DEFAULT_VIEW.window,
              range: null,
            })
          }
        >
          Reset
        </button>
      )}
    </div>
  )
}
