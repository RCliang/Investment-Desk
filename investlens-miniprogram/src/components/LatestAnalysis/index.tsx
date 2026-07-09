import { useState, useEffect } from 'react';
import { View, Text } from '@tarojs/components';
import { getLatestAnalysis } from '../../services/chainkb';
import type { AnalysisDoc, BucketId } from '../../types/deepAnalysis';
import { COMPANY_TYPE_LABELS } from '../../types/deepAnalysis';
import BucketTabs from '../BucketTabs';
import BucketFieldCard from '../BucketFieldCard';
import './index.scss';

interface LatestAnalysisProps {
  ticker: string;
}

export default function LatestAnalysis({ ticker }: LatestAnalysisProps) {
  const [doc, setDoc] = useState<AnalysisDoc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeBucket, setActiveBucket] = useState<BucketId | null>(null);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getLatestAnalysis(ticker)
      .then((d) => {
        if (cancelled) return;
        setDoc(d);
        if (d && d.buckets.length > 0) setActiveBucket(d.buckets[0].bucket_id);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [ticker]);

  if (loading) {
    return (
      <View className='latest-analysis'>
        <Text className='latest-analysis__title'>最新 AI 分析</Text>
        <Text className='latest-analysis__status'>加载中…</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View className='latest-analysis'>
        <Text className='latest-analysis__title'>最新 AI 分析</Text>
        <Text className='latest-analysis__status latest-analysis__status--err'>加载失败: {error}</Text>
      </View>
    );
  }

  if (!doc) {
    return (
      <View className='latest-analysis'>
        <Text className='latest-analysis__title'>最新 AI 分析</Text>
        <Text className='latest-analysis__empty'>暂无 AI 分析 (需要管理员在 Web 端生成)</Text>
      </View>
    );
  }

  const activeBucketData = doc.buckets.find((b) => b.bucket_id === activeBucket);
  const fieldEntries = activeBucketData ? Object.entries(activeBucketData.fields) : [];

  return (
    <View className='latest-analysis'>
      <View className='latest-analysis__head'>
        <Text className='latest-analysis__title'>最新 AI 分析</Text>
        <Text className='latest-analysis__meta'>
          {COMPANY_TYPE_LABELS[doc.company_type]} · {doc.model_name} · {new Date(doc.analyzed_at).toLocaleDateString('zh-CN')}
        </Text>
      </View>

      <BucketTabs
        buckets={doc.buckets}
        active={activeBucket ?? doc.buckets[0].bucket_id}
        onChange={setActiveBucket}
      />

      <View className='latest-analysis__fields'>
        {fieldEntries.length === 0 ? (
          <Text className='latest-analysis__empty'>该类别暂无字段</Text>
        ) : (
          fieldEntries.map(([name, field]) => (
            <BucketFieldCard key={name} name={name} field={field} />
          ))
        )}
      </View>
    </View>
  );
}
