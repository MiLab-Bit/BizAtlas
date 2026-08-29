// pages/compliance/statement.js — 数据合规声明
const app = getApp()

Page({
  data: { statement: null, loading: true },

  onLoad() {
    this.setData({ loading: true })
    app.request({ url: '/compliance/statement' })
      .then((res) => {
        this.setData({ statement: (res.data || res), loading: false })
      })
      .catch((err) => {
        console.error('[compliance]', err)
        this.setData({ loading: false })
      })
  }
})
