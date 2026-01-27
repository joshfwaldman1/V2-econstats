import type { SearchResponse } from '../types'

const API_BASE = '/api'

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

export async function streamSearch(
  query: string,
  onChunk: (chunk: string) => void,
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
    throw new Error(`Stream search failed: ${response.statusText}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No reader available')

  const decoder = new TextDecoder()

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const chunk = decoder.decode(value, { stream: true })
    onChunk(chunk)
  }
}

export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/health`)
  return response.json()
}
