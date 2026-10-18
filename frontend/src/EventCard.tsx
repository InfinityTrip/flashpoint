import { useQuery } from '@tanstack/react-query'
import { useEffect, useState, type ReactNode } from 'react'

import { type Actor, type EventDetail, fetchEvent } from './api'

const PRECISION_LABELS: Record<EventDetail['place']['precision'], string> = {
  city: 'located to a city',
  province: 'located to a province or state',
  country: 'located only to the country',
}

function formatReported(iso: string): string {
  return `${new Date(iso).toLocaleString('en-GB', {
    timeZone: 'UTC',
    dateStyle: 'medium',
    timeStyle: 'short',
  })} UTC`
}

function formatDay(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString('en-GB', {
    timeZone: 'UTC',
    dateStyle: 'medium',
  })
}

function count(n: number | null, noun: string): string {
  const value = n ?? 0
  return `${value.toLocaleString()} ${noun}${value === 1 ? '' : 's'}`
}

function actorText(actor: Actor): string | null {
  if (!actor.name && !actor.country_code) return null
  const country = actor.country_name ?? actor.country_code
  if (!actor.name) return country
  return country && country.toUpperCase() !== actor.name ? `${actor.name} (${country})` : actor.name
}

/** GDELT's source URLs come from crawled pages, so only link real web addresses. */
function safeLink(url: string | null): URL | null {
  if (!url) return null
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed : null
  } catch {
    return null
  }
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[5.5rem_1fr] gap-2">
      <dt className="text-gray-500">{label}</dt>
      <dd className="text-gray-200">{children}</dd>
    </div>
  )
}

function Details({ event }: { event: EventDetail }) {
  const by = actorText(event.actor1)
  const toward = actorText(event.actor2)
  const link = safeLink(event.source_url)
  const place = event.place.name ?? event.place.country_name ?? 'Unnamed place'
  return (
    <>
      <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
        <span
          className="h-2.5 w-2.5 rounded-full"
          style={{ backgroundColor: event.conflict_type.colour }}
        />
        <span style={{ color: event.conflict_type.colour }}>{event.conflict_type.name}</span>
      </p>
      <h2 className="mt-1 text-base leading-snug font-semibold text-gray-50">
        {event.action ?? event.conflict_type.name}
      </h2>
      <p className="text-xs text-gray-500">CAMEO code {event.event_code}</p>

      <dl className="mt-3 space-y-1.5">
        {(by || toward) && (
          <>
            <Row label="By">{by ?? 'Not coded'}</Row>
            <Row label="Toward">{toward ?? 'Not coded'}</Row>
          </>
        )}
        <Row label="Where">
          {place}
          <span className="block text-xs text-gray-500">
            {PRECISION_LABELS[event.place.precision]}
          </span>
        </Row>
        <Row label="Reported">{formatReported(event.date_added)}</Row>
        <Row label="Event date">{formatDay(event.event_date)}</Row>
        <Row label="Coverage">
          {count(event.num_mentions, 'mention')} in {count(event.num_sources, 'source')},{' '}
          {count(event.num_articles, 'article')}
        </Row>
        {event.goldstein !== null && (
          <Row label="Goldstein">
            {event.goldstein.toFixed(1)}
            <span className="block text-xs text-gray-500">
              How destabilising this kind of action is, from −10 to +10
            </span>
          </Row>
        )}
        {event.avg_tone !== null && (
          <Row label="Tone">
            {event.avg_tone.toFixed(1)}
            <span className="block text-xs text-gray-500">
              Average tone of the coverage; below 0 is negative
            </span>
          </Row>
        )}
      </dl>

      {link && (
        <a
          href={link.href}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 block truncate text-sm text-orange-300 hover:text-orange-200"
        >
          Read the source article ↗ <span className="text-gray-500">{link.hostname}</span>
        </a>
      )}
      <p className="mt-3 text-[11px] leading-snug text-gray-500">
        A news-reported event, machine-coded by GDELT from news coverage. It may be miscoded, and
        the same event may be reported more than once.
      </p>
    </>
  )
}

type Props = {
  /** The events under the clicked spot, newest first. */
  ids: number[]
  onClose: () => void
}

/** The detail card. Give it a `key` of the ids so a new click starts at the first event. */
export function EventCard({ ids, onClose }: Props) {
  const [index, setIndex] = useState(0)
  const id = ids[index]
  const event = useQuery({
    queryKey: ['event', id],
    queryFn: () => fetchEvent(id),
    staleTime: Infinity, // a stored event never changes
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const stepClass = 'px-1.5 text-gray-400 hover:text-white disabled:opacity-30'
  return (
    <aside
      aria-label="Event details"
      className="absolute inset-x-2 z-10 bottom-2 max-h-[65%] overflow-y-auto rounded-lg border border-white/10 bg-gray-950/95 p-4 text-sm shadow-xl backdrop-blur sm:inset-x-auto sm:top-3 sm:right-3 sm:bottom-auto sm:max-h-[calc(100%-1.5rem)] sm:w-80"
    >
      <div className="mb-2 flex items-center justify-between text-xs text-gray-400">
        {ids.length > 1 ? (
          <span className="flex items-center">
            <button
              type="button"
              className={stepClass}
              disabled={index === 0}
              onClick={() => setIndex(index - 1)}
              aria-label="Previous event"
            >
              ‹
            </button>
            {index + 1} of {ids.length} events at this spot
            <button
              type="button"
              className={stepClass}
              disabled={index === ids.length - 1}
              onClick={() => setIndex(index + 1)}
              aria-label="Next event"
            >
              ›
            </button>
          </span>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={onClose}
          className="rounded px-1.5 text-lg leading-none text-gray-400 hover:text-white"
          aria-label="Close"
        >
          ×
        </button>
      </div>
      {event.isPending && <p className="text-gray-400">Loading…</p>}
      {event.isError && (
        <p className="text-red-400">
          This event couldn&apos;t be loaded. It may be older than the 35 days Flashpoint keeps.
        </p>
      )}
      {event.data && <Details event={event.data} />}
    </aside>
  )
}
