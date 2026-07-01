import { useState } from 'react';
import type { ResearchReport, DownloadResult } from '../../types/deepAnalysis';
import { downloadReports } from '../../services/api';

interface Props {
  code: string;
  reports: ResearchReport[];
  results: DownloadResult[];
  onResultsChange: (results: DownloadResult[]) => void;
  onComplete: (results: DownloadResult[]) => void;
  onBack: () => void;
}

/**
 * Step 2: 把选中的研报下载到 OSS。
 * 进入页面时如有已存结果直接展示，否则等用户点「开始下载」。
 */
export default function ReportDownloadStep({
  code, reports, results, onResultsChange, onComplete, onBack,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleDownload = async () => {
    setLoading(true);
    setError('');
    try {
      const payload = reports.map((r) => ({
        info_code: r.info_code,
        publish_date: r.publish_date,
        org_name: r.org_name,
        title: r.title,
      }));
      const resp = await downloadReports(code, payload);
      onResultsChange(resp.results);
    } catch (e) {
      setError(`下载失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  };

  const successCount = results.filter((r) => r.status === 'ok' || r.status === 'exists').length;
  const failedCount = results.filter((r) => r.status === 'failed').length;
  const allDone = results.length > 0 && results.length === reports.length;
  const canProceed = allDone && successCount > 0;

  return (
    <div>
      <div className="da-row-between">
        <div>
          <div style={{ fontSize: 15, color: 'var(--da-text)' }}>
            准备下载 {reports.length} 篇研报到 OSS
          </div>
          <div style={{ fontSize: 12, color: 'var(--da-text-soft)', marginTop: 4 }}>
            路径：reports/{code}/&lt;日期&gt;_&lt;机构&gt;_&lt;标题&gt;.pdf
          </div>
        </div>
        <div className="da-row">
          <button className="da-btn da-btn-ghost" onClick={onBack} disabled={loading}>
            ← 返回
          </button>
          {results.length === 0 ? (
            <button className="da-btn" onClick={handleDownload} disabled={loading || reports.length === 0}>
              {loading ? '下载中...' : '开始下载'}
            </button>
          ) : (
            <>
              <button className="da-btn da-btn-ghost" onClick={handleDownload} disabled={loading}>
                {loading ? '重试中...' : '重新下载失败项'}
              </button>
              <button
                className="da-btn"
                onClick={() => onComplete(results)}
                disabled={!canProceed}
              >
                下一步：解析 PDF →
              </button>
            </>
          )}
        </div>
      </div>

      {error && <div className="da-error">{error}</div>}

      {results.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--da-text-soft)', marginBottom: 8 }}>
            成功 {successCount} / 失败 {failedCount} / 总计 {results.length}
          </div>
          {results.map((r) => (
            <div key={r.info_code} className="da-status-row">
              <div className="da-status-text">
                <span className={`da-status-icon ${
                  r.status === 'ok' || r.status === 'exists' ? 'ok' :
                  r.status === 'failed' ? 'fail' : 'pending'
                }`}>
                  {r.status === 'ok' ? '✓' : r.status === 'exists' ? '✓' : '✗'}
                </span>
                {r.filename || r.info_code}
                {r.status === 'exists' && (
                  <span className="da-status-meta">已存在</span>
                )}
                {r.status === 'failed' && (
                  <span className="da-status-meta">失败：{r.error || 'unknown'}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {results.length === 0 && !loading && (
        <div className="da-empty">点击「开始下载」批量上传 PDF 到 OSS</div>
      )}
    </div>
  );
}
