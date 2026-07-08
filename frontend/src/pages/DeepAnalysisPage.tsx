import { useCallback, useMemo, useState } from 'react';
import type {
  CompanyType,
  AnalysisDoc,
  ResearchReport,
  DownloadResult,
} from '../types/deepAnalysis';
import ReportSearchStep from '../components/deep-analysis/ReportSearchStep';
import ReportDownloadStep from '../components/deep-analysis/ReportDownloadStep';
import ReportParseStep from '../components/deep-analysis/ReportParseStep';
import AnalysisResultStep from '../components/deep-analysis/AnalysisResultStep';
import { LogoutIcon } from '../auth/icons';
import { useAdminAuth } from '../auth/AdminAuthContext';
import './deep-analysis.css';

interface Props {
  onExit: () => void;
}

type Step = 1 | 2 | 3 | 4;

const STEPS: { key: Step; label: string }[] = [
  { key: 1, label: '搜索研报' },
  { key: 2, label: '下载到 OSS' },
  { key: 3, label: '解析 PDF' },
  { key: 4, label: 'AI 分析' },
];

/**
 * 公司深度分析页面 — 4 步向导。
 * 每步独立组件，主容器持有跨步状态：
 * - code, selectedReports（Step1 → Step2）
 * - downloadResults（Step2 → Step3）
 * - ossKeys（Step3 → Step4）
 * - companyType, analysisDoc（Step4 v2 结构化）
 */
export default function DeepAnalysisPage({ onExit }: Props) {
  const { logout } = useAdminAuth();
  const [step, setStep] = useState<Step>(1);

  // ── 跨步状态 ───────────────────────────────────────────
  const [code, setCode] = useState<string>('');
  const [selectedReports, setSelectedReports] = useState<ResearchReport[]>([]);
  const [downloadResults, setDownloadResults] = useState<DownloadResult[]>([]);
  const [companyType, setCompanyType] = useState<CompanyType>('general');
  const [analysisDoc, setAnalysisDoc] = useState<AnalysisDoc | null>(null);

  // ── 衍生：从下载结果反推 oss_keys ──────────────────────
  const ossKeys = useMemo(() => {
    return downloadResults
      .filter((r) => r.status === 'ok' || r.status === 'exists')
      .map((r) => `reports/${code}/${r.filename}`)
      .filter((name) => !!name);
  }, [downloadResults, code]);

  // ── 步骤跳转 ───────────────────────────────────────────
  const goToStep = useCallback((target: Step) => {
    // 仅允许跳到已完成或当前步
    setStep(target);
    setAnalysisDoc(null); // 切步时清空分析结果，避免展示过期内容
  }, []);

  const handleSearchComplete = useCallback(
    (newCode: string, selected: ResearchReport[]) => {
      setCode(newCode);
      setSelectedReports(selected);
      setDownloadResults([]);
      setAnalysisDoc(null);
      setStep(2);
    },
    [],
  );

  const handleDownloadComplete = useCallback((results: DownloadResult[]) => {
    setDownloadResults(results);
    setStep(3);
  }, []);

  const handleParseComplete = useCallback(() => {
    setStep(4);
  }, []);

  const handleAnalysisDocChange = useCallback((doc: AnalysisDoc | null) => {
    setAnalysisDoc(doc);
  }, []);

  // ── 渲染 ───────────────────────────────────────────────
  return (
    <div className="da-root">
      <header className="da-header">
        <div className="row-between">
          <h1>公司深度分析</h1>
          <button
            className="btn btn-ghost"
            onClick={() => {
              logout();
              onExit();
            }}
            style={{ fontSize: 13 }}
          >
            <LogoutIcon /> 退出管理员
          </button>
        </div>
        <p className="da-subtitle">
          搜索研报 → 下载到 OSS → MinerU 解析 → AI 多维度分析
        </p>
      </header>

      <ol className="stepper">
        {STEPS.map((s, idx) => {
          const isCurrent = step === s.key;
          const isDone = step > s.key;
          return (
            <li
              key={s.key}
              className={`step ${isCurrent ? 'current' : ''} ${isDone ? 'done' : ''}`}
            >
              <button
                className="step-btn"
                onClick={() => goToStep(s.key)}
                disabled={s.key > step && s.key > 1 && !_canJumpTo(s.key, step)}
              >
                <span className="step-num">
                  {isDone ? '✓' : s.key}
                </span>
                <span className="step-label">{s.label}</span>
              </button>
              {idx < STEPS.length - 1 && <span className="step-arrow">→</span>}
            </li>
          );
        })}
      </ol>

      <section className="panel">
        {step === 1 && (
          <ReportSearchStep
            initialCode={code}
            initialSelected={selectedReports}
            companyType={companyType}
            onCompanyTypeChange={setCompanyType}
            onComplete={handleSearchComplete}
          />
        )}
        {step === 2 && (
          <ReportDownloadStep
            code={code}
            reports={selectedReports}
            results={downloadResults}
            onResultsChange={setDownloadResults}
            onComplete={handleDownloadComplete}
            onBack={() => setStep(1)}
          />
        )}
        {step === 3 && (
          <ReportParseStep
            code={code}
            ossKeys={ossKeys}
            onComplete={handleParseComplete}
            onBack={() => setStep(2)}
          />
        )}
        {step === 4 && (
          <AnalysisResultStep
            code={code}
            ossKeys={ossKeys}
            companyType={companyType}
            analysisDoc={analysisDoc}
            onAnalysisDocChange={handleAnalysisDocChange}
            onBack={() => setStep(3)}
          />
        )}
      </section>
    </div>
  );
}

/** 是否允许从当前步跳到目标步 */
function _canJumpTo(target: number, current: number): boolean {
  // 向前跳需要前置步骤完成；这里仅允许向前 1 步的保守策略，
  // 实际通过按钮 disabled 控制不会触发，回退始终允许。
  return target <= current + 1;
}
