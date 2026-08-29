// pages/risk/analyze.js — 风险分析（调用 /v1/analyze）
const app = getApp()
const { gradeStyle } = require('../../utils/config.js')

Page({
  data: {
    form: { companyId: '', query: '' },
    fixtures: [{id:'healthy',label:'健康企业'},{id:'risky',label:'高风险企业'},{id:'defaulted',label:'失信企业'}],
    result: null, loading: false
  },
  onCompany(e){ this.setData({'form.companyId': e.detail.value}) },
  onQuery(e){ this.setData({'form.query': e.detail.value}) },
  onSubmit(){
    const id = this.data.form.companyId
    if(!id){ wx.showToast({title:'请输入企业ID',icon:'none'}); return }
    this.setData({loading:true, result:null})
    wx.showLoading({title:'风险研判中…'})
    app.request({url:'/analyze', method:'POST', data:{company_id:id, query:this.data.form.query||'全面风险研判'}})
      .then(res=>{
        const d = (res.data||res)
        this.setData({result:{...d, gradeStyle:gradeStyle(d.grade||d.risk_grade||'UNRATED')}})
      }).catch(err=>{ console.error('[analyze]',err); wx.showToast({title:'请求失败',icon:'none'}) })
      .then(()=>{ this.setData({loading:false}); wx.hideLoading() })
  }
})
