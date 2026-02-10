/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CACHE_SERVICE_URL?: string
  readonly VITE_RESULTS_SERVICE_URL?: string
  readonly VITE_CATALOG_SERVICE_URL?: string
  readonly VITE_SESSION_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
