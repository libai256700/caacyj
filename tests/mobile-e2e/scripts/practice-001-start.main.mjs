import fs from 'node:fs/promises'
import path from 'node:path'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import config from '../config.mjs'
import { launchCleanAppTask } from './lib/app-task.mjs'

const execFileAsync = promisify(execFile)
const scenario = { id: 'PRACTICE-001', reportDir: path.resolve('tests/mobile-e2e/reports/practice-001'), timeoutMs: 60_000 }
const startedAt = new Date()
const runId = startedAt.toISOString().replace(/[:.]/g, '-')
const reportDir = path.join(scenario.reportDir, runId)
const result = { scenarioId: scenario.id, status: 'running', startedAt: startedAt.toISOString(), device: null, apk: null, steps: [], evidence: [] }

class Driver {
  constructor(url) { this.url = url.replace(/\/$/, ''); this.session = ''; this.lastSource = '' }
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
  async source() { this.lastSource = await this.command('/source'); return this.lastSource }
  screenshot() { return this.command('/screenshot') }
  find(using, value) { return this.command('/element', 'POST', { using, value }) }
  rect(id) { return this.command(`/element/${id}/rect`) }
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
  for (const entry of entries) if (entry.isFile() && config.app.apkPattern.test(entry.name)) files.push({ path: path.join(config.app.apkDir, entry.name), mtime: (await fs.stat(path.join(config.app.apkDir, entry.name))).mtimeMs })
  files.sort((a, b) => b.mtime - a.mtime)
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

async function appiumAvailable() { try { return (await fetch(`${config.appium.serverUrl}/status`)).ok } catch { return false } }
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
async function sourceHas(driver, label, pattern) { return waitFor(label, async () => pattern.test(await driver.source())) }
function activeRoute(source) {
  const pageRoutes = [...source.matchAll(/text="(pages\/[^"]+)\[\d+\]"/g)].map((match) => match[1])
  const pageRoute = {
    'pages/home': 'home-page',
    'pages/practice/exam-topics': 'practice-topics-page',
    'pages/practice/exam-assessment': 'practice-assessment-page',
    'pages/practice/answer': 'practice-answer-page',
  }[pageRoutes.at(-1)]
  if (pageRoute) return pageRoute
  const routes = ['home-page', 'practice-topics-page', 'practice-assessment-page', 'practice-answer-page']
  return routes.reduce((active, route) => {
    const index = source.lastIndexOf(`resource-id="${route}"`)
    return index > active.index ? { route, index } : active
  }, { route: '', index: -1 }).route
}
async function activePage(driver, label, route, pattern = /.*/) {
  return waitFor(label, async () => {
    const source = await driver.source()
    return activeRoute(source) === route && pattern.test(source)
  })
}
async function activeAnyPage(driver, label, routes) {
  return waitFor(label, async () => {
    const source = await driver.source()
    const route = activeRoute(source)
    return routes.includes(route) ? { route, source } : null
  })
}
async function normalizeToHome(driver) {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const source = await driver.source()
    if (activeRoute(source) === 'home-page') return
    await adb(['shell', 'input', 'keyevent', '4'], true)
    await new Promise((resolve) => setTimeout(resolve, 600))
  }
  await activePage(driver, '返回首页', 'home-page', /开始测评|逐题练习|岗位招聘/)
}
async function element(driver, using, value) { const found = await driver.find(using, value); return found.elementId || found.ELEMENT }
function boundsForResourceId(source, id) {
  const escapedId = id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = String(source || '').match(new RegExp(`resource-id="${escapedId}"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`))
  if (!match) return null
  const [, left, top, right, bottom] = match.map(Number)
  return { x: Math.round((left + right) / 2), y: Math.round((top + bottom) / 2) }
}
function boundsForText(source, text) {
  const escapedText = text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = String(source || '').match(new RegExp(`text="${escapedText}"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`))
  if (!match) return null
  const [, left, top, right, bottom] = match.map(Number)
  return { x: Math.round((left + right) / 2), y: Math.round((top + bottom) / 2) }
}
async function tapBounds(bounds) {
  await adb(['shell', 'input', 'tap', String(bounds.x), String(bounds.y)])
}
async function tapById(driver, id) {
  const cachedBounds = boundsForResourceId(driver.lastSource, id)
  if (cachedBounds) {
    await tapBounds(cachedBounds)
    return
  }
  const node = await waitFor(`元素 ${id}`, async () => {
    const source = await driver.source()
    const bounds = boundsForResourceId(source, id)
    if (bounds) return bounds
    for (const [using, value] of [
      ['id', id],
      ['xpath', `//*[@resource-id="${id}"]`],
      ['xpath', `//*[@content-desc and contains(@content-desc,"${id.replace('practice-topic-', '')}")]`],
    ]) {
      const found = await element(driver, using, value).catch(() => null)
      if (found) return found
    }
    return null
  })
  if (node && typeof node.x === 'number') await tapBounds(node)
  else await driver.click(node)
}
async function tapByText(driver, text) {
  const cachedBounds = boundsForText(driver.lastSource, text)
  if (cachedBounds) {
    await tapBounds(cachedBounds)
    return
  }
  const node = await waitFor(`文本 ${text}`, async () => {
    const source = await driver.source()
    const bounds = boundsForText(source, text)
    if (bounds) return bounds
    return element(driver, 'xpath', `//*[contains(@text,"${text}")]`).catch(() => null)
  })
  if (node && typeof node.x === 'number') await tapBounds(node)
  else await driver.click(node)
}
async function step(id, name, action) {
  const item = { id, name, status: 'running', startedAt: new Date().toISOString() }
  const started = Date.now()
  result.steps.push(item)
  console.log(`[${scenario.id}] ${name}`)
  try {
    await action()
    item.status = 'passed'
  } catch (error) {
    item.status = 'failed'
    item.error = error.message
    throw error
  } finally {
    item.durationMs = Date.now() - started
    item.finishedAt = new Date().toISOString()
    console.log(`[${scenario.id}] ${name} 耗时 ${item.durationMs}ms`)
  }
}

async function main() {
  await fs.mkdir(reportDir, { recursive: true })
  result.device = { serial: await findDevice() }
  result.apk = await findApk()
  await launchCleanAppTask(adb, config.app)
  const appiumProcess = await ensureAppium()
  const driver = new Driver(config.appium.serverUrl)
  try {
    await driver.create({ alwaysMatch: { platformName: 'Android', 'appium:automationName': 'UiAutomator2', 'appium:deviceName': result.device.serial, 'appium:udid': result.device.serial, 'appium:app': result.apk, 'appium:appPackage': config.app.packageName, 'appium:appActivity': config.app.activity, 'appium:autoGrantPermissions': true, 'appium:noReset': true, 'appium:fullReset': false, 'appium:newCommandTimeout': 180, 'appium:chromedriverAutodownload': true } })
    await normalizeToHome(driver)
    await step(1, '已登录首页前置', async () => { await activePage(driver, '首页', 'home-page', /开始测评|逐题练习|岗位招聘/); await capture(driver, '01-home') })
    let entryRoute = ''
    await step(2, '进入逐题练习入口', async () => { await tapByText(driver, '逐题练习'); const page = await activeAnyPage(driver, '逐题练习页面', ['practice-topics-page', 'practice-assessment-page', 'practice-answer-page']); entryRoute = page.route; await capture(driver, `02-${entryRoute}`) })
    await step(3, '选择题目主题或恢复批次', async () => {
      if (entryRoute === 'practice-topics-page') {
        await tapById(driver, 'practice-topic-1')
        await activePage(driver, '批次详情', 'practice-assessment-page', /题量|总分|开始练习/)
        await capture(driver, '03-assessment')
      } else {
        await capture(driver, `03-${entryRoute}-resumed`)
      }
    })
    await step(4, '进入答题页', async () => {
      if (activeRoute(await driver.source()) === 'practice-assessment-page') await tapById(driver, 'practice-start-button').catch(() => tapByText(driver, '开始练习'))
      await activePage(driver, '答题页', 'practice-answer-page', /题目|提交|下一题|practice-question-stem/)
    })
    await step(5, '提交首题并验证结果态', async () => {
      const source = await driver.source()
      const optionMatch = source.match(/resource-id="(practice-option-[^"]+)"/)
      if (optionMatch) await tapById(driver, optionMatch[1])
      else if (/text="A\."/.test(source)) await tapByText(driver, 'A.')
      else throw new Error('答题页没有暴露可选择的题目选项')
      // The result text is intentionally not interpreted. This only checks
      // that submitting any legal option produces the answer-result state.
      await sourceHas(driver, '答案提交结果态', /回答正确|回答错误|试题详解/)
      await capture(driver, '05-answer-result')
    })
    await step(6, '进入下一题并验证题目推进', async () => {
      const before = await driver.source()
      const beforeMatch = before.match(/text="第\s*(\d+)\s*题"/)
      const beforeIndex = beforeMatch ? Number.parseInt(beforeMatch[1], 10) : 0
      await tapByText(driver, '下一题')
      await waitFor('下一题加载', async () => {
        const source = await driver.source()
        if (activeRoute(source) !== 'practice-answer-page') return false
        if (/正在拉取题目|提交中|判题中/.test(source)) return false
        const match = source.match(/text="第\s*(\d+)\s*题"/)
        return match && Number.parseInt(match[1], 10) > beforeIndex
      })
      await capture(driver, '06-next-question')
    })
    await step(7, '返回上一题并验证题目可继续操作', async () => {
      const before = await driver.source()
      await tapByText(driver, '上一题')
      await waitFor('上一题加载', async () => {
        const source = await driver.source()
        return activeRoute(source) === 'practice-answer-page'
          && !/正在拉取题目|提交中|判题中/.test(source)
          && source !== before
      })
      await capture(driver, '07-previous-question')
    })
    result.status = 'passed'
  } finally {
    try { const logs = await adb(['logcat', '-d', '-v', 'threadtime'], true); await fs.writeFile(path.join(reportDir, 'logcat-filtered.txt'), `${redact(`${logs.stdout}\n${logs.stderr}`)}\n`, 'utf8'); result.evidence.push('logcat-filtered.txt') } catch {}
    await driver.close()
    await stopProcess(appiumProcess)
    await fs.writeFile(path.join(reportDir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
  }
}

main().catch(async (error) => { result.status = 'failed'; result.error = error.message; await fs.mkdir(reportDir, { recursive: true }); await fs.writeFile(path.join(reportDir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8'); console.error(`[${scenario.id}] 结果：failed`); console.error(error.stack || error.message); process.exitCode = 1 })
