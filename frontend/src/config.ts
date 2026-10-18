/** Accepts a bare host ("api.example.com") as well as a full URL; drops any trailing slash. */
export function normaliseApiUrl(value: string | undefined): string {
  const url = (value ?? '').trim().replace(/\/+$/, '')
  if (!url) return 'http://localhost:8000'
  return /^https?:\/\//.test(url) ? url : `https://${url}`
}

export const API_URL = normaliseApiUrl(import.meta.env.VITE_API_URL)

// CARTO Dark Matter. Production builds pass a keyed style URL through VITE_BASEMAP_STYLE_URL.
export const BASEMAP_STYLE_URL =
  import.meta.env.VITE_BASEMAP_STYLE_URL ??
  'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
