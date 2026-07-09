import { useState } from 'react';
import { View, Text, Input, ScrollView } from '@tarojs/components';
import Taro, { getCurrentInstance } from '@tarojs/taro';
import { useSubIndustry } from '../../hooks/useChainKb';
import MarketBadge from '../../components/MarketBadge';
import { fmtPrice, signedPct, fmtNum } from '../../utils/format';
import './index.scss';

export default function LayersPage() {
  const groupId = (getCurrentInstance().router?.params?.groupId) || '';
  const { data, loading, error } = useSubIndustry(groupId || null);
  const [filter, setFilter] = useState('');

  if (!groupId) {
    return <View className='layers layers--center'><Text>缺少 groupId 参数</Text></View>;
  }
  if (loading) {
    return <View className='layers layers--center'><Text>加载中…</Text></View>;
  }
  if (error) {
    return <View className='layers layers--center'><Text className='layers__err'>加载失败: {error}</Text></View>;
  }
  if (!data) return null;

  const { sub_industry: sub, companies } = data;
  const q = filter.trim().toLowerCase();
  const filtered = q
    ? companies.filter(
        (c) => c.ticker.toLowerCase().includes(q) || c.name_zh.toLowerCase().includes(q),
      )
    : companies;

  const handleRowClick = (ticker: string) => {
    Taro.navigateTo({ url: `/pages/finance/index?ticker=${encodeURIComponent(ticker)}` });
  };

  return (
    <ScrollView className='layers' scrollY>
      <View className='layers__header'>
        <Text className='layers__sub-name'>{sub.name_zh}</Text>
        <Text className='layers__sub-meta'>
          {sub.layer_code ?? ''} {sub.layer_name_zh ?? ''} · {companies.length} 家公司
        </Text>
      </View>

      <Input
        className='layers__filter'
        type='text'
        placeholder='按代码 / 简称过滤'
        value={filter}
        onInput={(e) => setFilter(e.detail.value)}
      />

      <View className='layers__table'>
        <View className='layers__row layers__row--head'>
          <Text className='layers__cell layers__cell--ticker'>代码</Text>
          <Text className='layers__cell layers__cell--name'>公司</Text>
          <Text className='layers__cell layers__cell--num'>现价</Text>
          <Text className='layers__cell layers__cell--num'>涨跌</Text>
          <Text className='layers__cell layers__cell--num'>PE</Text>
          <Text className='layers__cell layers__cell--num'>市值(亿)</Text>
        </View>

        {filtered.length === 0 && (
          <View className='layers__empty'><Text>无匹配公司</Text></View>
        )}

        {filtered.map((c) => {
          const pctVal = c.quote?.change_pct;
          const pctCls = pctVal == null ? '' : pctVal > 0 ? 'layers__cell--up' : pctVal < 0 ? 'layers__cell--down' : '';
          return (
            <View
              key={c.ticker}
              className='layers__row layers__row--data'
              onClick={() => handleRowClick(c.ticker)}
            >
              <View className='layers__cell layers__cell--ticker'>
                <MarketBadge market={c.market} />
                <Text className='layers__ticker'>{c.ticker}</Text>
              </View>
              <Text className='layers__cell layers__cell--name'>{c.name_zh}</Text>
              <Text className='layers__cell layers__cell--num'>{fmtPrice(c.quote?.price)}</Text>
              <Text className={`layers__cell layers__cell--num ${pctCls}`}>{signedPct(pctVal)}</Text>
              <Text className='layers__cell layers__cell--num'>{fmtNum(c.quote?.pe_ttm)}</Text>
              <Text className='layers__cell layers__cell--num'>{fmtNum(c.quote?.mcap_yi)}</Text>
            </View>
          );
        })}
      </View>
    </ScrollView>
  );
}
