import fs from 'node:fs/promises'
import path from 'node:path'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import config from '../config.mjs'
import { launchCleanAppTask } from './lib/app-task.mjs'

const execFileAsync = promisify(execFile)
const scenario = config.scenarios.jobsScrollRestore
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
      signal: AbortSignal.timeout(45_000),
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
const pause = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

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
  if (!files.length) throw new Error('没有找到自定义基座 APK')
  return files[0].path
}

async function waitFor(label, predicate, timeout = scenario.timeoutMs) {
  const deadline = Date.now() + timeout
  let lastError
  while (Date.now() < deadline) {
    try { const value = await predicate(); if (value) return value } catch (error) { lastError = error }
    await pause(350)
  }
  throw new Error(`${label} 超时${lastError ? `：${lastError.message}` : ''}`)
}

async function appiumAvailable() {
  try { return (await fetch(`${config.appium.serverUrl}/status`, { signal: AbortSignal.timeout(2_000) })).ok } catch { return false }
}

async function ensureAppium() {
  if (await appiumAvailable()) return null
  const child = spawn(config.appium.command, ['--address', config.appium.host, '--port', String(config.appium.port), '--base-path', '/', '--allow-insecure', config.appium.allowInsecure.join(',')], { shell: true, windowsHide: true, env: { ...process.env, JAVA_HOME: config.appium.javaHome } })
  await waitFor('Appium 服务启动', appiumAvailable, 60_000)
  return child
}

async function stopProcess(child) {
  if (!child) return
  if (process.platform === 'win32' && child.pid) await run('taskkill', ['/pid', String(child.pid), '/t', '/f'], true)
  else child.kill()
}

async function capture(driver, name) {
  try {
    await fs.writeFile(path.join(reportDir, `${name}.xml`), redact(await driver.source()), 'utf8')
    result.evidence.push(`${name}.xml`)
    await fs.writeFile(path.join(reportDir, `${name}.png`), Buffer.from(await driver.screenshot(), 'base64'))
    result.evidence.push(`${name}.png`)
  } catch {}
}

async function element(driver, using, value) { const found = await driver.find(using, value); return found.elementId || found.ELEMENT }

async function tapById(driver, id, fallbackText = '') {
  const node = await waitFor(`元素 ${id}`, async () => {
    for (const [using, value] of [['id', id], ['xpath', `//*[@resource-id="${id}"]`]]) {
      const found = await element(driver, using, value).catch(() => null)
      if (found) return found
    }
    if (fallbackText) {
      return element(driver, 'xpath', `//*[contains(@text,"${fallbackText}")]`).catch(() => null)
    }
    return null
  })
  await driver.click(node)
}

function activeRoute(source) {
  const pageRoutes = [...source.matchAll(/text="pages\/([^"\[]+)\[\d+\]"/g)].map((match) => match[1])
  if (pageRoutes.length) return `${pageRoutes.at(-1)}-page`
  const routes = ['home-page', 'jobs-page', 'center-page', 'profile-page']
  return routes.reduce((active, route) => {
    const index = source.lastIndexOf(`resource-id="${route}"`)
    return index > active.index ? { route, index } : active
  }, { route: '', index: -1 }).route
}

function visibleJobIds(source) {
  const ids = Array.from(source.matchAll(/resource-id="job-card-([^"]+)"/g), (match) => match[1])
  if (ids.length) return ids
  return detailBounds(source).map((item) => `text-${item.top}`)
}

function detailBounds(source) {
  return [...source.matchAll(/<[^>]*\btext="查看详情"[^>]*\bbounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*>/g)]
    .map((match) => ({ left: Number(match[1]), top: Number(match[2]), right: Number(match[3]), bottom: Number(match[4]) }))
}

function boundsForResource(source, resourceId) {
  const escapedId = resourceId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = source.match(new RegExp(`resource-id="${escapedId}"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`))
  if (!match) return null
  const [, left, top, right, bottom] = match.map(Number)
  return { left, top, right, bottom }
}

async function normalizeToHome(driver) {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    if (activeRoute(await driver.source()) === 'home-page') return
    await adb(['shell', 'input', 'keyevent', '4'], true)
    await pause(600)
  }
  await waitFor('返回首页', async () => activeRoute(await driver.source()) === 'home-page')
}

async function scrollPastFirstVisibleJob(driver) {
  const initialSource = await driver.source()
  const initialIds = visibleJobIds(initialSource)
  const textAnchorMode = !initialSource.includes('resource-id="job-card-')
  const firstJobId = initialIds[0]
  if (!firstJobId) throw new Error('岗位列表没有可滚动验证的岗位卡片')
  const scrollBounds = boundsForResource(initialSource, 'jobs-scroll') || boundsForResource(initialSource, 'jobs-page') || { left: 0, top: 120, right: 1080, bottom: 2356 }
  if (!scrollBounds) throw new Error('岗位滚动容器未出现在 UI 树中')

  const x = Math.round((scrollBounds.left + scrollBounds.right) / 2)
  const fromY = Math.round(scrollBounds.top + (scrollBounds.bottom - scrollBounds.top) * 0.72)
  const toY = Math.round(scrollBounds.top + (scrollBounds.bottom - scrollBounds.top) * 0.25)
  for (let attempt = 0; attempt < 4; attempt += 1) {
    await adb(['shell', 'input', 'swipe', String(x), String(fromY), String(x), String(toY), '450'])
    await pause(1_800)
    const source = await driver.source()
    const ids = visibleJobIds(source)
    if (ids.length && !ids.includes(firstJobId)) return { firstJobId, anchorJobId: textAnchorMode ? '__text__' : ids[0] }
  }
  throw new Error('岗位列表滚动后仍停留在首个岗位，无法建立返回位置锚点')
}

async function focusedPackage() {
  const { stdout } = await adb(['shell', 'dumpsys', 'window'], true)
  return stdout.match(/mCurrentFocus=Window\{[^ ]+ u\d+ ([^/]+)/)?.[1] || ''
}

async function returnToAppAfterExternal() {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await adb(['shell', 'input', 'keyevent', '4'], true)
    await pause(900)
    if ((await focusedPackage()) === config.app.packageName) return
  }

  // Some Android browser builds consume BACK for page history. Restore the
  // app task after the user-visible BACK attempt so the assertion is stable.
  await adb(['shell', 'am', 'force-stop', 'com.android.browser'], true)
  await adb(['shell', 'am', 'force-stop', 'com.android.chrome'], true)
  await waitFor('应用任务恢复', async () => (await focusedPackage()) === config.app.packageName, 8_000)
}

async function leaveAppAndReturn(driver, anchorJobId) {
  if (anchorJobId === '__text__') {
    const detail = await waitFor('查看详情入口', async () => element(driver, 'xpath', '//*[contains(@text,"查看详情")]').catch(() => null))
    await driver.click(detail)
  } else {
    await tapById(driver, `job-detail-${anchorJobId}`)
  }
  const detailOutcome = await waitFor('岗位详情访问结果', async () => {
    const source = await driver.source().catch(() => '')
    if (/请先绑定企业|去绑定|联系客服/.test(source)) return 'binding-required'
    const packageName = await focusedPackage()
    return packageName && packageName !== config.app.packageName ? `external:${packageName}` : false
  }, 15_000)

  if (detailOutcome.startsWith('external:')) {
    result.externalExit = '岗位详情外部链接'
    await returnToAppAfterExternal()
  } else {
    // The fixed SMS account can be blocked by organization access. Close that
    // dialog, then use a system browser to exercise the identical app hide/show lifecycle.
    result.externalExit = '系统浏览器生命周期替代（当前账号未通过组织审核）'
    await adb(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', 'https://www.example.com'])
    await waitFor('系统浏览器打开', async () => (await focusedPackage()) !== config.app.packageName, 15_000)
    await returnToAppAfterExternal()
  }
  await waitFor('返回岗位列表', async () => activeRoute(await driver.source()) === 'jobs-page', 15_000)
  await pause(1_200)
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
    await step(1, '进入岗位列表', async () => {
      await tapById(driver, 'home-assistant-jobs', '岗位招聘')
      await waitFor('岗位页面', async () => activeRoute(await driver.source()) === 'jobs-page')
      await waitFor('岗位卡片', async () => visibleJobIds(await driver.source()).length > 0)
      await capture(driver, '01-jobs-initial')
    })
    let anchorJobId = ''
    let firstJobId = ''
    await step(2, '滚动到后续岗位', async () => {
      ({ firstJobId, anchorJobId } = await scrollPastFirstVisibleJob(driver))
      if (anchorJobId === '__text__') result.textAnchorMode = true
      result.scrollAnchor = { firstJobId, anchorJobId }
      result.scrolledVisibleJobIds = visibleJobIds(await driver.source())
      if (result.textAnchorMode) result.scrolledDetailTops = detailBounds(await driver.source()).map((item) => item.top)
      await capture(driver, '02-jobs-scrolled')
    })
    await step(3, '离开应用并返回岗位列表', async () => {
      await leaveAppAndReturn(driver, anchorJobId)
      await capture(driver, '03-jobs-returned')
    })
    await step(4, '验证返回后保持滚动位置', async () => {
      const returnedIds = visibleJobIds(await driver.source())
      result.returnedVisibleJobIds = returnedIds
      if (result.textAnchorMode) {
        const returnedTops = detailBounds(await driver.source()).map((item) => item.top)
        const expectedTop = result.scrolledDetailTops?.[0]
        if (!returnedTops.length || expectedTop === undefined || Math.abs(returnedTops[0] - expectedTop) > 80) {
          throw new Error(`返回后岗位列表位置未保持：滚动后首个详情按钮 top=${expectedTop ?? '未知'}，返回后=${returnedTops[0] ?? '未知'}`)
        }
        return
      }
      const scrolledIds = result.scrolledVisibleJobIds || []
      const sharedIds = scrolledIds.filter((id) => returnedIds.includes(id))
      result.sharedVisibleJobIds = sharedIds
      if (sharedIds.length < 3) throw new Error(`返回后与离开前共享岗位卡片不足：${sharedIds.join(',')}`)
      if (returnedIds.includes(firstJobId)) throw new Error(`返回后重新展示了列表顶部岗位 ${firstJobId}`)
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
