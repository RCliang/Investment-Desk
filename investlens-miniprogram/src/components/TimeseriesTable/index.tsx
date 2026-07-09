import { View, Text, ScrollView } from '@tarojs/components';
import type { ReactNode } from 'react';
import './index.scss';

export interface Column {
  key: string;
  label: string;
  width?: number;
  align?: 'left' | 'right';
  render?: (row: Record<string, unknown>) => ReactNode;
}

interface TimeseriesTableProps {
  columns: Column[];
  rows: Record<string, unknown>[];
  emptyText?: string;
}

export default function TimeseriesTable({ columns, rows, emptyText = '暂无数据' }: TimeseriesTableProps) {
  return (
    <View className='ts-table'>
      <View className='ts-table__head'>
        {columns.map((col) => (
          <Text
            key={col.key}
            className='ts-table__head-cell'
            style={{ flex: col.width ?? 1, textAlign: col.align ?? 'left' }}
          >
            {col.label}
          </Text>
        ))}
      </View>

      {rows.length === 0 ? (
        <View className='ts-table__empty'><Text>{emptyText}</Text></View>
      ) : (
        <ScrollView scrollY className='ts-table__body'>
          {rows.map((row, i) => (
            <View key={i} className='ts-table__row'>
              {columns.map((col) => (
                <Text
                  key={col.key}
                  className='ts-table__cell'
                  style={{ flex: col.width ?? 1, textAlign: col.align ?? 'left' }}
                >
                  {col.render ? col.render(row) : formatDefault(row[col.key])}
                </Text>
              ))}
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

function formatDefault(v: unknown): string {
  if (v == null || v === '') return '—';
  if (typeof v === 'number') {
    if (Number.isNaN(v)) return '—';
    return String(v);
  }
  return String(v);
}
