import { Card, Text, Flex, Box } from '@radix-ui/themes'
import { ArrowUpIcon, ArrowDownIcon } from '@radix-ui/react-icons'
import type { Metric } from '../types'

interface MetricCardProps {
  metric: Metric
}

export function MetricCard({ metric }: MetricCardProps) {
  const isPositive = metric.changeType === 'positive'
  const isNegative = metric.changeType === 'negative'

  return (
    <Card size="2">
      <Text size="1" color="gray" mb="1">
        {metric.label}
      </Text>
      <Flex align="baseline" gap="2">
        <Text size="5" weight="bold">
          {metric.value}
        </Text>
        {metric.change && (
          <Flex
            align="center"
            gap="1"
            style={{
              color: isPositive
                ? 'var(--green-9)'
                : isNegative
                ? 'var(--red-9)'
                : 'var(--gray-9)',
            }}
          >
            {isPositive && <ArrowUpIcon width="12" height="12" />}
            {isNegative && <ArrowDownIcon width="12" height="12" />}
            <Text size="1" weight="medium">
              {metric.change}
            </Text>
          </Flex>
        )}
      </Flex>
    </Card>
  )
}
