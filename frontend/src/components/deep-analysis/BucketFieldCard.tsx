import type { FieldValue, Evidence } from '../../types/deepAnalysis';
import { fieldLabel } from '../../types/deepAnalysis';

interface Props {
  name: string;
  field: FieldValue;
}

const EVIDENCE_LABEL: Record<Evidence, string> = {
  strong:  '强证据',
  medium:  '中等证据',
  weak:    '弱证据',
  unknown: '未提及',
};

const EVIDENCE_CLASS: Record<Evidence, string> = {
  strong:  'ev-strong',
  medium:  'ev-medium',
  weak:    'ev-weak',
  unknown: 'ev-unknown',
};

function formatValue(v: FieldValue['value']): string {
  if (v === null || v === undefined) return '—';
  if (Array.isArray(v)) return v.length ? v.join('、') : '—';
  return String(v);
}

/**
 * 单字段 ledger 行:左侧 evidence 色带 + 标签 + 大字 value + 可选原文。
 *
 * Layout (single column, full width):
 *   ┌──────────────────────────────────────────────┐
 *   │ ▌ 国产化率                          [中等证据] │
 *   │ ▌ 约 15%                                      │
 *   │ ▌ ╱ "原文..." ← 研报                           │
 *   └──────────────────────────────────────────────┘
 */
export default function BucketFieldCard({ name, field }: Props) {
  const evClass = EVIDENCE_CLASS[field.evidence];
  return (
    <div className={`field-row ${evClass}`}>
      <div className="field-row-head">
        <span className="field-label">{fieldLabel(name)}</span>
        <span className={`field-evidence ${evClass}`}>{EVIDENCE_LABEL[field.evidence]}</span>
      </div>
      <div className="field-value">{formatValue(field.value)}</div>
      {field.quote && (
        <blockquote className="field-quote">
          <span className="field-quote-mark">╱</span>
          <span className="field-quote-text">{field.quote}</span>
        </blockquote>
      )}
    </div>
  );
}
