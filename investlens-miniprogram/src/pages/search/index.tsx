import { useState } from 'react';
import { View, Text, Input, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { useSearch } from '../../hooks/useChainKb';
import MarketBadge from '../../components/MarketBadge';
import './index.scss';

export default function SearchPage() {
  const [q, setQ] = useState('');
  const { data, loading, error } = useSearch(q, 20, 280);

  const handleCompanyClick = (ticker: string) => {
    Taro.navigateTo({ url: `/pages/finance/index?ticker=${encodeURIComponent(ticker)}` });
  };
  const handleSubClick = (groupId: string) => {
    Taro.navigateTo({ url: `/pages/layers/index?groupId=${encodeURIComponent(groupId)}` });
  };

  const subResults = (data?.results ?? []).filter(
    (r) => r.sub_industries && r.sub_industries.length > 0,
  );
  const subSet = new Map<string, string>();
  subResults.forEach((r) => {
    r.sub_industries.forEach((s) => subSet.set(s.group_id, s.name_zh));
  });
  const subList = Array.from(subSet.entries()).slice(0, 10);

  return (
    <View className='search'>
      <Input
        className='search__input'
        type='text'
        placeholder='搜索公司代码 / 名称 / 子行业'
        confirmType='search'
        value={q}
        onInput={(e) => setQ(e.detail.value)}
        focus
      />

      <ScrollView className='search__body' scrollY>
        {!q && (
          <View className='search__hint'>
            <Text>输入关键字开始搜索</Text>
          </View>
        )}

        {loading && <View className='search__status'><Text>搜索中…</Text></View>}
        {error && <View className='search__status search__status--err'><Text>搜索失败: {error}</Text></View>}

        {data && !loading && (
          <>
            {subList.length > 0 && (
              <View className='search__group'>
                <Text className='search__group-title'>子行业 ({subList.length})</Text>
                {subList.map(([gid, name]) => (
                  <View key={gid} className='search__sub-row' onClick={() => handleSubClick(gid)}>
                    <Text className='search__sub-name'>{name}</Text>
                    <Text className='search__sub-gid'>{gid}</Text>
                  </View>
                ))}
              </View>
            )}

            <View className='search__group'>
              <Text className='search__group-title'>公司 ({data.results.length})</Text>
              {data.results.length === 0 && (
                <View className='search__empty'><Text>无匹配公司</Text></View>
              )}
              {data.results.map((r) => (
                <View
                  key={r.ticker}
                  className='search__company-row'
                  onClick={() => handleCompanyClick(r.ticker)}
                >
                  <MarketBadge market={r.market} />
                  <Text className='search__company-ticker'>{r.ticker}</Text>
                  <Text className='search__company-name'>{r.name_zh}</Text>
                </View>
              ))}
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}
