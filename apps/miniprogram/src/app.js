// app.js — 商舆 BizAtlas 小程序入口
const config = require('./utils/config.js')

App({
  globalData: {
    apiBase: config.API_BASE,
    token: '',
    companyList: []
  },

  onLaunch() {
    // 从本地缓存恢复 token
    const token = wx.getStorageSync('bizatlas_token')
    if (token) this.globalData.token = token
    console.log('[BizAtlas] 启动，API:', config.API_BASE)
  },

  /** 统一带 token 的请求封装 */
  request(opts) {
    const { url, method = 'GET', data, header = {} } = opts
    return new Promise((resolve, reject) => {
      wx.request({
        url: this.globalData.apiBase + url,
        method,
        data,
        header: Object.assign({ 'Content-Type': 'application/json' }, header, this._authHeader()),
        success: (res) => {
          if (res.statusCode === 401) {
            wx.showToast({ title: '请先登录', icon: 'none' })
            reject(new Error('未授权'))
            return
          }
          if (res.statusCode >= 400) {
            reject(new Error(`HTTP ${res.statusCode}`))
            return
          }
          resolve(res.data)
        },
        fail: (err) => reject(err)
      })
    })
  },

  _authHeader() {
    return this.globalData.token ? { Authorization: `Bearer ${this.globalData.token}` } : {}
  },

  setToken(token) {
    this.globalData.token = token
    if (token) {
      wx.setStorageSync('bizatlas_token', token)
    } else {
      wx.removeStorageSync('bizatlas_token')
    }
  }
})
