import { View, Text, ScrollView } from '@tarojs/components';
import { useFreshness } from '../../hooks/useChainKb';
import SketchPanel from '../../components/SketchPanel';
import DataFreshness from '../../components/DataFreshness';
import './index.scss';

export default function ProfilePage() {
  const freshness = useFreshness();

  return (
    <ScrollView className='profile' scrollY>
      <View className='profile__brand'>
        <Text className='profile__brand-name'>InvestLens</Text>
        <Text className='profile__brand-sub'>投资研究工作台 · 小程序版 v1</Text>
      </View>

      <SketchPanel title='数据更新'>
        <DataFreshness
          variant='full'
          market={freshness?.quotes}
          finance={freshness?.finance}
        />
      </SketchPanel>

      <SketchPanel title='关于'>
        <Text className='profile__about'>
          InvestLens 是个人 A 股投资研究工作台, 提供五层产业链拆解、公司基本面与财务时序数据、AI 公司分析。小程序版 v1 聚焦产业链知识库浏览, 深度分析与数据刷新请前往 Web 端。
        </Text>
      </SketchPanel>

      <SketchPanel title='更多'>
        <View className='profile__row profile__row--disabled'>
          <Text>设置</Text><Text className='profile__row-meta'>敬请期待</Text>
        </View>
        <View className='profile__row profile__row--disabled'>
          <Text>反馈</Text><Text className='profile__row-meta'>敬请期待</Text>
        </View>
      </SketchPanel>

      <View className='profile__footer'>
        <Text>© 2026 InvestLens</Text>
      </View>
    </ScrollView>
  );
}
