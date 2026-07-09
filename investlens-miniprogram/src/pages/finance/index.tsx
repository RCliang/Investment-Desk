import { useState, useMemo } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import { getCurrentInstance } from '@tarojs/taro';
import { useCompany, useTimeseries } from '../../hooks/useChainKb';
import SketchKpi from '../../components/SketchKpi';
import MarketBadge from '../../components/MarketBadge';
import TimeseriesTable, { type Column } from '../../components/TimeseriesTable';
import LatestAnalysis from '../../components/LatestAnalysis';
import { fmtPrice, signedPct, fmtNum, pct } from '../../utils/format';
import './index.scss';

type SubTab = 'lockup' | 'holders' | 'margin' | 'reports';
const SUB_TABS: { key: SubTab; label: string }[] = [
  { key: 'lockup',  label: '解禁' },
  { key: 'holders', label: '股东户数' },
  { key: 'margin',  label: '融资融券' },
  { key: 'reports', label: '研报' },
];

const LOCKUP_COLS: Column[] = [
  { key: 'date',                label: '日期',   width: 1.2 },
  { key: 'type',                label: '类型',   width: 0.8 },
  { key: 'shares_wan',          label: '股数(万)', align: 'right' },
  { key: 'ratio_pct',           label: '占比%',   align: 'right', render: (r) => pct(r.ratio_pct as number | null) },
  { key: 'mcap_wan',            label: '市值(万)', align: 'right', render: (r) => fmtNum(r.mcap_wan as number | null) },
];
const HOLDER_COLS: Column[] = [
  { key: 'end_date',           label: '截止日',  width: 1.2 },
  { key: 'holder_num',         label: '户数',    align: 'right', render: (r) => fmtNum(r.holder_num as number | null) },
  { key: 'change_ratio_pct',   label: '环比%',   align: 'right', render: (r) => signedPct(r.change_ratio_pct as number | null) },
  { key: 'avg_free_shares',    label: '人均流通', align: 'right', render: (r) => fmtNum(r.avg_free_shares as number | null) },
];
const MARGIN_COLS: Column[] = [
  { key: 'date',     label: '日期',   width: 1.2 },
  { key: 'rzye_yi',  label: '融资(亿)', align: 'right', render: (r) => fmtNum(r.rzye_yi as number | null) },
  { key: 'rqye_yi',  label: '融券(亿)', align: 'right', render: (r) => fmtNum(r.rqye_yi as number | null) },
  { key: 'rzjme_yi', label: '净买(亿)', align: 'right', render: (r) => fmtNum(r.rzjme_yi as number | null) },
];
const REPORT_COLS: Column[] = [
  { key: 'publish_date', label: '日期',   width: 1 },
  { key: 'broker',       label: '券商',   width: 1 },
  { key: 'rating',       label: '评级',   width: 0.7 },
  { key: 'title',        label: '标题',   width: 2.5 },
];

export default function FinancePage() {
  const ticker = (getCurrentInstance().router?.params?.ticker) || '';
  const { data: profile, loading, error } = useCompany(ticker || null);
  const { data: ts } = useTimeseries(ticker || null, 30);
  const [subTab, setSubTab] = useState<SubTab>('lockup');

  const subRows = useMemo<Record<string, unknown>[]>(() => {
    if (!ts) return [];
    switch (subTab) {
      case 'lockup':  return (ts.lockup  ?? []) as unknown as Record<string, unknown>[];
      case 'holders': return (ts.holders ?? []) as unknown as Record<string, unknown>[];
      case 'margin':  return (ts.margin  ?? []) as unknown as Record<string, unknown>[];
      case 'reports': return (ts.reports ?? []) as unknown as Record<string, unknown>[];
    }
  }, [ts, subTab]);

  const subCols = subTab === 'lockup' ? LOCKUP_COLS : subTab === 'holders' ? HOLDER_COLS : subTab === 'margin' ? MARGIN_COLS : REPORT_COLS;

  if (!ticker) {
    return <View className='finance finance--center'><Text>缺少 ticker 参数</Text></View>;
  }
  if (loading) {
    return <View className='finance finance--center'><Text>加载中…</Text></View>;
  }
  if (error) {
    return <View className='finance finance--center'><Text className='finance__err'>加载失败: {error}</Text></View>;
  }
  if (!profile) return null;

  const { company, quote, finance: fin, sub_industries: subs } = profile;
  const changePct = quote?.change_pct;
  const priceCls = changePct == null ? '' : changePct > 0 ? 'finance__price--up' : changePct < 0 ? 'finance__price--down' : '';

  return (
    <ScrollView className='finance' scrollY>
      <View className='finance__head'>
        <View className='finance__head-row'>
          <MarketBadge market={company.market} />
          <Text className='finance__ticker'>{company.ticker}</Text>
          <Text className='finance__name'>{company.name_zh}</Text>
        </View>
        <View className='finance__head-row'>
          <Text className={`finance__price ${priceCls}`}>{fmtPrice(quote?.price)}</Text>
          <Text className={`finance__change ${priceCls}`}>{signedPct(changePct)}</Text>
        </View>
        <Text className='finance__sub'>
          {subs.map((s) => s.name_zh).join(' / ') || '—'}
        </Text>
      </View>

      <ScrollView className='finance__kpis' scrollX>
        <SketchKpi label='PE(TTM)'  value={fmtNum(quote?.pe_ttm)} />
        <SketchKpi label='PB'       value={fmtNum(quote?.pb)} />
        <SketchKpi label='市值'     value={fmtNum(quote?.mcap_yi)} unit='亿' />
        <SketchKpi label='EPS'      value={fmtNum(fin?.eps)} />
        <SketchKpi label='ROE'      value={pct(fin?.roe_pct)} />
        <SketchKpi label='毛利率'   value={pct(fin?.gross_margin_pct)} />
      </ScrollView>

      <View className='finance__subtabs'>
        {SUB_TABS.map((t) => (
          <View
            key={t.key}
            className={`finance__subtab ${subTab === t.key ? 'finance__subtab--active' : ''}`}
            onClick={() => setSubTab(t.key)}
          >
            <Text>{t.label}</Text>
          </View>
        ))}
      </View>

      <TimeseriesTable columns={subCols} rows={subRows} emptyText={`暂无${SUB_TABS.find((t) => t.key === subTab)?.label}数据`} />

      <LatestAnalysis ticker={ticker} />

      <View className='finance__footer'>
        <Text>数据来源: 后端 chainkb / deep-analysis</Text>
      </View>
    </ScrollView>
  );
}
