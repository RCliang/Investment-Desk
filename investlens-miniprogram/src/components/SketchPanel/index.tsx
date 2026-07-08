import { View, Text } from '@tarojs/components';
import type { ReactNode } from 'react';
import './index.scss';

interface SketchPanelProps {
  title?: string;
  code?: string;
  children: ReactNode;
  className?: string;
}

export default function SketchPanel({ title, code, children, className = '' }: SketchPanelProps) {
  return (
    <View className={`sketch-panel ${className}`}>
      <View className='sketch-panel__tape' />
      {(title || code) && (
        <View className='sketch-panel__header'>
          {code && <Text className='sketch-panel__code'>{code}</Text>}
          {title && <Text className='sketch-panel__title'>{title}</Text>}
        </View>
      )}
      <View className='sketch-panel__body'>{children}</View>
    </View>
  );
}
