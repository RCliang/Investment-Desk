// 生产构建: 走微信云开发 + CloudBase AnyService + Lighthouse 回源
// 部署前替换 <your-cloud-env-id> 和 <your-anyservice-name> 为真实值:
//   - CLOUD_ENV: 微信开发者工具 → 云开发 → 设置 → 环境ID
//   - ANY_SERVICE_NAME: CloudBase 控制台 → AnyService → 接入名
module.exports = {
  env: {
    NODE_ENV: '"production"'
  },
  defineConstants: {
    BASE_URL_ENV: '""',  // prod 不走 BASE_URL, 由 wx.cloud.callContainer 取代
    CLOUD_ENV: '"<your-cloud-env-id>"',
    ANY_SERVICE_NAME: '"<your-anyservice-name>"'
  },
  mini: {},
  h5: {}
}
