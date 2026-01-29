import { useState, type FormEvent } from 'react'
import {
  Box,
  Flex,
  Heading,
  Text,
  TextField,
  Button,
  Card,
  Badge,
  Separator,
  Grid,
  IconButton,
  Link,
} from '@radix-ui/themes'
import {
  ArrowLeftIcon,
  PaperPlaneIcon,
  PersonIcon,
  ChatBubbleIcon,
} from '@radix-ui/react-icons'
import { Chart } from './Chart'
import { MetricCard } from './MetricCard'
import type { SearchResponse } from '../types'

interface ResultsPageProps {
  response: SearchResponse
  onFollowUp: (query: string) => void
  onBack: () => void
  isLoading: boolean
  isStreaming?: boolean
}

export function ResultsPage({
  response,
  onFollowUp,
  onBack,
  isLoading,
  isStreaming = false,
}: ResultsPageProps) {
  const [followUpQuery, setFollowUpQuery] = useState('')

  const handleFollowUpSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (followUpQuery.trim()) {
      onFollowUp(followUpQuery.trim())
      setFollowUpQuery('')
    }
  }

  return (
    <Box py="4" className="fade-in">
      {/* Header */}
      <Flex align="center" justify="between" mb="4">
        <Flex align="center" gap="3">
          <IconButton variant="ghost" onClick={onBack}>
            <ArrowLeftIcon width="20" height="20" />
          </IconButton>
          <Heading size="5">EconStats</Heading>
        </Flex>
        <Button variant="ghost" onClick={onBack}>
          New Search
        </Button>
      </Flex>

      <Separator size="4" mb="6" />

      {/* User Query */}
      <Flex gap="3" mb="4">
        <Box
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            background: 'var(--gray-4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <PersonIcon width="16" height="16" />
        </Box>
        <Box>
          <Text weight="medium">{response.query}</Text>
          {response.temporal_context && (
            <Badge color="blue" size="1" ml="2">
              {response.temporal_context}
            </Badge>
          )}
        </Box>
      </Flex>

      {/* AI Response */}
      <Flex gap="3" mb="2">
        <Box
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            background: 'var(--blue-4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <ChatBubbleIcon width="16" height="16" color="var(--blue-9)" />
        </Box>
        <Card style={{ flex: 1 }}>
          <Text size="3" style={{ lineHeight: 1.6 }}>
            {response.summary || (isStreaming ? '' : 'Generating summary...')}
            {isStreaming && (
              <span
                style={{
                  display: 'inline-block',
                  width: 2,
                  height: '1em',
                  background: 'var(--blue-9)',
                  marginLeft: 2,
                  verticalAlign: 'text-bottom',
                  animation: 'blink 1s step-end infinite',
                }}
              />
            )}
          </Text>
        </Card>
      </Flex>

      {/* Source Citations */}
      {response.sources && response.sources.length > 0 && (
        <Flex gap="1" align="center" ml="9" mb="6" wrap="wrap">
          <Text size="1" color="gray">Sources:</Text>
          {response.sources.map((source, i) => (
            <span key={source.series_id}>
              {i > 0 && <Text size="1" color="gray"> · </Text>}
              <Link
                size="1"
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                title={source.name}
                highContrast
              >
                {source.series_id}
              </Link>
            </span>
          ))}
        </Flex>
      )}

      {/* Special Data Boxes */}
      {response.fed_sep_html && (
        <Card mb="4">
          <div dangerouslySetInnerHTML={{ __html: response.fed_sep_html }} />
        </Card>
      )}

      {response.recession_html && (
        <Card mb="4">
          <div dangerouslySetInnerHTML={{ __html: response.recession_html }} />
        </Card>
      )}

      {/* Metrics Grid */}
      {response.metrics && response.metrics.length > 0 && (
        <Grid columns={{ initial: '2', md: '4' }} gap="3" mb="6">
          {response.metrics.map((metric, i) => (
            <MetricCard key={i} metric={metric} />
          ))}
        </Grid>
      )}

      {/* Charts */}
      {response.charts && response.charts.length > 0 && (
        <Flex direction="column" gap="4" mb="6">
          {response.charts.map((chart) => (
            <Chart
              key={chart.series_id}
              data={chart}
              description={response.chart_descriptions?.[chart.series_id]}
            />
          ))}
        </Flex>
      )}

      {/* Follow-up Suggestions */}
      <Box mb="6">
        {response.suggestions && response.suggestions.length > 0 && (
          <>
            <Text size="2" color="gray" mb="3">
              Continue exploring:
            </Text>
            <Flex gap="2" wrap="wrap" mb="4">
              {response.suggestions.map((suggestion) => (
                <Button
                  key={suggestion}
                  variant="outline"
                  size="2"
                  onClick={() => onFollowUp(suggestion)}
                  disabled={isLoading || isStreaming}
                >
                  {suggestion}
                </Button>
              ))}
            </Flex>
          </>
        )}

        {/* Follow-up Input */}
        <form onSubmit={handleFollowUpSubmit}>
          <Flex gap="2">
            <Box style={{ flex: 1 }}>
              <TextField.Root
                size="3"
                placeholder="Ask a follow-up question..."
                value={followUpQuery}
                onChange={(e) => setFollowUpQuery(e.target.value)}
                disabled={isLoading || isStreaming}
              />
            </Box>
            <IconButton
              size="3"
              type="submit"
              disabled={isLoading || isStreaming || !followUpQuery.trim()}
            >
              <PaperPlaneIcon width="18" height="18" />
            </IconButton>
          </Flex>
        </form>
      </Box>

      {/* Loading indicator */}
      {isLoading && (
        <Flex align="center" justify="center" py="4">
          <Box className="animate-pulse">
            <Text color="gray">Loading...</Text>
          </Box>
        </Flex>
      )}

      {/* CSS for blinking cursor animation */}
      <style>{`
        @keyframes blink {
          50% { opacity: 0; }
        }
      `}</style>
    </Box>
  )
}
