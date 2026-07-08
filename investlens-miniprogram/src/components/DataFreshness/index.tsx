import { View, Text } from '@tarojs/components';
import type { FreshnessEntry } from '../../types/chainkb';
import { formatAgo } from '../../utils/format';
import './index.scss';

interface DataFreshnessProps {
  market?: FreshnessEntry | null;
  finance?: FreshnessEntry | null;
  variant?: 'compact' | 'full';
}

export default function DataFreshness({ market, finance, variant = 'compact' }: DataFreshnessProps) {
  if (variant === 'compact') {
    return (
      <View className='data-freshness data-freshness--compact'>
        <Text className='data-freshness__item'>
          行情 <Text className='data-freshness__time'>{formatAgo(market?.minutes_ago ?? null)}</Text>
        </Text>
        <Text className='data-freshness__sep'>·</Text>
        <Text className='data-freshness__item'>
          财务 <Text className='data-freshness__time'>{formatAgo(finance?.minutes_ago ?? null)}</Text>
        </Text>
      </View>
    );
  }

  return (
    <View className='data-freshness data-freshness--full'>
      <View className='data-freshness__row'>
        <Text className='data-freshness__label'>行情数据</Text>
        <Text className='data-freshness__value'>{formatAgo(market?.minutes_ago ?? null)}</Text>
      </View>
      <View className='data-freshness__row'>
        <Text className='data-freshness__label'>财务数据</Text>
        <Text className='data-freshness__value'>{formatAgo(finance?.minutes_ago ?? null)}</Text>
      </View>
    </View>
  );
}
