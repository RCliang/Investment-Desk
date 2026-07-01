import { useState } from 'react';
import type { ResearchReport } from '../../types/deepAnalysis';
import { searchReportsByCode } from '../../services/api';

interface Props {
  initialCode: string;
  initialSelected: ResearchReport[];
  onComplete: (code: string, selected: ResearchReport[]) => void;
}

/**
 * Step 1: 按股票代码搜索研报，用户勾选后进入下一步。
 * 点击「下一步」时不立即下载，下载在 Step2 触发。
 */
export default function ReportSearchStep({ initialCode, initialSelected, onComplete }: Props) {
  const [code, setCode] = useState(initialCode || '');
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set(initialSelected.map((r) => r.info_code)));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSearch = async () => {
    if (!/^\d{6}$/.test(code)) {
      setError('股票代码必须为 6 位数字');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const resp = await searchReportsByCode(code);
      setReports(resp.reports || []);
      setSelected(new Set());
    } catch (e) {
      setError(`搜索失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (infoCode: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(infoCode)) next.delete(infoCode);
      else next.add(infoCode);
      return next;
    });
  };

  const selectAll = () => {
    setSelected(new Set(reports.map((r) => r.info_code)));
  };

  const selectNone = () => {
    setSelected(new Set());
  };

  const handleNext = () => {
    const chosen = reports.filter((r) => selected.has(r.info_code));
    if (chosen.length === 0) {
      setError('请至少选择 1 篇研报');
      return;
    }
    onComplete(code, chosen);
  };

  return (
    <div>
      <div className="da-row">
        <input
          className="da-search-input"
          placeholder="股票代码，如 301095"
          value={code}
          onChange={(e) => setCode(e.target.value.trim())}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          style={{ width: 200 }}
        />
        <button className="da-btn" onClick={handleSearch} disabled={loading || !code}>
          {loading ? '搜索中...' : '搜索'}
        </button>
        {reports.length > 0 && (
          <>
            <button className="da-btn-ghost da-btn" onClick={selectAll}>全选</button>
            <button className="da-btn-ghost da-btn" onClick={selectNone}>清空</button>
          </>
        )}
        <div style={{ flex: 1 }} />
        <button
          className="da-btn"
          onClick={handleNext}
          disabled={selected.size === 0}
        >
          下一步：下载到 OSS →
        </button>
      </div>

      {error && <div className="da-error">{error}</div>}

      {reports.length > 0 && (
        <div style={{ marginTop: 12, color: 'var(--da-text-soft)', fontSize: 12 }}>
          共 {reports.length} 篇，已选 {selected.size} 篇
        </div>
      )}

      {reports.length > 0 && (
        <table className="da-table">
          <thead>
            <tr>
              <th style={{ width: 36 }}></th>
              <th>标题</th>
              <th>机构</th>
              <th>评级</th>
              <th>日期</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.info_code}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(r.info_code)}
                    onChange={() => toggleSelect(r.info_code)}
                  />
                </td>
                <td className="da-title-cell">{r.title}</td>
                <td className="da-meta-cell">{r.org_name}</td>
                <td className="da-meta-cell">{r.rating || '-'}</td>
                <td className="da-meta-cell">{r.publish_date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!loading && reports.length === 0 && !error && (
        <div className="da-empty">输入股票代码后点击「搜索」</div>
      )}
    </div>
  );
}
