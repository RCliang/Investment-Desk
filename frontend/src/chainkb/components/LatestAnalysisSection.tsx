import { useLatestAnalysis } from '../hooks/useChainKb';
import {
  COMPANY_TYPE_LABELS,
  type AnalysisDoc,
  type BucketId,
} from '../../types/deepAnalysis';
import BucketTabs, { type BucketState } from '../../components/deep-analysis/BucketTabs';
// 拉入 .da-root 作用域样式 — 该 CSS 默认只在 DeepAnalysisPage 加载,
// 显式 import 保证 ChainKb 用户也能拿到 bucket-tabs/field-card 样式。
import '../../pages/deep-analysis.css';

interface Props {
  ticker: string;
}

/**
 * ChainKb tab 03「公司拆解」中的 AI 分析 section。
 *
 * 4 态渲染:
 *   loading → 占位
 *   error   → 失败提示
 *   empty   → 引导文案(404 / null)
 *   loaded  → 标题 + 元信息 + 复用 BucketTabs(全部 done 态)
 */
export default function LatestAnalysisSection({ ticker }: Props) {
  const la = useLatestAnalysis(ticker);

  if (la.loading) {
    return (
      <div className="la-section">
        <div className="la-pad">载入 AI 公司拆解…</div>
      </div>
    );
  }
  if (la.error) {
    return (
      <div className="la-section">
        <div className="la-pad">AI 分析载入失败:{la.error}</div>
      </div>
    );
  }
  if (!la.data) {
    return (
      <div className="la-section">
        <div className="la-header">
          <span className="la-title">AI 公司拆解</span>
        </div>
        <div className="la-empty">
          <div className="la-empty-title">该股票暂无 AI 公司拆解</div>
          <div className="la-empty-sub">
            前往「公司深度分析」页 → 选择企业类型 → 上传研报 → 一键生成
          </div>
        </div>
      </div>
    );
  }

  const doc: AnalysisDoc = la.data;
  const bucketOrder = doc.buckets.map((b) => b.bucket_id);
  const bucketResults = Object.fromEntries(doc.buckets.map((b) => [b.bucket_id, b]));
  // 历史视图: 全部 done,无 spinner / pending
  const bucketState = Object.fromEntries(
    bucketOrder.map((b) => [b, 'done' as BucketState]),
  ) as Record<BucketId, BucketState>;

  return (
    <div className="la-section">
      <div className="la-header">
        <span className="la-title">AI 公司拆解</span>
        <span className="la-pill">{COMPANY_TYPE_LABELS[doc.company_type]}</span>
        <span className="la-meta">
          {doc.analyzed_at?.slice(0, 10)} · {doc.model_name} · {doc.stats.ok}/{doc.stats.total} 桶
        </span>
      </div>
      <div className="da-root">
        <BucketTabs
          bucketOrder={bucketOrder}
          bucketState={bucketState}
          bucketResults={bucketResults}
          bucketErrors={{}}
        />
      </div>
    </div>
  );
}
