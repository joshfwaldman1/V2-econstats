import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { Box, Card, Heading, Text, Flex, Badge } from '@radix-ui/themes'
import type { ChartData } from '../types'

interface ChartProps {
  data: ChartData
  description?: string
}

export function Chart({ data, description }: ChartProps) {
  const plotData = useMemo(() => {
    const trace: Plotly.Data = {
      x: data.dates,
      y: data.values,
      type: 'scatter',
      mode: 'lines',
      name: data.name,
      line: {
        color: '#3b82f6',
        width: 2,
      },
      fill: 'tozeroy',
      fillcolor: 'rgba(59, 130, 246, 0.1)',
      hovertemplate: `%{x|%b %Y}<br><b>%{y:.2f}</b> ${data.unit}<extra></extra>`,
    }

    return [trace]
  }, [data])

  const layout = useMemo((): Partial<Plotly.Layout> => {
    // Add recession shading
    const shapes: Partial<Plotly.Shape>[] = data.recessions.map((recession) => ({
      type: 'rect',
      xref: 'x',
      yref: 'paper',
      x0: recession.start,
      x1: recession.end,
      y0: 0,
      y1: 1,
      fillcolor: 'rgba(0, 0, 0, 0.08)',
      line: { width: 0 },
      layer: 'below',
    }))

    return {
      autosize: true,
      height: 300,
      margin: { l: 50, r: 20, t: 10, b: 40 },
      xaxis: {
        showgrid: false,
        tickfont: { size: 11, color: '#64748b' },
      },
      yaxis: {
        showgrid: true,
        gridcolor: '#f1f5f9',
        tickfont: { size: 11, color: '#64748b' },
        zeroline: false,
      },
      hoverlabel: {
        bgcolor: '#0f172a',
        font: { color: 'white', size: 13 },
        bordercolor: '#0f172a',
      },
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      shapes,
    }
  }, [data.recessions])

  const config: Partial<Plotly.Config> = {
    displayModeBar: false,
    responsive: true,
  }

  // Format YoY change display
  const formatYoyChange = () => {
    if (data.yoy_change === null || data.yoy_type === null) return null

    const value = data.yoy_change
    const isPositive = value > 0

    switch (data.yoy_type) {
      case 'pp':
        return `${isPositive ? '+' : ''}${value.toFixed(1)} pp YoY`
      case 'jobs':
        return `${isPositive ? '+' : ''}${(value / 1000).toFixed(0)}K jobs YoY`
      case 'percent':
        return `${isPositive ? '+' : ''}${value.toFixed(1)}% YoY`
      default:
        return null
    }
  }

  const yoyDisplay = formatYoyChange()

  return (
    <Card size="3">
      {/* Header */}
      <Flex justify="between" align="start" mb="3">
        <Box>
          <Heading size="4" mb="1">
            {data.name}
          </Heading>
          <Flex gap="2" align="center">
            <Text size="5" weight="bold">
              {data.latest?.toLocaleString(undefined, {
                minimumFractionDigits: 1,
                maximumFractionDigits: 2,
              })}{' '}
              <Text size="2" color="gray">
                {data.unit}
              </Text>
            </Text>
            {yoyDisplay && (
              <Badge
                color={
                  data.yoy_change && data.yoy_change > 0 ? 'green' : 'red'
                }
                size="1"
              >
                {yoyDisplay}
              </Badge>
            )}
          </Flex>
          <Text size="1" color="gray">
            As of {data.latest_date} • Source: {data.source}
            {data.sa && ' • Seasonally Adjusted'}
          </Text>
        </Box>
      </Flex>

      {/* Bullets */}
      {data.bullets && data.bullets.length > 0 && (
        <Box mb="3" style={{ borderLeft: '3px solid var(--blue-6)', paddingLeft: 12 }}>
          {data.bullets.map((bullet, i) => (
            <Text key={i} size="2" color="gray" as="p" mb="1">
              {bullet}
            </Text>
          ))}
        </Box>
      )}

      {/* Chart */}
      <Box className="chart-container">
        <Plot
          data={plotData}
          layout={layout}
          config={config}
          style={{ width: '100%', height: '100%' }}
          useResizeHandler
        />
      </Box>

      {/* AI Description */}
      {description && (
        <Box mt="3" pt="3" style={{ borderTop: '1px solid var(--gray-4)' }}>
          <Text size="2" color="gray">
            {description}
          </Text>
        </Box>
      )}
    </Card>
  )
}
