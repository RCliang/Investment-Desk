// 与 frontend/src/types/deepAnalysis.ts 对齐 (v1 只需要展示最新分析, 不需要 SSE/parse 相关)

export type CompanyType = 'equipment' | 'material' | 'packaging' | 'ip' | 'general';

export type BucketId =
  | 'industry_chain'
  | 'equipment'
  | 'material'
  | 'financial'
  | 'risk'
  | 'catalyst';

export type Evidence = 'strong' | 'medium' | 'weak' | 'unknown';

export interface FieldValue {
  value: string | number | string[] | null;
  evidence: Evidence;
  quote: string | null;
}

export interface BucketResult {
  bucket_id: BucketId;
  fields: Record<string, FieldValue>;
}

export interface AnalysisStats {
  ok: number;
  error: number;
  total: number;
}

export interface AnalysisDoc {
  version: 'v2';
  company_type: CompanyType;
  stock_code: string;
  buckets: BucketResult[];
  analyzed_at: string;
  model_name: string;
  stats: AnalysisStats;
}

export const COMPANY_TYPE_LABELS: Record<CompanyType, string> = {
  equipment: '设备',
  material:  '材料',
  packaging: '封测',
  ip:        'IP',
  general:   '综合',
};

export const BUCKET_DISPLAY_NAMES: Record<BucketId, string> = {
  industry_chain: '产业链与竞争格局',
  equipment:      '设备层指标',
  material:       '材料层指标',
  financial:      '分业务财务',
  risk:           '风险与反证',
  catalyst:       '催化剂与监控',
};

export const FIELD_LABELS: Record<string, string> = {
  domestic_share:        '国产化率',
  competitors:           '主要竞争对手',
  certification_stage:   '客户认证阶段',
  industry_position:     '行业地位',
  value_chain_link:      '产业链环节',
  keyEquipmentModels:    '核心设备型号',
  targetProcessNode:     '目标制程节点',
  throughput:            '设备产能/吞吐',
  yield_rate:            '良率',
  customer_validation:   '客户验证进度',
  key_materials:         '核心材料',
  purity_grade:          '纯度等级',
  domestic_suppliers:    '国产供应商',
  import_dependency:     '进口依赖度',
  certification_progress:'认证进度',
  revenue_forecast:      '营收预测',
  gross_margin:          '毛利率',
  net_profit_forecast:   '净利润预测',
  pe_band:               'PE 估值区间',
  growth_drivers:        '增长驱动',
  tech_risk:             '技术风险',
  market_risk:           '市场风险',
  policy_risk:           '政策/贸易战风险',
  supply_chain_risk:     '供应链风险',
  counter_evidence:      '反证(看空理由)',
  short_term_catalyst:   '短期催化剂',
  long_term_catalyst:    '长期催化剂',
  monitoring_metrics:    '监控指标',
  inflection_point:      '拐点信号',
};

export function fieldLabel(name: string): string {
  return FIELD_LABELS[name] ?? name;
}
