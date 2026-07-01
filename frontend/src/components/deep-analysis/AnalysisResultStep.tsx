import { useEffect, useRef, useState } from 'react';
import { getAnalysisHistory, streamAnalyze } from '../../services/api';
import type { HistoryItem } from '../../types/deepAnalysis';
import MarkdownRenderer from '../MarkdownRenderer';

interface Props {
  code: string;
  ossKeys: string[];
  analysisText: string;
  onAnalysisUpdate: (text: string) => void;
  onBack: () => void;
}

/**
 * Step 4: 调 SSE 流式 AI 分析，markdown 实时渲染。
 * 进入页面自动触发一次；支持强制重新分析、查看历史记录。
 */
export default function AnalysisResultStep({
  code, ossKeys, analysisText, onAnalysisUpdate, onBack,
}: Props) {
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [cacheHit, setCacheHit] = useState(false);
  const startedRef = useRef(false);
  const accumulatedRef = useRef('');

  // 进入页面自动触发一次（仅当 ossKeys 非空且未启动过）
  useEffect(() => {
    if (startedRef.current) return;
    if (ossKeys.length === 0) return;
    startedRef.current = true;
    runAnalyze(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, ossKeys.join(',')]);

  const runAnalyze = async (forceRefresh: boolean) => {
    if (streaming) return;
    setStreaming(true);
    setError('');
    setCacheHit(false);
    accumulatedRef.current = '';
    onAnalysisUpdate('');

    try {
      await streamAnalyze(code, ossKeys, {
        onChunk: (content) => {
          accumulatedRef.current += content;
          onAnalysisUpdate(accumulatedRef.current);
        },
        onCached: (payload) => {
          accumulatedRef.current = payload.analysis_text;
          onAnalysisUpdate(accumulatedRef.current);
          setCacheHit(true);
        },
        onDone: (info) => {
          if (info.cache_hit) setCacheHit(true);
        },
        onError: (err) => setError(err),
      }, { forceRefresh });
    } catch (e) {
      setError(`分析失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setStreaming(false);
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

  return (
    <div>
      <div className="da-row-between">
        <div>
          <div style={{ fontSize: 15, color: 'var(--da-text)' }}>
            AI 多维度分析
            {cacheHit && (
              <span style={{ marginLeft: 12, color: 'var(--da-success)', fontSize: 12 }}>
                ✓ 缓存命中
              </span>
            )}
            {streaming && (
              <span style={{ marginLeft: 12, color: 'var(--da-accent)', fontSize: 12 }}>
                ● 流式中...
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: 'var(--da-text-soft)', marginTop: 4 }}>
            基于 {ossKeys.length} 篇研报 · 股票代码 {code}
          </div>
        </div>
        <div className="da-row">
          <button className="da-btn da-btn-ghost" onClick={onBack} disabled={streaming}>
            ← 返回
          </button>
          <button className="da-btn da-btn-ghost" onClick={toggleHistory}>
            {showHistory ? '隐藏历史' : '查看历史'}
          </button>
          <button
            className="da-btn"
            onClick={() => runAnalyze(true)}
            disabled={streaming || ossKeys.length === 0}
          >
            {streaming ? '分析中...' : '重新分析'}
          </button>
        </div>
      </div>

      {error && <div className="da-error">分析错误：{error}</div>}

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
                  {h.report_count} 篇 · {(h.preview || '').slice(0, 50)}
                </span>
              </div>
            ))
          )}
        </div>
      )}

      <div className="da-analysis-output" style={{ marginTop: 16 }}>
        {analysisText ? (
          <>
            <MarkdownRenderer content={analysisText} />
            {streaming && <span className="da-cursor" />}
          </>
        ) : (
          <div className="da-empty">
            {streaming ? '正在生成...' : '点击「重新分析」开始'}
          </div>
        )}
      </div>
    </div>
  );
}
