import { useEffect, useRef, useState } from 'react';
import { getParseStatus, parseReports } from '../../services/api';
import type { ParseStatusItem } from '../../types/deepAnalysis';

interface Props {
  code: string;
  ossKeys: string[];
  onComplete: () => void;
  onBack: () => void;
}

const POLL_INTERVAL_MS = 3000;

/**
 * Step 3: 提交 PDF 给 MinerU 解析，轮询直到全部 done/failed。
 * 进入页面时自动触发解析（除非已经全部完成）。
 */
export default function ReportParseStep({ code, ossKeys, onComplete, onBack }: Props) {
  const [details, setDetails] = useState<ParseStatusItem[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [mineruMode, setMineruMode] = useState<'live' | 'mock' | ''>('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 触发解析
  const triggerParse = async () => {
    if (ossKeys.length === 0) {
      setError('没有可解析的研报（OSS keys 为空）');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const resp = await parseReports(code, ossKeys);
      setMineruMode(resp.mineru_mode);
    } catch (e) {
      setError(`解析提交失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSubmitting(false);
    }
  };

  // 轮询状态
  useEffect(() => {
    if (ossKeys.length === 0) return;

    // 进入时立即触发一次解析（如果需要）
    triggerParse();

    // 启动轮询
    pollRef.current = setInterval(async () => {
      try {
        const status = await getParseStatus(code);
        setDetails(status.details);
        // 全部终止条件
        if (status.pending === 0 && status.total > 0) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      } catch (e) {
        // 轮询单次失败不致命
        console.warn('parse-status poll failed', e);
      }
    }, POLL_INTERVAL_MS);

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, ossKeys.join(',')]);

  const doneCount = details.filter((d) => d.status === 'done').length;
  const failedCount = details.filter((d) => d.status === 'failed').length;
  const pendingCount = details.filter((d) => d.status === 'parsing').length;
  const total = details.length || ossKeys.length;
  const allSettled = total > 0 && pendingCount === 0 && details.length > 0;
  const canProceed = allSettled && doneCount > 0;

  return (
    <div>
      <div className="da-row-between">
        <div>
          <div style={{ fontSize: 15, color: 'var(--da-text)' }}>
            MinerU 解析进度：{doneCount} done / {pendingCount} parsing / {failedCount} failed
            {total > 0 && ` / ${total}`}
          </div>
          {mineruMode && (
            <div style={{ fontSize: 12, color: 'var(--da-text-soft)', marginTop: 4 }}>
              模式：{mineruMode === 'mock' ? 'mock（未配置 MINERU_API_KEY）' : 'live'}
            </div>
          )}
        </div>
        <div className="da-row">
          <button className="da-btn da-btn-ghost" onClick={onBack} disabled={submitting}>
            ← 返回
          </button>
          <button
            className="da-btn"
            onClick={onComplete}
            disabled={!canProceed}
          >
            下一步：AI 分析 →
          </button>
        </div>
      </div>

      {error && <div className="da-error">{error}</div>}

      <div style={{ marginTop: 16 }}>
        {details.length === 0 && (
          <div className="da-empty">
            {submitting ? '正在提交解析请求...' : '等待解析'}
          </div>
        )}
        {details.map((d) => (
          <div key={d.oss_key} className="da-status-row">
            <div className="da-status-text">
              <span className={`da-status-icon ${
                d.status === 'done' ? 'ok' :
                d.status === 'failed' ? 'fail' : 'pending'
              }`}>
                {d.status === 'done' ? '✓' :
                 d.status === 'failed' ? '✗' : '⏳'}
              </span>
              {_shortenKey(d.oss_key)}
              {d.status === 'done' && d.token_count && (
                <span className="da-status-meta">{d.token_count} tokens</span>
              )}
              {d.status === 'failed' && (
                <span className="da-status-meta">失败：{d.error || 'unknown'}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {allSettled && failedCount > 0 && (
        <div style={{ marginTop: 16, fontSize: 12, color: 'var(--da-warn)' }}>
          ⚠ 有 {failedCount} 篇解析失败，可继续用已成功的部分进行 AI 分析
        </div>
      )}
    </div>
  );
}

function _shortenKey(ossKey: string): string {
  // reports/301095/2026-03-15_华泰_广立微.pdf → 2026-03-15_华泰_广立微.pdf
  const parts = ossKey.split('/');
  return parts[parts.length - 1] || ossKey;
}
