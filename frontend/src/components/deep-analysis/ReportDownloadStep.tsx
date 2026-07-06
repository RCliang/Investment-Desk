import { useState } from 'react';
import axios from 'axios';
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
 * 把下载失败的异常转成给用户看的中文消息。
 * FastAPI 422 校验错误会返回 {detail:[{msg,...},...]},提取首条 msg 让用户看到具体哪个字段不合法。
 */
function describeDownloadError(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const status = e.response?.status;
    const data = e.response?.data;
    if (status === 422) {
      let detail: unknown = data;
      if (data && typeof data === 'object' && 'detail' in data) {
        detail = (data as { detail: unknown }).detail;
      }
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: string; loc?: unknown };
        const loc = Array.isArray(first.loc) ? first.loc.join('.') : '';
        return `字段校验失败(422): ${first.msg ?? '未知错误'}${loc ? ` [${loc}]` : ''}`;
      }
      if (typeof detail === 'string') return `字段校验失败(422): ${detail}`;
      return '字段校验失败(422),请检查研报数据是否完整';
    }
    if (status && status >= 500) {
      return `服务器错误(${status}),请稍后重试`;
    }
    return e.message || `请求失败(${status ?? 'network'})`;
  }
  return e instanceof Error ? e.message : String(e);
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
      // 防御性过滤:即使后端已丢掉无 infoCode 的脏数据,这里再保一道闸。
      const payload = reports
        .filter((r) => r.info_code)
        .map((r) => ({
          info_code: r.info_code,
          publish_date: r.publish_date,
          org_name: r.org_name,
          title: r.title,
        }));
      if (payload.length === 0) {
        setError('没有可下载的有效研报(所有行均缺少 info_code)');
        return;
      }
      const resp = await downloadReports(code, payload);
      onResultsChange(resp.results);
    } catch (e) {
      setError(`下载失败: ${describeDownloadError(e)}`);
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
      <div className="row-between">
        <div>
          <div style={{ fontSize: 15, color: 'var(--ink)' }}>
            准备下载 {reports.length} 篇研报到 OSS
          </div>
          <div style={{ fontSize: 12, color: 'var(--ink-soft)', marginTop: 4 }}>
            路径：reports/{code}/&lt;日期&gt;_&lt;机构&gt;_&lt;标题&gt;.pdf
          </div>
        </div>
        <div className="row">
          <button className="btn btn-ghost" onClick={onBack} disabled={loading}>
            ← 返回
          </button>
          {results.length === 0 ? (
            <button className="btn" onClick={handleDownload} disabled={loading || reports.length === 0}>
              {loading ? '下载中...' : '开始下载'}
            </button>
          ) : (
            <>
              <button className="btn btn-ghost" onClick={handleDownload} disabled={loading}>
                {loading ? '重试中...' : '重新下载失败项'}
              </button>
              <button
                className="btn"
                onClick={() => onComplete(results)}
                disabled={!canProceed}
              >
                下一步：解析 PDF →
              </button>
            </>
          )}
        </div>
      </div>

      {error && <div className="error-text">{error}</div>}

      {results.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--ink-soft)', marginBottom: 8 }}>
            成功 {successCount} / 失败 {failedCount} / 总计 {results.length}
          </div>
          {results.map((r) => (
            <div key={r.info_code} className="status-row">
              <div className="status-text">
                <span className={`status-icon ${
                  r.status === 'ok' || r.status === 'exists' ? 'ok' :
                  r.status === 'failed' ? 'fail' : 'pending'
                }`}>
                  {r.status === 'ok' ? '✓' : r.status === 'exists' ? '✓' : '✗'}
                </span>
                {r.filename || r.info_code}
                {r.status === 'exists' && (
                  <span className="status-meta">已存在</span>
                )}
                {r.status === 'failed' && (
                  <span className="status-meta">失败：{r.error || 'unknown'}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {results.length === 0 && !loading && (
        <div className="empty-pad">点击「开始下载」批量上传 PDF 到 OSS</div>
      )}
    </div>
  );
}
