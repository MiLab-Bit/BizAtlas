/**
 * upload_mp.js — 用 miniprogram-ci 上传小程序到微信平台
 * 使用 private.wx18d6236028c29ea9.key 进行鉴权
 */
import ci from 'miniprogram-ci'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const APP_ID = 'wx18d6236028c29ea9'
const PRIVATE_KEY_PATH = path.join(__dirname, 'private.wx18d6236028c29ea9.key')
const PROJECT_PATH = path.join(__dirname, 'src')

const project = new ci.Project({
  appid: APP_ID,
  type: 'miniProgram',
  projectPath: PROJECT_PATH,
  privateKeyPath: PRIVATE_KEY_PATH,
  ignores: ['node_modules/**/*'],
})

const VERSION = '1.0.0'
const DESC = '商舆 BizAtlas v1.0 — 企业经营与风险研判 Agent（GOAI 2026 复赛）：贷前审批/风险分析/验证报告/数据合规'

async function main() {
  try {
    const privateKey = readFileSync(PRIVATE_KEY_PATH, 'utf-8')
    console.log('[upload] 私钥读取成功，长度:', privateKey.length)
  } catch (e) {
    console.error('[upload] 私钥读取失败:', e.message)
    process.exit(1)
  }

  console.log('[upload] 开始上传…')
  const result = await ci.upload({
    project,
    version: VERSION,
    desc: DESC,
    setting: { es6: true, minify: true, autoPrefixWXSS: true },
    onProgressUpdate: (info) => {
      if (info._msg) console.log('  ', info._msg)
    },
  })
  console.log('[upload] 上传完成:', JSON.stringify(result, null, 2))
}

main().catch((err) => {
  console.error('[upload] FAILED:', err)
  process.exit(1)
})
