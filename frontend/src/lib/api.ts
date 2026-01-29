import type { SearchResponse, ChartData, Metric, SourceInfo } from '../types'

const API_BASE = '/api'

/**
 * Non-streaming search — returns the complete response at once.
 * Used as fallback if streaming fails.
 */
export async function searchQuery(
  query: string,
  history: string[] = []
): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE}/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, history }),
  })

  if (!response.ok) {
    throw new Error(`Search failed: ${response.statusText}`)
  }

  return response.json()
}

/**
 * Callbacks for progressive SSE event handling.
 * Each callback fires as soon as that piece of data is available.
 */
export interface StreamCallbacks {
  /** Charts and metrics are ready — show results page immediately */
  onCharts: (charts: ChartData[], metrics: Metric[], temporalContext: string | null) => void
  /** Special HTML boxes (Fed SEP, recession, CAPE, Polymarket) */
  onSpecial: (data: Record<string, string>) => void
  /** Source citations with FRED URLs */
  onSources: (sources: SourceInfo[]) => void
  /** A chunk of the AI summary text — append to existing summary */
  onSummaryChunk: (text: string) => void
  /** Streaming complete — suggestions are available */
  onDone: (suggestions: string[]) => void
  /** An error occurred */
  onError: (message: string) => void
}

/**
 * Streaming search via Server-Sent Events.
 *
 * Sends charts/metrics immediately, then streams the AI summary
 * token-by-token for a responsive feel.
 */
export async function streamSearch(
  query: string,
  callbacks: StreamCallbacks,
  history: string[] = []
): Promise<void> {
  const response = await fetch(`${API_BASE}/search/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, history }),
  })

  if (!response.ok) {
    callbacks.onError(`Search failed: ${response.statusText}`)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    callbacks.onError('No reader available')
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // SSE format: each event is "data: {json}\n\n"
    // Process all complete events in the buffer
    const lines = buffer.split('\n\n')
    // Keep the last incomplete chunk in the buffer
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data: ')) continue

      try {
        const jsonStr = trimmed.slice(6) // Remove "data: " prefix
        const event = JSON.parse(jsonStr)

        switch (event.type) {
          case 'charts':
            callbacks.onCharts(
              event.data || [],
              event.metrics || [],
              event.temporal_context || null
            )
            break

          case 'special':
            callbacks.onSpecial(event)
            break

          case 'sources':
            callbacks.onSources(event.data || [])
            break

          case 'summary_chunk':
            callbacks.onSummaryChunk(event.text || '')
            break

          case 'done':
            callbacks.onDone(event.suggestions || [])
            break

          case 'error':
            callbacks.onError(event.message || 'Unknown error')
            break
        }
      } catch (e) {
        // Skip malformed SSE lines
        console.warn('Failed to parse SSE event:', trimmed, e)
      }
    }
  }
}

export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/health`)
  return response.json()
}
