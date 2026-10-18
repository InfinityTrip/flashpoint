import { API_URL } from './config'

export type Health = {
  status: 'ok' | 'down'
  database: 'ok' | 'unreachable'
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}/v1${path}`)
  // /v1/health answers 503 with a JSON body when the database is down.
  if (!response.ok && response.status !== 503) {
    throw new Error(`${path} failed with HTTP ${response.status}`)
  }
  return (await response.json()) as T
}

export const fetchHealth = () => getJson<Health>('/health')
