// 生产构建时把 BASE_URL_ENV 注入为字符串字面量。
// 真机部署前请把 https://api.investlens.example.com 改成实际域名
// (该域名需在小程序后台 request 合法域名列表里配置)。
module.exports = {
  env: {
    NODE_ENV: '"production"'
  },
  defineConstants: {
    BASE_URL_ENV: '"https://api.investlens.example.com"'
  },
  mini: {},
  h5: {}
}
