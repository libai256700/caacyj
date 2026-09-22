import fs from 'node:fs/promises'
import path from 'node:path'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import config from '../config.mjs'
import { launchCleanAppTask } from './lib/app-task.mjs'

const execFileAsync = promisify(execFile)
const scenario = config.scenarios.jobsFilter
const trainingJobKeywords = ['教员', '讲师', '教师', '老师', '培训', '教学', '授课']
const startedAt = new Date()
const runId = startedAt.toISOString().replace(/[:.]/g, '-')
const reportDir = path.join(scenario.reportDir, runId)
const result = {
  scenarioId: scenario.id,
  status: 'running',
  startedAt: startedAt.toISOString(),
  device: null,
  apk: null,
  steps: [],
  evidence: [],
  branches: {}
}

class Driver {
  constructor(url) {
    this.url = url.replace(/\/$/, '')
    this.session = ''
  }

  async request(endpoint, method = 'GET', body) {
    const response = await fetch(`${this.url}${endpoint}`, {
      method,
      headers: body === undefined ? undefined : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(45_000)
    })
    const payload = await response.json().catch(() => ({}))
    const error = payload?.value?.error || payload?.value?.message
    if (!response.ok || error) {
      throw new Error(`${method} ${endpoint} failed: ${error || response.statusText}`)
    }
    return payload.value ?? payload
  }

  async create(capabilities) {
    const payload = await this.request('/session', 'POST', { capabilities })
    this.session = payload.sessionId || payload.value?.sessionId
    if (!this.session) throw new Error('Appium session 创建失败')
  }

  async close() {
    if (this.session) await this.request(`/session/${this.session}`, 'DELETE').catch(() => {})
    this.session = ''
  }

  command(endpoint, method = 'GET', body) {
    return this.request(`/session/${this.session}${endpoint}`, method, body)
  }

  source() { return this.command('/source') }
  screenshot() { return this.command('/screenshot') }
  find(using, value) { return this.command('/element', 'POST', { using, value }) }
  findElements(using, value) { return this.command('/elements', 'POST', { using, value }) }
  attribute(id, name) { return this.command(`/element/${id}/attribute/${name}`) }
  click(id) { return this.command(`/element/${id}/click`, 'POST', {}) }
}

const run = (command, args, allowFailure = false) => execFileAsync(command, args, {
  windowsHide: true,
  maxBuffer: 8 * 1024 * 1024,
  timeout: 10_000
}).catch((error) => {
  if (allowFailure) {
    return {
      stdout: error.stdout?.toString() || '',
      stderr: error.stderr?.toString() || error.message
    }
  }
  throw error
})

const adb = (args, allowFailure = false) => run(config.device.adbPath, ['-s', result.device.serial, ...args], allowFailure)
const pause = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

async function uiTree() {
  const remotePath = '/sdcard/jobs-003-current.xml'
  await adb(['shell', 'uiautomator', 'dump', remotePath])
  const { stdout } = await adb(['exec-out', 'cat', remotePath])
  return stdout
}

function redact(value) {
  return String(value)
    .replace(/(access[_-]?token|openid|auth[_-]?token|secret|password)["'\s:=]+[^,\s}\]]+/gi, '$1=<redacted>')
    .replace(/\b\d{11}\b/g, '<phone-redacted>')
}

async function findDevice() {
  const { stdout } = await run(config.device.adbPath, ['devices'])
  const devices = stdout.split(/\r?\n/)
    .slice(1)
    .map((line) => line.trim().split(/\s+/))
    .filter(([, state]) => state === 'device')
    .map(([serial]) => serial)
  const serial = config.device.serial || (devices.length === 1 ? devices[0] : '')
  if (!serial || !devices.includes(serial)) throw new Error('没有找到配置的 Android 真机')
  return serial
}

async function findApk() {
  const entries = await fs.readdir(config.app.apkDir, { withFileTypes: true })
  const candidates = []
  for (const entry of entries) {
    if (!entry.isFile() || !config.app.apkPattern.test(entry.name)) continue
    const fullPath = path.join(config.app.apkDir, entry.name)
    candidates.push({ fullPath, mtimeMs: (await fs.stat(fullPath)).mtimeMs })
  }
  candidates.sort((left, right) => right.mtimeMs - left.mtimeMs)
  if (!candidates.length) throw new Error(`没有找到 APK：${config.app.apkDir}`)
  return candidates[0].fullPath
}

async function appiumAvailable() {
  try {
    return (await fetch(`${config.appium.serverUrl}/status`, { signal: AbortSignal.timeout(2_000) })).ok
  } catch {
    return false
  }
}

async function ensureAppium() {
  if (await appiumAvailable()) return null
  const child = spawn(
    config.appium.command,
    ['--address', config.appium.host, '--port', String(config.appium.port), '--base-path', '/', '--allow-insecure', config.appium.allowInsecure.join(',')],
    { shell: true, windowsHide: true, env: { ...process.env, JAVA_HOME: config.appium.javaHome } }
  )
  await waitFor('Appium 服务启动', appiumAvailable, 60_000)
  return child
}

async function stopProcess(child) {
  if (!child) return
  if (process.platform === 'win32' && child.pid) {
    await run('taskkill', ['/pid', String(child.pid), '/t', '/f'], true)
  } else {
    child.kill()
  }
}

async function waitFor(label, predicate, timeout = scenario.timeoutMs, interval = 350) {
  const deadline = Date.now() + timeout
  let lastError
  while (Date.now() < deadline) {
    try {
      const value = await predicate()
      if (value) return value
    } catch (error) {
      lastError = error
    }
    await pause(interval)
  }
  throw new Error(`${label} 超时${lastError ? `：${lastError.message}` : ''}`)
}

async function capture(driver, name) {
  if (driver.session) {
    try {
      await fs.writeFile(path.join(reportDir, `${name}.png`), Buffer.from(await driver.screenshot(), 'base64'))
      result.evidence.push(`${name}.png`)
    } catch {}
    try {
      await fs.writeFile(path.join(reportDir, `${name}.xml`), redact(await driver.source()), 'utf8')
      result.evidence.push(`${name}.xml`)
    } catch {}
    return
  }
  try {
    await fs.writeFile(path.join(reportDir, `${name}.xml`), redact(await uiTree()), 'utf8')
    result.evidence.push(`${name}.xml`)
  } catch {}
}

async function findElement(driver, using, value) {
  const found = await driver.find(using, value)
  return found.elementId || found.ELEMENT
}

function elementId(element) {
  return element?.elementId || element?.ELEMENT || element?.['element-6066-11e4-a52e-4f735466cecf']
}

async function elementTextsByIdPrefix(driver, prefix) {
  const elements = await driver.findElements('xpath', `//*[starts-with(@resource-id,"${prefix}")]`)
  const values = []
  for (const element of elements) {
    const id = elementId(element)
    if (!id) continue
    const value = await driver.attribute(id, 'text').catch(() => '')
    if (value) values.push(value)
  }
  return values
}

async function waitForFilterOutcome(driver, label, prefix) {
  return waitFor(label, async () => {
    const source = await uiTree()
    if (source.includes('jobs-filter-empty')) return { branch: 'empty', values: [] }
    const values = textsByIdPrefix(source, prefix)
    return values.length ? { branch: 'matched', values } : null
  }, scenario.timeoutMs, 1_500)
}

function assertFilterValues(outcome, matcher, label) {
  if (outcome.branch === 'empty') return outcome
  const invalid = outcome.values.filter((value) => !matcher(value))
  if (invalid.length) throw new Error(`${label}出现不匹配结果：${invalid.join('、')}`)
  return outcome
}

function isTrainingJobTitle(value) {
  const title = value.replace(/\s/g, '')
  return trainingJobKeywords.some((keyword) => title.includes(keyword))
}

async function tapById(driver, id) {
  const element = await waitFor(`元素 ${id}`, async () => {
    for (const [using, value] of [
      ['id', id],
      ['xpath', `//*[@resource-id="${id}"]`]
    ]) {
      const found = await findElement(driver, using, value).catch(() => null)
      if (found) return found
    }
    return null
  })
  await driver.click(element)
}

async function tapText(driver, text) {
  await tapById(driver, `text:${text}`).catch(async () => {
    const element = await waitFor(`文本 ${text}`, async () => findElement(driver, 'xpath', `//*[contains(@text,"${text}")]`).catch(() => null))
    await driver.click(element)
  })
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

function readAttribute(node, name) {
  const match = node.match(new RegExp(`${name}="([^"]*)"`))
  return match ? decodeXml(match[1]) : ''
}

function decodeXml(value) {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

function nodes(source) {
  return Array.from(source.matchAll(/<node\b[^>]*>/g), (match) => match[0])
}

function boundsForResource(source, resourceId) {
  const node = nodes(source).find((item) => readAttribute(item, 'resource-id') === resourceId)
  const value = node && readAttribute(node, 'bounds')
  const match = value && value.match(/^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$/)
  if (!match) return null
  const [, left, top, right, bottom] = match.map(Number)
  return { left, top, right, bottom }
}

async function locateResource(resourceId, { reveal = false } = {}) {
  if (!reveal) {
    return waitFor(`元素 ${resourceId}`, async () => boundsForResource(await uiTree(), resourceId), scenario.timeoutMs, 1_000)
  }

  for (let attempt = 0; attempt < 12; attempt += 1) {
    const source = await uiTree()
    const bounds = boundsForResource(source, resourceId)
    if (bounds && bounds.top > 0 && bounds.bottom > bounds.top && bounds.bottom <= 2_180) return bounds

    const menu = boundsForResource(source, 'jobs-province-menu')
    if (!menu || menu.bottom <= menu.top) throw new Error('省份菜单未显示可滚动区域')
    const x = Math.round((menu.left + menu.right) / 2)
    const fromY = Math.max(menu.top + 40, menu.bottom - 50)
    const toY = Math.min(menu.bottom - 40, menu.top + 60)
    console.log(`[${scenario.id}] ${resourceId}未在菜单视口，滚动省份菜单`)
    await adb(['shell', 'input', 'swipe', String(x), String(fromY), String(x), String(toY), '300'])
    await pause(600)
  }
  throw new Error(`元素 ${resourceId}滚动后仍不可见`)
}

async function tapByResourceId(resourceId, options) {
  const bounds = await locateResource(resourceId, options)
  const x = Math.round((bounds.left + bounds.right) / 2)
  const y = Math.round((bounds.top + Math.min(bounds.bottom, 2_050)) / 2)
  console.log(`[${scenario.id}] 点击 ${resourceId} @ ${x},${y}`)
  await adb(['shell', 'input', 'tap', String(x), String(y)])
}

function textsByIdPrefix(source, prefix) {
  return nodes(source)
    .map((node) => ({ id: readAttribute(node, 'resource-id'), text: readAttribute(node, 'text') }))
    .filter((item) => item.id.startsWith(prefix) && item.text)
    .map((item) => item.text)
}

function assertFilterResult(source, prefix, matcher, label) {
  const values = textsByIdPrefix(source, prefix)
  if (!values.length) {
    if (!source.includes('jobs-filter-empty')) throw new Error(`${label}没有岗位结果，也没有展示空态`)
    return { branch: 'empty', values: [] }
  }
  const invalid = values.filter((value) => !matcher(value))
  if (invalid.length) throw new Error(`${label}出现不匹配结果：${invalid.join('、')}`)
  return { branch: 'matched', values }
}

async function normalizeToHome() {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const source = await uiTree().catch(() => '')
    if (source && activeRoute(source) === 'home-page') return
    await adb(['shell', 'input', 'keyevent', '4'], true)
    await pause(600)
  }
  await waitFor('返回首页', async () => activeRoute(await uiTree()) === 'home-page', scenario.timeoutMs, 1_000)
}

async function step(id, name, action) {
  const item = { id, name, status: 'running' }
  result.steps.push(item)
  console.log(`[${scenario.id}] ${name}`)
  try {
    await action()
    item.status = 'passed'
  } catch (error) {
    item.status = 'failed'
    item.error = error.message
    throw error
  }
}

async function main() {
  await fs.mkdir(reportDir, { recursive: true })
  result.device = { serial: await findDevice() }
  result.apk = await findApk()
  await launchCleanAppTask(adb, config.app)
  const driver = { session: '' }

  try {
    await normalizeToHome()

    await step(1, '进入岗位招聘并确认筛选控件', async () => {
      await tapByResourceId('home-assistant-jobs')
      await waitFor('岗位页面', async () => activeRoute(await uiTree()) === 'jobs-page', scenario.timeoutMs, 1_000)
      const filterControls = await waitFor('岗位筛选控件', async () => {
        const source = await uiTree()
        if (source.includes('jobs-type-instructor') && source.includes('jobs-type-engineer') && source.includes('jobs-province-trigger')) {
          return true
        }
        return false
      }, scenario.filterControlTimeoutMs ?? 8_000, 500).catch(() => null)
      if (!filterControls) {
        const source = await uiTree().catch(() => '')
        const hasJobsPage = activeRoute(source) === 'jobs-page' || source.includes('岗位招聘')
        throw new Error(
          hasJobsPage
            ? '最新岗位页面未提供筛选控件（jobs-type-instructor/jobs-type-engineer/jobs-province-trigger）；请先接入岗位筛选功能，再执行 JOBS-003'
            : '未确认当前页面为岗位招聘页面，无法执行岗位筛选验收'
        )
      }
      await capture(driver, '01-jobs-filters')
    })

    await step(2, '教员岗位筛选', async () => {
      await tapByResourceId('jobs-type-instructor')
      const outcome = await waitForFilterOutcome(driver, '教员筛选结果', 'job-title-')
      result.branches.instructor = assertFilterValues(outcome, isTrainingJobTitle, '教员筛选')
      await capture(driver, '02-jobs-instructor')
    })

    await step(3, '工程师岗位筛选', async () => {
      await tapByResourceId('jobs-type-engineer')
      const outcome = await waitForFilterOutcome(driver, '工程师筛选结果', 'job-title-')
      result.branches.engineer = assertFilterValues(outcome, (value) => value.includes('工程师'), '工程师筛选')
      await capture(driver, '03-jobs-engineer')
    })

    await step(4, '展示省份筛选选项', async () => {
      await tapByResourceId('jobs-type-all')
      await tapByResourceId('jobs-province-trigger')
      await waitFor('省份选项菜单', async () => (await uiTree()).includes('jobs-province-menu'), scenario.timeoutMs, 1_500)
      await capture(driver, '04-jobs-province-options')
    })

    await step(5, '湖北省岗位筛选', async () => {
      await tapByResourceId('jobs-province-option-hubei')
      const outcome = await waitForFilterOutcome(driver, '湖北省筛选结果', 'job-address-')
      result.branches.hubei = assertFilterValues(outcome, (value) => /湖北(?:省)?/.test(value), '湖北省筛选')
      await capture(driver, '05-jobs-hubei')
    })

    result.status = 'passed'
  } finally {
    try {
      const logs = await adb(['logcat', '-d', '-v', 'threadtime'], true)
      await fs.writeFile(path.join(reportDir, 'logcat-filtered.txt'), redact(`${logs.stdout}\n${logs.stderr}`), 'utf8')
      result.evidence.push('logcat-filtered.txt')
    } catch {}
    await fs.writeFile(path.join(reportDir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
  }
}

main().catch(async (error) => {
  result.status = 'failed'
  result.error = error.message
  await fs.mkdir(reportDir, { recursive: true })
  await fs.writeFile(path.join(reportDir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
  console.error(`[${scenario.id}] 结果：failed`)
  console.error(error.stack || error.message)
  process.exitCode = 1
})
