import type { FieldValue, Evidence } from '../../types/deepAnalysis';

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
 * 单字段卡片:字段名 + value + evidence 色块 + quote 原文。
 */
export default function BucketFieldCard({ name, field }: Props) {
  const evClass = EVIDENCE_CLASS[field.evidence];
  return (
    <div className={`da-field-card ${evClass}`}>
      <div className="da-field-name">{name}</div>
      <div className="da-field-value">{formatValue(field.value)}</div>
      <div className={`da-field-evidence ${evClass}`}>
        {EVIDENCE_LABEL[field.evidence]}
      </div>
      {field.quote && (
        <blockquote className="da-field-quote">"{field.quote}"</blockquote>
      )}
    </div>
  );
}
