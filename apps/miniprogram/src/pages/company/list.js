// pages/company/list.js — 企业列表（调用 /v1/companies）
const app = getApp()

Page({
  data: { companies: [], loading: true, keyword: '' },

  onLoad() { this.loadCompanies() },

  loadCompanies() {
    this.setData({ loading: true })
    app.request({ url: '/companies' })
      .then((res) => {
        const companies = (res.data || res || []).map(c => ({
          ...c,
          gradeStyle: require('../../utils/config.js').gradeStyle(c.grade || c.risk_grade || 'UNRATED')
        }))
        this.setData({ companies, loading: false })
      })
      .catch((err) => {
        console.error('[companies]', err)
        this.setData({ loading: false })
        wx.showToast({ title: '加载失败', icon: 'none' })
      })
  },

  onSearch(e) { this.setData({ keyword: e.detail.value }) },

  onTapCompany(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/company/detail?id=${id}` })
  },

  onPullDownRefresh() {
    this.loadCompanies()
    wx.stopPullDownRefresh()
  }
})
