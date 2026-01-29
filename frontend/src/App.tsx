import { useState, useCallback, useRef } from 'react'
import { Box, Container } from '@radix-ui/themes'
import { SearchPage } from './components/SearchPage'
import { ResultsPage } from './components/ResultsPage'
import { streamSearch, searchQuery } from './lib/api'
import type { SearchResponse, SourceInfo } from './types'

type View = 'search' | 'results'

export default function App() {
  const [view, setView] = useState<View>('search')
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [history, setHistory] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  // Ref to accumulate summary text during streaming without stale closures
  const summaryRef = useRef('')

  const handleSearch = useCallback(async (query: string) => {
    setIsLoading(true)
    setIsStreaming(false)
    setError(null)
    summaryRef.current = ''

    // Initialize a partial response with the query
    const partialResponse: SearchResponse = {
      query,
      summary: '',
      suggestions: [],
      chart_descriptions: {},
      charts: [],
      sources: [],
      temporal_context: null,
      fed_sep_html: null,
      recession_html: null,
      cape_html: null,
      polymarket_html: null,
      metrics: [],
      error: null,
    }

    try {
      await streamSearch(query, {
        onCharts: (charts, metrics, temporalContext) => {
          // Show results page as soon as charts arrive
          partialResponse.charts = charts
          partialResponse.metrics = metrics
          partialResponse.temporal_context = temporalContext
          setResponse({ ...partialResponse })
          setView('results')
          setIsLoading(false)
          setIsStreaming(true)
        },

        onSpecial: (data) => {
          if (data.fed_sep_html) partialResponse.fed_sep_html = data.fed_sep_html
          if (data.recession_html) partialResponse.recession_html = data.recession_html
          if (data.cape_html) partialResponse.cape_html = data.cape_html
          if (data.polymarket_html) partialResponse.polymarket_html = data.polymarket_html
          setResponse({ ...partialResponse })
        },

        onSources: (sources: SourceInfo[]) => {
          partialResponse.sources = sources
          setResponse({ ...partialResponse })
        },

        onSummaryChunk: (text: string) => {
          summaryRef.current += text
          partialResponse.summary = summaryRef.current
          setResponse({ ...partialResponse })
        },

        onDone: (suggestions: string[]) => {
          partialResponse.suggestions = suggestions
          setResponse({ ...partialResponse })
          setIsStreaming(false)
        },

        onError: (message: string) => {
          setError(message)
          setIsLoading(false)
          setIsStreaming(false)
        },
      }, history)

      setHistory(prev => [...prev, query])
    } catch (err) {
      // SSE streaming failed — fall back to non-streaming endpoint
      console.warn('Streaming failed, falling back to non-streaming:', err)
      try {
        const result = await searchQuery(query, history)
        setResponse(result)
        setHistory(prev => [...prev, query])
        setView('results')
      } catch (fallbackErr) {
        setError(fallbackErr instanceof Error ? fallbackErr.message : 'Search failed')
      }
      setIsLoading(false)
      setIsStreaming(false)
    }
  }, [history])

  const handleFollowUp = useCallback(async (query: string) => {
    await handleSearch(query)
  }, [handleSearch])

  const handleBack = useCallback(() => {
    setView('search')
    setResponse(null)
    setIsStreaming(false)
  }, [])

  return (
    <Box style={{ minHeight: '100vh', background: 'var(--gray-1)' }}>
      <Container size="3" px="4">
        {view === 'search' ? (
          <SearchPage
            onSearch={handleSearch}
            isLoading={isLoading}
            error={error}
          />
        ) : (
          <ResultsPage
            response={response!}
            onFollowUp={handleFollowUp}
            onBack={handleBack}
            isLoading={isLoading}
            isStreaming={isStreaming}
          />
        )}
      </Container>
    </Box>
  )
}
