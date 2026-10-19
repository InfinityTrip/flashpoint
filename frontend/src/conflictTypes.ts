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

/**
 * The root codes that can hold major events: violent protest (14), violent repression (17),
 * assault (18), fight (19) and mass violence (20). Military posture and reduced relations can't.
 */
export const MAJOR_EVENT_TYPES = [14, 17, 18, 19, 20]

/** A MapLibre expression colouring each feature by the conflict type in `property`. */
export function colourByType(property: string): ExpressionSpecification {
  const pairs = Object.entries(CONFLICT_TYPE_COLOURS).flatMap(([code, colour]) => [Number(code), colour])
  // MapLibre's tuple type can't describe a computed list of match pairs, hence the cast.
  return ['match', ['get', property], ...pairs, '#f97316'] as unknown as ExpressionSpecification
}

/** Cluster properties counting each conflict type among a cluster's events: t14 … t20. */
export function typeCountProperties(): Record<string, ExpressionSpecification> {
  return Object.fromEntries(
    Object.keys(CONFLICT_TYPE_COLOURS).map((code) => [
      `t${code}`,
      ['+', ['case', ['==', ['get', 'root_code'], Number(code)], 1, 0]],
    ]),
  ) as Record<string, ExpressionSpecification>
}

/** Colours a cluster by its most common conflict type, using the counts above. */
export function colourByMostCommonType(): ExpressionSpecification {
  const codes = Object.keys(CONFLICT_TYPE_COLOURS)
  // For each type: "this type's count is at least every other type's count".
  const branches = codes.flatMap((code) => [
    [
      'all',
      ...codes
        .filter((other) => other !== code)
        .map((other) => ['>=', ['get', `t${code}`], ['get', `t${other}`]]),
    ],
    CONFLICT_TYPE_COLOURS[Number(code)],
  ])
  return ['case', ...branches, '#f97316'] as unknown as ExpressionSpecification
}
