// pages/validation/report.js — 风险评分回溯验证报告（复赛方向二核心）
const app = getApp()

Page({
  data: { report: null, loading: true },

  onLoad() {
    this.setData({ loading: true })
    app.request({ url: '/validation/backtest' })
      .then((res) => {
        const r = (res.data || res)
        this.setData({ report: r, loading: false })
      })
      .catch((err) => {
        console.error('[validation]', err)
        this.setData({ loading: false })
      })
  }
})
