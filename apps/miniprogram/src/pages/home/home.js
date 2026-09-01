// pages/home/home.js
Page({
  data: {
    features: [
      { key: 'company', title: '企业查询', desc: '查看企业列表与详情，快速研判主体', icon: '🔍', path: '/pages/company/list' },
      { key: 'risk',    title: '风险分析', desc: '调用规则引擎，输出五维风险评分', icon: '⚡', path: '/pages/risk/analyze' },
      { key: 'credit',  title: '贷前审批', desc: '一键生成审批决策、建议额度与条件', icon: '✅', path: '/pages/credit/decision' },
      { key: 'validation', title: '评分验证', desc: '查看评分回溯 AUC/KS 与样本构成', icon: '📊', path: '/pages/validation/report' }
    ]
  },

  onNavigate(e) {
    const path = e.currentTarget.dataset.path
    wx.navigateTo({ url: path })
  },

  onAbout() {
    wx.navigateTo({ url: '/pages/about/about' })
  }
})
