import { View, Text } from '@tarojs/components';
import type { SubIndustry } from '../../types/chainkb';
import './index.scss';

interface SubIndustryCardProps {
  sub: SubIndustry;
  onClick: (groupId: string) => void;
}

export default function SubIndustryCard({ sub, onClick }: SubIndustryCardProps) {
  return (
    <View className='sub-card' onClick={() => onClick(sub.group_id)}>
      <Text className='sub-card__name'>{sub.name_zh}</Text>
      <View className='sub-card__meta'>
        <Text className='sub-card__group'>{sub.group_id}</Text>
        <Text className='sub-card__count'>{sub.company_count} 家</Text>
      </View>
    </View>
  );
}
