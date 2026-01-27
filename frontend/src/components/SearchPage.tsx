import { useState, type FormEvent } from 'react'
import {
  Box,
  Flex,
  Heading,
  Text,
  TextField,
  Button,
  Card,
  Grid,
} from '@radix-ui/themes'
import { MagnifyingGlassIcon } from '@radix-ui/react-icons'

interface SearchPageProps {
  onSearch: (query: string) => void
  isLoading: boolean
  error: string | null
}

const QUICK_SEARCHES = [
  'How is inflation?',
  'Job market health',
  'GDP growth',
  'Fed rate outlook',
]

const EXAMPLE_QUERIES = [
  {
    title: 'Inflation',
    queries: ['CPI vs PCE inflation', 'Core inflation trend', 'Shelter costs'],
  },
  {
    title: 'Jobs',
    queries: ['Unemployment rate', 'Job openings vs hires', 'Wage growth'],
  },
  {
    title: 'Housing',
    queries: ['Home prices', 'Mortgage rates', 'Housing starts'],
  },
  {
    title: 'Fed Policy',
    queries: ['Fed rate projections', 'Yield curve', 'Recession odds'],
  },
]

export function SearchPage({ onSearch, isLoading, error }: SearchPageProps) {
  const [query, setQuery] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (query.trim()) {
      onSearch(query.trim())
    }
  }

  return (
    <Flex direction="column" align="center" justify="center" py="9" gap="6">
      {/* Hero */}
      <Box style={{ textAlign: 'center', maxWidth: 600 }}>
        <Heading size="9" mb="3" style={{ fontWeight: 700 }}>
          EconStats
        </Heading>
        <Text size="5" color="gray">
          Ask anything about U.S. economic data. Get charts, context, and AI-powered insights.
        </Text>
      </Box>

      {/* Search Box */}
      <Box style={{ width: '100%', maxWidth: 600 }}>
        <form onSubmit={handleSubmit}>
          <Flex gap="2">
            <Box style={{ flex: 1 }}>
              <TextField.Root
                size="3"
                placeholder="What do you want to know about the economy?"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={isLoading}
              >
                <TextField.Slot>
                  <MagnifyingGlassIcon height="18" width="18" />
                </TextField.Slot>
              </TextField.Root>
            </Box>
            <Button size="3" type="submit" disabled={isLoading || !query.trim()}>
              {isLoading ? 'Searching...' : 'Search'}
            </Button>
          </Flex>
        </form>

        {error && (
          <Text color="red" size="2" mt="2">
            {error}
          </Text>
        )}
      </Box>

      {/* Quick Search Buttons */}
      <Flex gap="2" wrap="wrap" justify="center">
        {QUICK_SEARCHES.map((q) => (
          <Button
            key={q}
            variant="soft"
            size="2"
            onClick={() => onSearch(q)}
            disabled={isLoading}
          >
            {q}
          </Button>
        ))}
      </Flex>

      {/* Example Queries Grid */}
      <Grid columns={{ initial: '1', sm: '2', md: '4' }} gap="4" mt="6" style={{ width: '100%', maxWidth: 900 }}>
        {EXAMPLE_QUERIES.map((category) => (
          <Card key={category.title} size="2">
            <Heading size="3" mb="2" color="gray">
              {category.title}
            </Heading>
            <Flex direction="column" gap="1">
              {category.queries.map((q) => (
                <Text
                  key={q}
                  size="2"
                  color="blue"
                  style={{ cursor: 'pointer' }}
                  onClick={() => !isLoading && onSearch(q)}
                >
                  {q}
                </Text>
              ))}
            </Flex>
          </Card>
        ))}
      </Grid>

      {/* Footer */}
      <Text size="1" color="gray" mt="6">
        Powered by FRED, BLS, and Claude AI •{' '}
        <a href="/about" style={{ color: 'var(--blue-9)' }}>
          About
        </a>
      </Text>
    </Flex>
  )
}
