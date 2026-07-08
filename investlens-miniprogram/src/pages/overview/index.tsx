import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { useTree, useFreshness } from '../../hooks/useChainKb';
import SketchPanel from '../../components/SketchPanel';
import SketchKpi from '../../components/SketchKpi';
import DataFreshness from '../../components/DataFreshness';
import SubIndustryCard from '../../components/SubIndustryCard';
import { fmtCount } from '../../utils/format';
import './index.scss';

export default function OverviewPage() {
  const { data: tree, loading, error } = useTree();
  const freshness = useFreshness();

  const handleSubClick = (groupId: string) => {
    Taro.navigateTo({ url: `/pages/layers/index?groupId=${encodeURIComponent(groupId)}` });
  };

  if (loading) {
    return (
      <View className='overview overview--center'>
        <Text className='overview__status'>加载中…</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View className='overview overview--center'>
        <Text className='overview__status overview__status--err'>加载失败: {error}</Text>
      </View>
    );
  }

  if (!tree) return null;

  const totalCompanies = tree.layers.reduce(
    (sum, l) => sum + l.sub_industries.reduce((s, sub) => s + sub.company_count, 0),
    0,
  );
  const totalSubs = tree.layers.reduce((s, l) => s + l.sub_industries.length, 0);

  return (
    <ScrollView className='overview' scrollY>
      <View className='overview__brand'>
        <Text className='overview__brand-name'>InvestLens</Text>
        <Text className='overview__brand-sub'>投资研究 · 五层产业链拆解</Text>
        <DataFreshness market={freshness?.quotes} finance={freshness?.finance} />
      </View>

      <ScrollView className='overview__kpis' scrollX>
        <SketchKpi label='公司总数' value={fmtCount(totalCompanies)} unit='家' />
        <SketchKpi label='子行业' value={fmtCount(totalSubs)} unit='个' />
        <SketchKpi label='覆盖层' value={fmtCount(tree.layers.length)} unit='层' />
      </ScrollView>

      {tree.layers.map((layer) => {
        const layerCompanyCount = layer.sub_industries.reduce((s, sub) => s + sub.company_count, 0);
        return (
          <SketchPanel key={layer.code} code={layer.code} title={layer.name_zh}>
            <View className='overview__layer-meta'>
              <Text className='overview__layer-count'>{fmtCount(layerCompanyCount)} 家公司 · {layer.sub_industries.length} 个子行业</Text>
            </View>
            <View className='overview__sub-grid'>
              {layer.sub_industries.map((sub) => (
                <SubIndustryCard key={sub.id} sub={sub} onClick={handleSubClick} />
              ))}
            </View>
          </SketchPanel>
        );
      })}

      <View className='overview__footer'>
        <Text>InvestLens · 产业链知识库 v1</Text>
      </View>
    </ScrollView>
  );
}
