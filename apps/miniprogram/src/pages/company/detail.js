// pages/company/detail.js
const app = getApp()
const { gradeStyle } = require('../../utils/config.js')
Page({
  data: { id:'', company:null, loading:true },
  onLoad(opts){ this.setData({id:opts.id||'healthy'}); this.load() },
  load(){
    this.setData({loading:true})
    app.request({url:`/companies/${this.data.id}`})
      .then(res=>{ const d=(res.data||res); this.setData({company:{...d, gradeStyle:gradeStyle(d.grade||d.risk_grade||'UNRATED')}, loading:false}) })
      .catch(err=>{ console.error('[detail]',err); this.setData({loading:false}) })
  }
})
