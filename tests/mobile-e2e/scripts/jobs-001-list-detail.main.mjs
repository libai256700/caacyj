import fs from 'node:fs/promises'
import path from 'node:path'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import config from '../config.mjs'
import { launchCleanAppTask } from './lib/app-task.mjs'

const execFileAsync = promisify(execFile)
const scenario = config.scenarios.jobs
const startedAt = new Date()
const runId = startedAt.toISOString().replace(/[:.]/g, '-')
const reportDir = path.join(scenario.reportDir, runId)
const result = { scenarioId: scenario.id, status: 'running', startedAt: startedAt.toISOString(), device: null, apk: null, steps: [], evidence: [] }

class Driver {
  constructor(url) { this.url = url.replace(/\/$/, ''); this.session = '' }
  async request(endpoint, method = 'GET', body) {
    const response = await fetch(`${this.url}${endpoint}`, {
      method,
      headers: body === undefined ? undefined : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(45_000)
    })
    const payload = await response.json().catch(() => ({}))
    const error = payload?.value?.error || payload?.value?.message
    if (!response.ok || error) throw new Error(`${method} ${endpoint} failed: ${error || response.statusText}`)
    return payload.value ?? payload
  }
  async create(capabilities) {
    const payload = await this.request('/session', 'POST', { capabilities })
    this.session = payload.sessionId || payload.value?.sessionId
    if (!this.session) throw new Error('Appium session 创建失败')
  }
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

async function appiumAvailable() {
  try { return (await fetch(`${config.appium.serverUrl}/status`, { signal: AbortSignal.timeout(2_000) })).ok } catch { return false }
}
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
async function tapByText(driver, text, label = text) {
  const node = await waitFor(label, async () => {
    const found = await element(driver, 'xpath', `//*[contains(@text,"${text}")]`).catch(() => null)
    return found || null
  })
  await driver.click(node)
}
async function tapResourceOrText(driver, id, text, label = text) {
  const byId = await element(driver, 'id', id).catch(() => null)
  if (byId) {
    await driver.click(byId)
    return
  }
  await tapByText(driver, text, label)
}
async function activeRoute(driver) {
  const source = await driver.source()
  const pageRoutes = [...source.matchAll(/text="pages\/([^"\[]+)\[\d+\]"/g)].map((match) => match[1])
  if (pageRoutes.length) return `${pageRoutes.at(-1)}-page`
  const routes = ['home-page', 'jobs-page', 'center-page', 'profile-page']
  return routes.reduce((active, route) => {
    const index = source.lastIndexOf(`resource-id="${route}"`)
    return index > active.index ? { route, index } : active
  }, { route: '', index: -1 }).route
}

async function tapFirstDetail(driver) {
  const node = await waitFor('查看详情入口', async () => element(driver, 'xpath', '//*[contains(@text,"查看详情")]').catch(() => null))
  await driver.click(node)
}
async function normalizeToHome(driver) {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    if (await activeRoute(driver) === 'home-page') return
    await adb(['shell', 'input', 'keyevent', '4'], true)
    await new Promise((resolve) => setTimeout(resolve, 600))
  }
  await waitFor('返回首页', async () => (await activeRoute(driver)) === 'home-page')
}
async function focusedPackage() {
  const { stdout } = await adb(['shell', 'dumpsys', 'window'], true)
  return stdout.match(/mCurrentFocus=Window\{[^ ]+ u\d+ ([^/]+)/)?.[1] || ''
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
    await step(1, '登录后首页前置', async () => { await waitFor('首页', async () => (await activeRoute(driver)) === 'home-page'); await capture(driver, '01-home') })
    await step(2, '进入岗位招聘列表', async () => {
      await tapResourceOrText(driver, 'home-assistant-jobs', '岗位招聘', '岗位招聘入口')
      await waitFor('岗位页面', async () => (await activeRoute(driver)) === 'jobs-page')
      await waitFor('岗位列表状态', async () => /岗位招聘|正在加载岗位列表|暂无招聘岗位|岗位信息暂不可用|查看详情/.test(await driver.source()))
      await capture(driver, '02-jobs-list')
    })
    let jobId = ''
    await step(3, '验证岗位列表数据或空态', async () => {
      const source = await driver.source()
      const match = source.match(/resource-id="(job-card-[^"]+)"/)
      if (match) { jobId = match[1].replace(/^job-card-/, ''); return }
      if ((source.match(/text="查看详情"/g) || []).length > 0) { jobId = '__text__'; return }
      if (/暂无招聘岗位|岗位信息暂不可用/.test(source)) return
      throw new Error('岗位页面既没有岗位卡片，也没有明确空态')
    })
    await step(4, '进入首个岗位详情分支', async () => {
      if (!jobId) { await capture(driver, '04-jobs-empty'); return }
      if (jobId === '__text__') await tapFirstDetail(driver)
      else {
        const detailId = await element(driver, 'id', `job-detail-${jobId}`).catch(() => null)
        if (detailId) await driver.click(detailId)
        else await tapFirstDetail(driver)
      }
      const outcome = await waitFor('岗位详情访问结果', async () => {
        const source = await driver.source().catch(() => '')
        // The complete UI tree retains pages in the navigation stack, including
        // the home-page "联系客服" entry. Only the dialog's unique title/copy
        // establishes that the access-blocking branch was actually rendered.
        if (/暂不可查看详情|请先绑定企业，绑定成功后即可查看招聘详情/.test(source)) return 'binding-required'
        const packageName = await focusedPackage()
        return packageName && packageName !== config.app.packageName ? `external:${packageName}` : false
      })
      result.jobDetailOutcome = outcome
      await capture(driver, `04-job-detail-${outcome.replace(/[^a-z0-9-]/gi, '-')}`)
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
