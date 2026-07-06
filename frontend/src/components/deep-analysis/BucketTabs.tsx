import { useState } from 'react';
import type { BucketId, BucketResult } from '../../types/deepAnalysis';
import { BUCKET_DISPLAY_NAMES } from '../../types/deepAnalysis';
import BucketFieldCard from './BucketFieldCard';

export type BucketState = 'pending' | 'running' | 'done' | 'error';

interface Props {
  bucketOrder: BucketId[];
  bucketState: Record<BucketId, BucketState>;
  bucketResults: Partial<Record<BucketId, BucketResult>>;
  bucketErrors: Partial<Record<BucketId, string>>;
}

/**
 * Tab 容器:每桶一 Tab,Tab 标题显示状态(灰/spinner/绿✓/红✗)。
 */
export default function BucketTabs({
  bucketOrder, bucketState, bucketResults, bucketErrors,
}: Props) {
  const [active, setActive] = useState<BucketId | null>(null);

  // 默认选第一个 done 的 Tab,否则选第一个
  const defaultActive: BucketId | null =
    active ?? bucketOrder.find((b) => bucketState[b] === 'done') ?? bucketOrder[0] ?? null;

  return (
    <div className="bucket-tabs">
      <div className="tab-header">
        {bucketOrder.map((bid) => {
          const st = bucketState[bid] || 'pending';
          const isActive = defaultActive === bid;
          return (
            <button
              key={bid}
              type="button"
              className={`tab ${isActive ? 'active' : ''} st-${st}`}
              onClick={() => setActive(bid)}
            >
              <span className="tab-status">
                {st === 'done' && '✓'}
                {st === 'error' && '✗'}
                {st === 'running' && <span className="spinner" />}
                {st === 'pending' && '·'}
              </span>
              <span className="tab-label">{BUCKET_DISPLAY_NAMES[bid]}</span>
            </button>
          );
        })}
      </div>

      <div className="tab-body">
        {defaultActive && bucketState[defaultActive] === 'done' && bucketResults[defaultActive] && (
          <div className="field-grid">
            {Object.entries(bucketResults[defaultActive]!.fields).map(([name, field]) => (
              <BucketFieldCard key={name} name={name} field={field} />
            ))}
          </div>
        )}
        {defaultActive && bucketState[defaultActive] === 'running' && (
          <div className="tab-skeleton">解析中...</div>
        )}
        {defaultActive && bucketState[defaultActive] === 'pending' && (
          <div className="tab-empty">等待中</div>
        )}
        {defaultActive && bucketState[defaultActive] === 'error' && (
          <div className="tab-error">
            该模块解析失败:{bucketErrors[defaultActive] || '未知错误'}
          </div>
        )}
      </div>
    </div>
  );
}
