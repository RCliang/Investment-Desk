import { View, Text } from '@tarojs/components';
import './index.scss';

interface MarketBadgeProps {
  market: string;
}

const COLORS: Record<string, string> = {
  SH: 'sh',
  SZ: 'sz',
  BJ: 'bj',
  HK: 'hk',
  US: 'us',
};

export default function MarketBadge({ market }: MarketBadgeProps) {
  const cls = COLORS[market] || 'other';
  return (
    <View className={`market-badge market-badge--${cls}`}>
      <Text className='market-badge__text'>{market}</Text>
    </View>
  );
}
