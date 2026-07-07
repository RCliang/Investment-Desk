import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import Taro from '@tarojs/taro'
import './index.scss'

interface ChainData {
  layers: Array<{
    code: string
    name_zh: string
    sub_industries: Array<{
      id: string
      name_zh: string
      group_id: string
      company_count: number
    }>
  }>
}

export default class ChainPage extends Component {
  state = {
    chainData: null as ChainData | null,
    loading: true,
    error: ''
  }

  async componentDidMount() {
    try {
      const res = await Taro.request({
        url: 'http://localhost:8000/api/chainkb/tree',
        method: 'GET'
      })
      
      if (res.statusCode === 200) {
        this.setState({
          chainData: res.data,
          loading: false
        })
      } else {
        this.setState({
          loading: false,
          error: '数据加载失败'
        })
      }
    } catch (err) {
      console.error('Failed to fetch chain data:', err)
      this.setState({
        loading: false,
        error: '网络请求失败'
      })
    }
  }

  handleSubIndustryClick = (groupId: string) => {
    Taro.navigateTo({
      url: `/pages/layers/index?groupId=${groupId}`
    })
  }

  render() {
    const { chainData, loading, error } = this.state

    if (loading) {
      return (
        <View className='chain-page'>
          <Text className='loading-text'>加载中...</Text>
        </View>
      )
    }

    if (error) {
      return (
        <View className='chain-page'>
          <Text className='error-text'>{error}</Text>
        </View>
      )
    }

    if (!chainData) {
      return (
        <View className='chain-page'>
          <Text className='empty-text'>暂无数据</Text>
        </View>
      )
    }

    return (
      <ScrollView className='chain-page' scrollY>
        <View className='header'>
          <Text className='title'>产业链知识库</Text>
          <Text className='subtitle'>投资研究 · 五层产业链拆解视图</Text>
        </View>

        {chainData.layers.map((layer, idx) => (
          <View key={layer.code} className='layer-section'>
            <View className='layer-header'>
              <Text className='layer-code'>{layer.code}</Text>
              <Text className='layer-name'>{layer.name_zh}</Text>
            </View>

            <View className='sub-industry-grid'>
              {layer.sub_industries.map((sub) => (
                <View
                  key={sub.id}
                  className='sub-card'
                  onClick={() => this.handleSubIndustryClick(sub.group_id)}
                >
                  <Text className='sub-name'>{sub.name_zh}</Text>
                  <View className='sub-meta'>
                    <Text className='sub-group-id'>{sub.group_id}</Text>
                    <Text className='sub-count'>{sub.company_count}</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        ))}

        <View className='footer'>
          <Text className='footer-text'>
            InvestLens · 产业链知识库 v1
          </Text>
        </View>
      </ScrollView>
    )
  }
}
