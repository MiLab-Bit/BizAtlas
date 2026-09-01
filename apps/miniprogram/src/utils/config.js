/** 商舆 BizAtlas 小程序 — 配置与工具 */

// API 基地址（小程序 request 合法域名需在管理后台配置）
const API_BASE = 'https://sy-realm.ltd/bizatlas/v1'

/** 风险等级 → 颜色/文案映射（与 Web 端一致） */
const GRADE_STYLE = {
  GREEN:   { label: '低风险',   color: '#16A34A', bg: '#DCFCE7' },
  YELLOW:  { label: '中低风险', color: '#CA8A04', bg: '#FEF9C3' },
  ORANGE:  { label: '中高风险', color: '#EA580C', bg: '#FFEDD5' },
  RED:     { label: '高风险',   color: '#DC2626', bg: '#FEE2E2' },
  BLACK:   { label: '极高风险', color: '#1E293B', bg: '#E2E8F0' },
  UNRATED: { label: '数据不足', color: '#64748B', bg: '#F1F5F9' }
}

function gradeStyle(grade) {
  return GRADE_STYLE[grade] || GRADE_STYLE.UNRATED
}

module.exports = { API_BASE, GRADE_STYLE, gradeStyle }
