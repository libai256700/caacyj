import fs from 'node:fs/promises'
import path from 'node:path'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import config from '../config.mjs'
import { launchCleanAppTask } from './lib/app-task.mjs'

const execFileAsync = promisify(execFile)
const scenario = config.scenarios.practiceEntry
const startedAt = new Date()
const runId = startedAt.toISOString().replace(/[:.]/g, '-')
const reportDir = path.join(scenario.reportDir, runId)
const result = { scenarioId: scenario.id, status: 'running', startedAt: startedAt.toISOString(), device: null, apk: null, steps: [], evidence: [] }

class Driver {
  constructor(url) { this.url = url.replace(/\/$/, ''); this.session = '' }
  async request(endpoint, method = 'GET', body) {
    const response = await fetch(`${this.url}${endpoint}`, { method, headers: body === undefined ? undefined : { 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(45_000) })
    const payload = await response.json().catch(() => ({}))
    const error = payload?.value?.error || payload?.value?.message
    if (!response.ok || error) throw new Error(`${method} ${endpoint} failed: ${error || response.statusText}`)
    return payload.value ?? payload
  }
  async create(capabilities) { const payload = await this.request('/session', 'POST', { capabilities }); this.session = payload.sessionId || payload.value?.sessionId; if (!this.session) throw new Error('Appium session 创建失败') }
  async close() { if (this.session) await this.request(`/session/${this.session}`, 'DELETE').catch(() => {}); this.session = '' }
  command(endpoint, method = 'GET', body) { return this.request(`/session/${this.session}${endpoint}`, method, body) }
  source() { return this.command('/source') }
  screenshot() { return this.command('/screenshot') }
  find(using, value) { return this.command('/element', 'POST', { using, value }) }
  click(id) { return this.command(`/element/${id}/click`, 'POST', {}) }
}

const run = (command, args, allowFailure = false) => execFileAsync(command, args, { windowsHide: true, maxBuffer: 8 * 1024 * 1024 }).catch((error) => {
  if (allowFailure) return { stdout: error.stdout?.toString() || '', stderr: error.stderr?.toString() || error.message }
  throw error
})
const adb = (args, allowFailure = false) => run(config.device.adbPath, ['-s', result.device.serial, ...args], allowFailure)
const redact = (value) => String(value).replace(/(access[_-]?token|openid|auth[_-]?token|secret|password)["'\s:=]+[^,\s}\]]+/gi, '$1=<redacted>').replace(/\b\d{11}\b/g, '<phone-redacted>')

async function findDevice() {
  const { stdout } = await run(config.device.adbPath, ['devices'])
  const devices = stdout.split(/\r?\n/).slice(1).map((line) => line.trim().split(/\s+/)).filter(([, state]) => state === 'device').map(([serial]) => serial)
  const serial = config.device.serial || (devices.length === 1 ? devices[0] : '')
  if (!serial || !devices.includes(serial)) throw new Error('没有找到配置的 Android 真机')
  return serial
}
async function findApk() {
  const entries = await fs.readdir(config.app.apkDir, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    if (!entry.isFile() || !config.app.apkPattern.test(entry.name)) continue
    const fullPath = path.join(config.app.apkDir, entry.name)
    files.push({ path: fullPath, mtime: (await fs.stat(fullPath)).mtimeMs })
  }
  files.sort((left, right) => right.mtime - left.mtime)
  if (!files.length) throw new Error('没有找到发行 APK')
  return files[0].path
}
async function waitFor(label, predicate, timeout = scenario.timeoutMs) {
  const deadline = Date.now() + timeout
  let lastError
  while (Date.now() < deadline) {
    try { const value = await predicate(); if (value) return value } catch (error) { lastError = error }
    await new Promise((resolve) => setTimeout(resolve, 350))
  }
  throw new Error(`${label} 超时${lastError ? `：${lastError.message}` : ''}`)
}
async function appiumAvailable() { try { return (await fetch(`${config.appium.serverUrl}/status`, { signal: AbortSignal.timeout(2_000) })).ok } catch { return false } }
async function ensureAppium() {
  if (await appiumAvailable()) return null
  const child = spawn(config.appium.command, ['--address', config.appium.host, '--port', String(config.appium.port), '--base-path', '/', '--allow-insecure', config.appium.allowInsecure.join(',')], { shell: true, windowsHide: true, env: { ...process.env, JAVA_HOME: config.appium.javaHome } })
  await waitFor('Appium 服务启动', appiumAvailable, 20_000)
  return child
}
async function stopProcess(child) { if (!child) return; if (process.platform === 'win32' && child.pid) await run('taskkill', ['/pid', String(child.pid), '/t', '/f'], true); else child.kill() }
async function capture(driver, name) {
  try {
    await fs.writeFile(path.join(reportDir, `${name}.xml`), redact(await driver.source()), 'utf8')
    result.evidence.push(`${name}.xml`)
    await fs.writeFile(path.join(reportDir, `${name}.png`), Buffer.from(await driver.screenshot(), 'base64'))
    result.evidence.push(`${name}.png`)
  } catch {}
}
async function element(driver, using, value) { const found = await driver.find(using, value); return found.elementId || found.ELEMENT }
async function tapById(driver, id) {
  const node = await waitFor(`元素 ${id}`, async () => {
    for (const [using, value] of [['id', id], ['xpath', `//*[@resource-id="${id}"]`]]) {
      const found = await element(driver, using, value).catch(() => null)
      if (found) return found
    }
    return null
  })
  await driver.click(node)
}
async function tapByText(driver, text) {
  const node = await waitFor(`文本 ${text}`, async () => {
    const found = await element(driver, 'xpath', `//*[contains(@text,"${text}")]`).catch(() => null)
    return found || null
  })
  await driver.click(node)
}
async function tapResourceFromUiTree(driver, resourceId) {
  const source = await waitFor(`UI 树元素 ${resourceId}`, async () => {
    const current = await driver.source()
    return new RegExp(`resource-id="${resourceId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"[^>]*bounds="\\[\\d+,\\d+\\]\\[\\d+,\\d+\\]"`).test(current) ? current : null
  })
  const escapedId = resourceId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = source.match(new RegExp(`resource-id="${escapedId}"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`))
  if (!match) throw new Error(`UI 树没有返回 ${resourceId} 的边界`)
  const [, left, top, right, bottom] = match.map(Number)
  await adb(['shell', 'input', 'tap', String(Math.round((left + right) / 2)), String(Math.round((top + bottom) / 2))])
}
function activeRoute(source) {
  const pageRoutes = [...source.matchAll(/text="(pages\/[^"]+)\[\d+\]"/g)].map((match) => match[1])
  const pageRoute = {
    'pages/home': 'home-page',
    'pages/practice/exam-topics': 'practice-topics-page',
    'pages/practice/exam-assessment': 'practice-assessment-page',
    'pages/practice/answer': 'practice-answer-page',
  }[pageRoutes.at(-1)]
  if (pageRoute) return pageRoute
  return ['home-page', 'practice-topics-page', 'practice-assessment-page', 'practice-answer-page'].reduce((active, route) => {
    const index = source.lastIndexOf(`resource-id="${route}"`)
    return index > active.index ? { route, index } : active
  }, { route: '', index: -1 }).route
}
async function normalizeToHome(driver) {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const source = await driver.source()
    const overlayVisible = /填写基本资料|正在加载自测题目|暂无可用自测题目|请输入姓名|选择考试模式|批次创建后统一进入详情页|practice-start-summary/.test(source)
    if (activeRoute(source) === 'home-page' && !overlayVisible) return
    await adb(['shell', 'input', 'keyevent', '4'], true)
    await new Promise((resolve) => setTimeout(resolve, 600))
  }
  await waitFor('返回首页', async () => activeRoute(await driver.source()) === 'home-page')
}
async function step(id, name, action) {
  const item = { id, name, status: 'running' }
  result.steps.push(item)
  console.log(`[${scenario.id}] ${name}`)
  try { await action(); item.status = 'passed' } catch (error) { item.status = 'failed'; item.error = error.message; throw error }
}

async function main() {
  await fs.mkdir(reportDir, { recursive: true })
  result.device = { serial: await findDevice() }
  result.apk = await findApk()
  await launchCleanAppTask(adb, config.app)
  const appiumProcess = await ensureAppium()
  const driver = new Driver(config.appium.serverUrl)
  try {
    await driver.create({ alwaysMatch: { platformName: 'Android', 'appium:automationName': 'UiAutomator2', 'appium:deviceName': result.device.serial, 'appium:udid': result.device.serial, 'appium:app': result.apk, 'appium:appPackage': config.app.packageName, 'appium:appActivity': config.app.activity, 'appium:noReset': true, 'appium:fullReset': false, 'appium:newCommandTimeout': 180 } })
    await normalizeToHome(driver)
    await step(1, '登录后首页前置', async () => { await waitFor('首页', async () => activeRoute(await driver.source()) === 'home-page'); await capture(driver, '01-home') })
    await step(2, '章节测试入口与题型页', async () => {
      await tapByText(driver, '章节测试')
      await waitFor('章节测试页面', async () => {
        const source = await driver.source()
        return ['practice-topics-page', 'practice-assessment-page', 'practice-answer-page'].includes(activeRoute(source)) || /章节测试暂不可用|暂无可用题目主题/.test(source)
      })
      await capture(driver, '02-chapter-test-entry')
      await normalizeToHome(driver)
    })
    await step(3, '考试入口与组织绑定保护', async () => {
      await tapByText(driver, '考试')
      await waitFor('考试页面或绑定提示', async () => /选择考试模式|题库训练暂不可用|请先绑定企业|去绑定|理论考试|综合考试/.test(await driver.source()))
      await capture(driver, '03-exam-entry')
    })
    await step(4, '评测结果入口状态', async () => {
      await normalizeToHome(driver)
      await tapByText(driver, '评测结果')
      await waitFor('评测结果状态', async () => /测评未完成|评测报告|自测报告|您的测评未完成|知道了/.test(await driver.source()))
      await capture(driver, '04-assessment-result')
    })
    result.status = 'passed'
  } finally {
    try { const logs = await adb(['logcat', '-d', '-v', 'threadtime'], true); await fs.writeFile(path.join(reportDir, 'logcat-filtered.txt'), redact(`${logs.stdout}\n${logs.stderr}`), 'utf8'); result.evidence.push('logcat-filtered.txt') } catch {}
    await driver.close()
    await stopProcess(appiumProcess)
    await fs.writeFile(path.join(reportDir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
  }
}
main().catch(async (error) => { result.status = 'failed'; result.error = error.message; await fs.mkdir(reportDir, { recursive: true }); await fs.writeFile(path.join(reportDir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8'); console.error(`[${scenario.id}] 结果：failed`); console.error(error.stack || error.message); process.exitCode = 1 })
