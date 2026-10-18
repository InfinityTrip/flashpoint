export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// CARTO Dark Matter. Production builds pass a keyed style URL through VITE_BASEMAP_STYLE_URL.
export const BASEMAP_STYLE_URL =
  import.meta.env.VITE_BASEMAP_STYLE_URL ??
  'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
