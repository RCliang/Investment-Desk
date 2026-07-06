import type { CompanyType } from '../../types/deepAnalysis';
import { COMPANY_TYPE_LABELS } from '../../types/deepAnalysis';

interface Props {
  value: CompanyType;
  onChange: (v: CompanyType) => void;
  disabled?: boolean;
}

const ORDER: CompanyType[] = ['equipment', 'material', 'packaging', 'ip', 'general'];

/**
 * 企业类型 5 档单选(Step 1 顶部)。
 */
export default function CompanyTypeSelector({ value, onChange, disabled }: Props) {
  return (
    <div className="company-type-row">
      <span className="company-type-label">企业类型</span>
      <div className="company-type-options">
        {ORDER.map((ct) => (
          <button
            key={ct}
            type="button"
            className={`chip ${value === ct ? 'active' : ''}`}
            onClick={() => onChange(ct)}
            disabled={disabled}
          >
            {COMPANY_TYPE_LABELS[ct]}
          </button>
        ))}
      </div>
    </div>
  );
}
