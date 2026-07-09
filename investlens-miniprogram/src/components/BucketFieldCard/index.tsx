import { View, Text } from '@tarojs/components';
import type { FieldValue, Evidence } from '../../types/deepAnalysis';
import { fieldLabel } from '../../types/deepAnalysis';
import './index.scss';

interface BucketFieldCardProps {
  name: string;
  field: FieldValue;
}

const EVIDENCE_LABEL: Record<Evidence, string> = {
  strong:  '强证据',
  medium:  '中等证据',
  weak:    '弱证据',
  unknown: '未知',
};

const EVIDENCE_CLS: Record<Evidence, string> = {
  strong:  'bucket-field--strong',
  medium:  'bucket-field--medium',
  weak:    'bucket-field--weak',
  unknown: 'bucket-field--unknown',
};

function renderValue(v: FieldValue['value']): string {
  if (v == null) return '—';
  if (Array.isArray(v)) return v.length ? v.join('、') : '—';
  return String(v);
}

export default function BucketFieldCard({ name, field }: BucketFieldCardProps) {
  return (
    <View className={`bucket-field ${EVIDENCE_CLS[field.evidence]}`}>
      <View className='bucket-field__head'>
        <Text className='bucket-field__name'>{fieldLabel(name)}</Text>
        <Text className='bucket-field__evidence'>{EVIDENCE_LABEL[field.evidence]}</Text>
      </View>
      <Text className='bucket-field__value'>{renderValue(field.value)}</Text>
      {field.quote && (
        <Text className='bucket-field__quote'>「{field.quote}」</Text>
      )}
    </View>
  );
}
