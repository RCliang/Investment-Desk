import { View, Text, ScrollView } from '@tarojs/components';
import type { BucketId, BucketResult } from '../../types/deepAnalysis';
import { BUCKET_DISPLAY_NAMES } from '../../types/deepAnalysis';
import './index.scss';

interface BucketTabsProps {
  buckets: BucketResult[];
  active: BucketId;
  onChange: (id: BucketId) => void;
}

export default function BucketTabs({ buckets, active, onChange }: BucketTabsProps) {
  return (
    <ScrollView className='bucket-tabs' scrollX>
      {buckets.map((b) => {
        const isActive = b.bucket_id === active;
        return (
          <View
            key={b.bucket_id}
            className={`bucket-tabs__item ${isActive ? 'bucket-tabs__item--active' : ''}`}
            onClick={() => onChange(b.bucket_id)}
          >
            <Text className='bucket-tabs__label'>{BUCKET_DISPLAY_NAMES[b.bucket_id]}</Text>
          </View>
        );
      })}
    </ScrollView>
  );
}
