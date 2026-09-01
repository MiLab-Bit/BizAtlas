// pages/credit/decision.js — 贷前审批决策（核心页面，复赛聚焦场景）
const app = getApp()
const { gradeStyle } = require('../../utils/config.js')

Page({
  data: {
    form: { companyId: 'healthy', appliedAmount: 500, tenorMonths: 12 },
    fixtures: [
      { id: 'healthy',   label: '健康企业（演示）' },
      { id: 'risky',     label: '高风险企业（演示）' },
      { id: 'defaulted', label: '失信企业（演示）' }
    ],
    result: null,
    loading: false
  },

  onCompanyId(e) { this.setData({ 'form.companyId': e.detail.value }) },

  onAmount(e) { this.setData({ 'form.appliedAmount': Number(e.detail.value) || 0 }) },

  onTenor(e) { this.setData({ 'form.tenorMonths': Number(e.detail.value) || 12 }) },

  onSubmit() {
    const { companyId, appliedAmount, tenorMonths } = this.data.form
    if (!companyId) { wx.showToast({ title: '请输入企业ID', icon: 'none' }); return }
    this.setData({ loading: true, result: null })
    wx.showLoading({ title: '研判中…' })
    app.request({
      url: '/credit/decision',
      method: 'POST',
      data: {
        company_id: companyId,
        applied_amount: appliedAmount,
        tenor_months: tenorMonths,
        skip_polish: true,
        include_stress: false
      }
    }).then((res) => {
      const envelope = (res && res.data) ? res.data : res
      const d = (envelope && envelope.decision) ? envelope.decision : envelope
      const decisionStyle = this._decisionStyle(d.decision)
      this.setData({
        result: {
          ...d,
          decisionLabel: decisionStyle.label,
          decisionColor: decisionStyle.color,
          decisionBg: decisionStyle.bg,
          gradeStyle: gradeStyle(d.risk_grade || d.grade)
        }
      })
    }).catch((err) => {
      console.error('[credit]', err)
      wx.showToast({ title: '请求失败', icon: 'none' })
    }).then(() => {
      this.setData({ loading: false })
      wx.hideLoading()
    })
  },

  _decisionStyle(decision) {
    const map = {
      APPROVE:               { label: '通过',           color: '#16A34A', bg: '#DCFCE7' },
      APPROVE_WITH_CONDITIONS:{ label: '有条件通过',    color: '#2563EB', bg: '#DBEAFE' },
      MANUAL_REVIEW:         { label: '人工复核',       color: '#EA580C', bg: '#FFEDD5' },
      DECLINE:               { label: '拒绝',           color: '#DC2626', bg: '#FEE2E2' },
      INSUFFICIENT_DATA:     { label: '数据不足',       color: '#64748B', bg: '#F1F5F9' }
    }
    return map[decision] || { label: decision || '未知', color: '#64748B', bg: '#F1F5F9' }
  }
})
