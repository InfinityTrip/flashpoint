import type { ConflictType } from './api'

type Props = {
  types: ConflictType[] | undefined
  showingPoints: boolean
  majorOnly: boolean
}

export function Legend({ types, showingPoints, majorOnly }: Props) {
  if (!types?.length) return null
  return (
    <div className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-black/60 px-3 py-2 text-[11px] text-gray-300 backdrop-blur">
      <ul className="grid grid-cols-2 gap-x-3 gap-y-0.5 sm:grid-cols-1">
        {types.map((type) => (
          <li key={type.root_code} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: type.colour }} />
            {type.name}
          </li>
        ))}
      </ul>
      {majorOnly && (
        <p className="mt-1.5 max-w-44 text-gray-400">
          Major events only: violent events reported by 2+ sources, one per article.
        </p>
      )}
      <p className="mt-1.5 max-w-44 text-gray-500">
        {showingPoints
          ? 'Points: events located to a city or province. Numbered circles group nearby events.'
          : 'Circles: event counts, coloured by the most common type.'}
      </p>
    </div>
  )
}
