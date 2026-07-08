import { View, Text } from '@tarojs/components';
import type { ReactNode } from 'react';
import './index.scss';

interface SketchKpiProps {
  label: string;
  value: ReactNode;
  unit?: string;
}

export default function SketchKpi({ label, value, unit }: SketchKpiProps) {
  return (
    <View className='sketch-kpi'>
      <Text className='sketch-kpi__label'>{label}</Text>
      <Text className='sketch-kpi__value'>
        {value}
        {unit && <Text className='sketch-kpi__unit'> {unit}</Text>}
      </Text>
    </View>
  );
}
