import type { ExpressionSpecification } from 'maplibre-gl'

// CAMEO root codes 14–20 and their map colours (matches the event_types table).
export const CONFLICT_TYPE_COLOURS: Record<number, string> = {
  14: '#facc15',
  15: '#a3e635',
  16: '#38bdf8',
  17: '#fb923c',
  18: '#f43f5e',
  19: '#dc2626',
  20: '#c026d3',
}

/** A MapLibre expression colouring each feature by the conflict type in `property`. */
export function colourByType(property: string): ExpressionSpecification {
  const pairs = Object.entries(CONFLICT_TYPE_COLOURS).flatMap(([code, colour]) => [Number(code), colour])
  // MapLibre's tuple type can't describe a computed list of match pairs, hence the cast.
  return ['match', ['get', property], ...pairs, '#f97316'] as unknown as ExpressionSpecification
}
