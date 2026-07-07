# InvestLens 产业链知识库 - 微信小程序

## 📱 项目简介

基于 Taro + React 开发的微信小程序，展示五层产业链知识库。

## 🚀 快速开始

### 1. 安装依赖

```bash
npm install
```

### 2. 启动开发模式

```bash
npm run dev:weapp
```

编译后的代码会输出到 `dist/` 目录。

### 3. 在微信开发者工具中打开

#### 方式一：CLI 自动打开（推荐）

```bash
# Windows
"C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat" open --project "E:\2026projects\Investment-Desk\investlens-miniprogram\dist"

# macOS
/Applications/wechatwebdevtools.app/Contents/MacOS/cli open --project "/path/to/dist"
```

#### 方式二：手动打开

1. 启动微信开发者工具
2. 选择"导入项目"
3. 项目目录指向 `dist/` 目录
4. AppID 填写你的小程序 AppID（测试可用测试号）

## 📁 项目结构

```
investlens-miniprogram/
├── config/              # Taro 配置文件
│   ├── index.js         # 主配置
│   ├── dev.js           # 开发环境配置
│   └── prod.js          # 生产环境配置
├── src/
│   ├── pages/           # 页面
│   │   └── chain/       # 产业链首页
│   │       ├── index.tsx
│   │       ├── index.scss
│   │       └── index.config.ts
│   ├── chainkb/         # 产业链核心模块（待迁移）
│   │   ├── components/  # UI 组件
│   │   └── hooks/       # 自定义 Hooks
│   ├── types/           # TypeScript 类型定义
│   │   └── chainkb.ts   # 产业链数据类型
│   ├── services/        # API 服务
│   │   └── api.ts       # HTTP 请求封装
│   ├── app.tsx          # 应用入口
│   ├── app.config.ts    # 全局配置
│   └── app.scss         # 全局样式
├── dist/                # 编译输出目录（微信小程序代码）
├── package.json
├── tsconfig.json
└── project.config.json  # 微信小程序配置
```

## 🔧 技术栈

- **框架**: Taro 4.2.0
- **UI**: React 18
- **语言**: TypeScript 5
- **样式**: Sass
- **构建**: Webpack 5

## 🎯 下一步开发计划

### 阶段一：基础功能（已完成 ✅）
- [x] Taro 项目初始化
- [x] 产业链首页骨架
- [x] 类型定义迁移
- [x] API 服务迁移

### 阶段二：核心页面迁移（进行中 🚧）
- [ ] 从 uniapp 分支迁移 OverviewScreen
- [ ] 从 uniapp 分支迁移 LayerScreen
- [ ] 从 uniapp 分支迁移 FinanceScreen
- [ ] 适配 Taro 组件系统（View, Text, ScrollView 等）

### 阶段三：图表适配（待开发 📊）
- [ ] SVG 图表替换为 ECharts
- [ ] 安装 echarts-for-weixin
- [ ] 重写 TopologySvg 和 DistributionBars

### 阶段四：样式优化（待开发 🎨）
- [ ] 下载手写字体文件（Caveat, Patrick Hand）
- [ ] 适配小程序字体加载
- [ ] 优化手绘风格 UI

### 阶段五：真机调试（待测试 📱）
- [ ] 配置后端 API 地址
- [ ] 真机预览测试
- [ ] 性能优化

## ⚠️ 注意事项

### 1. API 请求适配

Web 版使用 `fetch`，小程序需改为 `Taro.request`：

```typescript
// Web 版
const response = await fetch('/api/chain/tree')

// 小程序版
import Taro from '@tarojs/taro'
const response = await Taro.request({
  url: 'https://your-api.com/api/chain/tree',
  method: 'GET'
})
```

### 2. SVG 图表替换

小程序不支持直接渲染 SVG，需使用以下方案之一：

- **方案一**：使用 ECharts for Weixin
  ```bash
  npm install echarts-for-weixin
  ```

- **方案二**：Canvas API 手动绘制

- **方案三**：预生成静态图片

### 3. 路由跳转

```typescript
// Web 版
<Link to="/layers?groupId=xxx">查看层级</Link>

// 小程序版
import Taro from '@tarojs/taro'
Taro.navigateTo({
  url: '/pages/layers/index?groupId=xxx'
})
```

### 4. 字体处理

小程序不支持 Google Fonts CDN，需下载字体文件到本地：

```css
@font-face {
  font-family: 'Caveat';
  src: url('/fonts/Caveat-Regular.ttf') format('truetype');
}
```

## 🔗 相关资源

- [Taro 官方文档](https://taro-docs.jd.com/)
- [微信小程序开发文档](https://developers.weixin.qq.com/miniprogram/dev/framework/)
- [ECharts for Weixin](https://github.com/ecomfe/echarts-for-weixin)

## 📝 开发日志

### 2026-07-04
- ✅ 创建 Taro 项目基础结构
- ✅ 安装依赖包
- ✅ 复制类型定义和 API 服务
- ✅ 创建产业链首页骨架
- ⚠️ 编译遇到问题（ENABLE_INNER_HTML 未定义），需要进一步调试

## 🐛 已知问题

1. **编译错误**: `ENABLE_INNER_HTML is not defined`
   - 原因：Taro 4.x 版本的兼容性问题
   - 解决：可能需要降级到 Taro 3.x 或等待官方修复

2. **依赖预编译失败**: `options.roots.map is not a function`
   - 已跳过预编译步骤，不影响最终编译结果

## 💡 建议

如果遇到编译问题，可以考虑：

1. **降级到 Taro 3.x**（更稳定）
   ```bash
   npm install @tarojs/cli@3.6.0 @tarojs/components@3.6.0 ...
   ```

2. **使用 H5 模式开发**（便于调试）
   ```bash
   npm run dev:h5
   ```

3. **先完成业务逻辑迁移**，再处理编译问题

---

**作者**: AI Assistant  
**日期**: 2026-07-04  
**版本**: v1.0.0
