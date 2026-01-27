// API Response Types

export interface ChartData {
  series_id: string
  name: string
  unit: string
  source: string
  dates: string[]
  values: number[]
  latest: number
  latest_date: string
  is_job_change: boolean
  is_payems_level: boolean
  three_mo_avg: number | null
  yoy_change: number | null
  yoy_type: 'pp' | 'percent' | 'jobs' | null
  bullets: string[]
  sa: boolean
  recessions: RecessionPeriod[]
  description: string
}

export interface RecessionPeriod {
  start: string
  end: string
}

export interface SearchResponse {
  query: string
  summary: string
  suggestions: string[]
  chart_descriptions: Record<string, string>
  charts: ChartData[]
  temporal_context: string | null
  fed_sep_html: string | null
  recession_html: string | null
  cape_html: string | null
  polymarket_html: string | null
  metrics: Metric[]
  error: string | null
}

export interface Metric {
  label: string
  value: string
  change?: string
  changeType?: 'positive' | 'negative' | 'neutral'
}

export interface ConversationMessage {
  role: 'user' | 'assistant'
  content: string
  query?: string
  charts?: ChartData[]
}

// Component Props
export interface SearchBoxProps {
  onSearch: (query: string) => void
  isLoading: boolean
  placeholder?: string
}

export interface ChartProps {
  data: ChartData
  description?: string
}

export interface ResultsProps {
  response: SearchResponse
  onFollowUp: (query: string) => void
  isLoading: boolean
}
