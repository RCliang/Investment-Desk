import { useEffect, useRef, useState } from 'react';
import { getAnalysisHistory, streamAnalyze } from '../../services/api';
import type {
  CompanyType, BucketId, BucketResult, AnalysisDoc, HistoryItem,
} from '../../types/deepAnalysis';
import BucketTabs, { type BucketState } from './BucketTabs';

interface Props {
  code: string;
  ossKeys: string[];
  companyType: CompanyType;
  /**
   * 父组件持有 analysisDoc 并由本组件通过 onAnalysisDocChange 回写。
   * Step 4 内部不读取父级持有的 analysisDoc(使用自身 bucketResults 状态渲染),
   * 因此该 prop 当前未在函数体内引用。保留在 Props 中以维持 API 一致性。
   */
  analysisDoc: AnalysisDoc | null;
  onAnalysisDocChange: (doc: AnalysisDoc | null) => void;
  onBack: () => void;
}

type Phase = 'idle' | 'running' | 'cached' | 'done' | 'error';

/**
 * Step 4: 调 SSE 流式结构化分析，按桶 Tab 展示。
 *
 * 企业类型在 Step 1 选定后即锁定(修改会让缓存失效),
 * 因此本组件不暴露 onCompanyTypeChange;只通过 meta 文本展示当前类型。
 */
export default function AnalysisResultStep({
  code, ossKeys, companyType,
  analysisDoc: _analysisDoc,
  onAnalysisDocChange, onBack,
}: Props) {
  // _analysisDoc 由父组件持有,本组件渲染依赖自身 bucketResults,无需读取。
  void _analysisDoc;
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [bucketOrder, setBucketOrder] = useState<BucketId[]>([]);
  const [bucketState, setBucketState] = useState<Record<BucketId, BucketState>>({} as Record<BucketId, BucketState>);
  const [bucketResults, setBucketResults] = useState<Partial<Record<BucketId, BucketResult>>>({});
  const [bucketErrors, setBucketErrors] = useState<Partial<Record<BucketId, string>>>({});
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    if (ossKeys.length === 0) return;
    startedRef.current = true;
    runAnalyze(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, ossKeys.join(','), companyType]);

  const resetBuckets = () => {
    setBucketOrder([]);
    setBucketState({} as Record<BucketId, BucketState>);
    setBucketResults({});
    setBucketErrors({});
    onAnalysisDocChange(null);
  };

  const runAnalyze = async (forceRefresh: boolean) => {
    if (phase === 'running') return;
    setPhase('running');
    setError('');
    resetBuckets();

    try {
      await streamAnalyze(code, ossKeys, companyType, {
        onStart: (payload) => {
          setBucketOrder(payload.buckets);
          const init: Record<BucketId, BucketState> = {} as Record<BucketId, BucketState>;
          payload.buckets.forEach((b) => { init[b] = 'pending'; });
          setBucketState(init);
        },
        onBucketStart: (bid) => {
          setBucketState((s) => ({ ...s, [bid]: 'running' }));
        },
        onBucketDone: (bid, result) => {
          setBucketState((s) => ({ ...s, [bid]: 'done' }));
          setBucketResults((r) => ({ ...r, [bid]: result }));
        },
        onBucketError: (bid, err) => {
          setBucketState((s) => ({ ...s, [bid]: 'error' }));
          setBucketErrors((e) => ({ ...e, [bid]: err }));
        },
        onCached: (doc) => {
          onAnalysisDocChange(doc);
          setBucketOrder(doc.buckets.map((b) => b.bucket_id));
          const init: Record<BucketId, BucketState> = {} as Record<BucketId, BucketState>;
          doc.buckets.forEach((b) => { init[b.bucket_id] = 'done'; });
          setBucketState(init);
          const rs: Partial<Record<BucketId, BucketResult>> = {};
          doc.buckets.forEach((b) => { rs[b.bucket_id] = b; });
          setBucketResults(rs);
          setPhase('cached');
        },
        onDone: () => {
          setPhase('done');
        },
        onError: (err) => {
          setError(err);
          setPhase('error');
        },
      }, { forceRefresh });
    } catch (e) {
      setError(`分析失败: ${e instanceof Error ? e.message : String(e)}`);
      setPhase('error');
    }
  };

  const toggleHistory = async () => {
    if (!showHistory) {
      try {
        const resp = await getAnalysisHistory(code);
        setHistory(resp.analyses || []);
      } catch (e) {
        console.warn('load history failed', e);
      }
    }
    setShowHistory(!showHistory);
  };

  const okCount = Object.values(bucketState).filter((s) => s === 'done').length;
  const errCount = Object.values(bucketState).filter((s) => s === 'error').length;

  return (
    <div>
      <div className="da-row-between">
        <div>
          <div style={{ fontSize: 16, color: 'var(--da-text)', fontWeight: 600 }}>
            AI 结构化分析
            {phase === 'cached' && (
              <span style={{ marginLeft: 12, color: 'var(--da-success)', fontSize: 12 }}>
                ✓ 缓存命中
              </span>
            )}
            {phase === 'running' && (
              <span style={{ marginLeft: 12, color: 'var(--da-accent)', fontSize: 12 }}>
                ● 流式中 ({okCount}/{bucketOrder.length})
              </span>
            )}
            {phase === 'done' && (
              <span style={{ marginLeft: 12, color: 'var(--da-success)', fontSize: 12 }}>
                ✓ 完成 {okCount} 桶成功{errCount > 0 && ` / ${errCount} 桶失败`}
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: 'var(--da-text-soft)', marginTop: 4 }}>
            基于 {ossKeys.length} 篇研报 · 股票代码 {code} · 类型 {companyType}
          </div>
        </div>
        <div className="da-row">
          <button className="da-btn da-btn-ghost" onClick={onBack} disabled={phase === 'running'}>
            ← 返回
          </button>
          <button className="da-btn da-btn-ghost" onClick={toggleHistory}>
            {showHistory ? '隐藏历史' : '查看历史'}
          </button>
          <button
            className="da-btn"
            onClick={() => runAnalyze(true)}
            disabled={phase === 'running' || ossKeys.length === 0}
          >
            {phase === 'running' ? '分析中...' : '重新分析'}
          </button>
        </div>
      </div>

      {error && <div className="da-error">{error}</div>}

      {showHistory && (
        <div className="da-history-list">
          <div style={{ fontSize: 12, color: 'var(--da-text-soft)', marginBottom: 8 }}>
            历史分析（{history.length} 条）
          </div>
          {history.length === 0 ? (
            <div className="da-empty">暂无历史</div>
          ) : (
            history.map((h) => (
              <div key={h.id} className="da-history-item">
                <span>#{h.id} · {h.created_at.slice(0, 16).replace('T', ' ')}</span>
                <span style={{ color: 'var(--da-text-soft)' }}>
                  {(h as any).analysis_version === 'v2' ? '[v2] ' : '[v1] '}
                  {(h as any).company_type && `${(h as any).company_type} · `}
                  {h.report_count} 篇 · {(h.preview || '').slice(0, 50)}
                </span>
              </div>
            ))
          )}
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        {bucketOrder.length > 0 ? (
          <BucketTabs
            bucketOrder={bucketOrder}
            bucketState={bucketState}
            bucketResults={bucketResults}
            bucketErrors={bucketErrors}
          />
        ) : (
          <div className="da-empty">
            {phase === 'running' ? '正在初始化...' : '点击「重新分析」开始'}
          </div>
        )}
      </div>
    </div>
  );
}
