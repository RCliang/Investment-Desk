import { defineAppConfig } from '@tarojs/taro'

export default defineAppConfig({
  pages: [
    'pages/chain/index'
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#fff',
    navigationBarTitleText: '产业链知识库',
    navigationBarTextStyle: 'black'
  },
  style: 'v2',
  lazyCodeLoading: 'requiredComponents',
  sitemapLocation: 'sitemap.json'
})
