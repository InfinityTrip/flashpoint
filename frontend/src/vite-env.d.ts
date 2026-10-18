/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Flashpoint API, without the /v1 prefix. */
  readonly VITE_API_URL?: string
  /** MapLibre style URL for the basemap; a keyed CARTO URL in production. */
  readonly VITE_BASEMAP_STYLE_URL?: string
}
