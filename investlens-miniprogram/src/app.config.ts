import { defineAppConfig } from '@tarojs/taro'

export default defineAppConfig({
  pages: [
    'pages/overview/index',
    'pages/search/index',
    'pages/profile/index',
    'pages/layers/index',
    'pages/finance/index',
  ],
  tabBar: {
    color: '#5a6a85',
    selectedColor: '#1a2b4a',
    backgroundColor: '#fbf9f4',
    borderStyle: 'white',
    list: [
      { pagePath: 'pages/overview/index', text: '总览' },
      { pagePath: 'pages/search/index',  text: '搜索' },
      { pagePath: 'pages/profile/index', text: '我的' },
    ],
  },
  window: {
    navigationBarTitleText: 'InvestLens',
    navigationBarBackgroundColor: '#fbf9f4',
    navigationBarTextStyle: 'black',
    backgroundColor: '#fbf9f4',
  },
  style: 'v2',
  lazyCodeLoading: 'requiredComponents',
  sitemapLocation: 'sitemap.json',
})
