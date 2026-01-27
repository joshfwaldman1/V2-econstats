import { useState, useCallback } from 'react'
import { Box, Container } from '@radix-ui/themes'
import { SearchPage } from './components/SearchPage'
import { ResultsPage } from './components/ResultsPage'
import { searchQuery } from './lib/api'
import type { SearchResponse } from './types'

type View = 'search' | 'results'

export default function App() {
  const [view, setView] = useState<View>('search')
  const [isLoading, setIsLoading] = useState(false)
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [history, setHistory] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const handleSearch = useCallback(async (query: string) => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await searchQuery(query, history)
      setResponse(result)
      setHistory(prev => [...prev, query])
      setView('results')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setIsLoading(false)
    }
  }, [history])

  const handleFollowUp = useCallback(async (query: string) => {
    await handleSearch(query)
  }, [handleSearch])

  const handleBack = useCallback(() => {
    setView('search')
    setResponse(null)
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
          />
        )}
      </Container>
    </Box>
  )
}
