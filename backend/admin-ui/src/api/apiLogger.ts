/**
 * In-browser API request/response logger.
 * Stores entries in localStorage under 'api_logs', capped at ~10 MB.
 */

const STORAGE_KEY = 'api_logs'
const MAX_BYTES = 10 * 1024 * 1024 // 10 MB

export interface ApiLogEntry {
  id: string
  timestamp: string
  method: string
  url: string
  requestBody?: any
  status: number | null
  statusText: string
  responseBody?: any
  durationMs: number
  error?: string
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7)
}

/** Read all log entries from localStorage */
export function getLogs(): ApiLogEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

/** Clear all logs */
export function clearLogs(): void {
  localStorage.removeItem(STORAGE_KEY)
}

/** Get approximate storage size in bytes */
export function getLogsSize(): number {
  const raw = localStorage.getItem(STORAGE_KEY)
  return raw ? new Blob([raw]).size : 0
}

function saveLogs(logs: ApiLogEntry[]): void {
  const json = JSON.stringify(logs)
  // Trim oldest entries if over the size cap
  while (new Blob([json]).size > MAX_BYTES && logs.length > 1) {
    logs.shift() // drop oldest
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(logs))
  } catch {
    // storage full — drop half the entries and retry
    const half = Math.floor(logs.length / 2)
    logs.splice(0, half)
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(logs)) } catch { /* give up */ }
  }
}

/** Truncate large response/request bodies so we don't blow up storage */
function truncateBody(body: any): any {
  if (body === undefined || body === null) return body
  const str = typeof body === 'string' ? body : JSON.stringify(body)
  if (str.length > 8000) {
    return str.slice(0, 8000) + `... [truncated, ${str.length} chars total]`
  }
  return body
}

/**
 * Log a completed API request.
 * Call this after fetch() completes (or errors).
 */
export function addLogEntry(entry: Omit<ApiLogEntry, 'id' | 'timestamp'>): void {
  const logs = getLogs()
  logs.push({
    ...entry,
    id: generateId(),
    timestamp: new Date().toISOString(),
    requestBody: truncateBody(entry.requestBody),
    responseBody: truncateBody(entry.responseBody),
  })
  saveLogs(logs)
}
