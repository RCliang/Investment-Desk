// 开发构建 (npm run dev:weapp) 注入 localhost 后端。
// 微信开发者工具需在「详情 → 本地设置」勾选「不校验合法域名」。
module.exports = {
  env: {
    NODE_ENV: '"development"'
  },
  defineConstants: {
    BASE_URL_ENV: '"http://localhost:8000"'
  },
  mini: {},
  h5: {}
}
