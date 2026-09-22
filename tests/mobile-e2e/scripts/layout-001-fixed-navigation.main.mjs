import fs from 'node:fs/promises'
import path from 'node:path'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import config from '../config.mjs'
import { launchCleanAppTask } from './lib/app-task.mjs'

const execFileAsync = promisify(execFile)
const scenario = config.scenarios.layout
const runId = new Date().toISOString().replace(/[:.]/g, '-')
const reportDir = path.join(scenario.reportDir, runId)
const result = {
  scenarioId: scenario.id,
  status: 'running',
  startedAt: new Date().toISOString(),
  device: null,
  apk: null,
  steps: [],
  evidence: [],
  skipped: [],
}

class WebDriverClient {
  constructor(serverUrl) {
    this.serverUrl = serverUrl.replace(/\/$/, '')
    this.sessionId = ''
  }

  async request(endpoint, method = 'GET', body) {
    const response = await fetch(`${this.serverUrl}${endpoint}`, {
      method,
      headers: body === undefined ? undefined : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(15_000),
    })
    const payload = await response.json().catch(() => ({}))
    const error = payload?.value?.error || payload?.value?.message
    if (!response.ok || error) throw new Error(`${method} ${endpoint} failed: ${error || response.statusText}`)
    return payload.value ?? payload
  }

  async createSession(capabilities) {
    const payload = await this.request('/session', 'POST', { capabilities })
    this.sessionId = payload.sessionId || payload.value?.sessionId
    if (!this.sessionId) throw new Error('Appium 没有返回 sessionId')
  }

  async deleteSession() {
    if (!this.sessionId) return
    await this.request(`/session/${this.sessionId}`, 'DELETE').catch(() => {})
    this.sessionId = ''
  }

  command(endpoint, method = 'GET', body) {
    if (!this.sessionId) throw new Error('Appium session 尚未建立')
    return this.request(`/session/${this.sessionId}${endpoint}`, method, body)
  }

  source() { return this.command('/source') }
  screenshot() { return this.command('/screenshot') }
  find(using, value) { return this.command('/element', 'POST', { using, value }) }
  findAll(using, value) { return this.command('/elements', 'POST', { using, value }) }
  rect(id) { return this.command(`/element/${id}/rect`) }
  click(id) { return this.command(`/element/${id}/click`, 'POST', {}) }
}

async function runCommand(command, args, allowFailure = false) {
  try {
    return await execFileAsync(command, args, { windowsHide: true, maxBuffer: 8 * 1024 * 1024, timeout: 15_000 })
  } catch (error) {
    if (allowFailure) return { stdout: error.stdout || '', stderr: error.stderr || error.message }
    throw error
  }
}

async function adb(args, allowFailure = false) {
  const prefix = result.device?.serial ? ['-s', result.device.serial] : []
  return runCommand(config.device.adbPath, [...prefix, ...args], allowFailure)
}

async function findDevice() {
  const { stdout } = await runCommand(config.device.adbPath, ['devices'])
  const devices = stdout.split(/\r?\n/).slice(1)
    .map((line) => line.trim().split(/\s+/))
    .filter(([serial, state]) => serial && state === 'device')
    .map(([serial]) => serial)
  const serial = config.device.serial || (devices.length === 1 ? devices[0] : '')
  if (!serial) throw new Error(devices.length ? `发现多个 Android 设备：${devices.join(', ')}` : '没有发现 Android 真机')
  if (!devices.includes(serial)) throw new Error(`设备 ${serial} 当前没有处于 device 状态`)
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
  candidates.sort((a, b) => b.mtimeMs - a.mtimeMs)
  if (!candidates.length) throw new Error(`没有找到 APK：${config.app.apkDir}`)
  return candidates[0].fullPath
}

async function appiumAvailable() {
  try { return (await fetch(`${config.appium.serverUrl}/status`)).ok } catch { return false }
}

async function waitFor(label, predicate, timeoutMs = scenario.timeoutMs) {
  const deadline = Date.now() + timeoutMs
  let lastError
  while (Date.now() < deadline) {
    try {
      const value = await predicate()
      if (value) return value
    } catch (error) { lastError = error }
    await new Promise((resolve) => setTimeout(resolve, 350))
  }
  throw new Error(`${label} 超时${lastError ? `：${lastError.message}` : ''}`)
}

async function ensureAppium() {
  if (await appiumAvailable()) return null
  const child = spawn(config.appium.command, [
    '--address', config.appium.host,
    '--port', String(config.appium.port),
    '--base-path', '/',
    '--allow-insecure', config.appium.allowInsecure.join(','),
  ], { shell: true, windowsHide: true, env: { ...process.env, JAVA_HOME: config.appium.javaHome } })
  await waitFor('Appium 服务启动', appiumAvailable, 20_000).catch(async (error) => {
    await fs.writeFile(path.join(reportDir, 'appium-startup.log'), error.message, 'utf8')
    child.kill()
    throw error
  })
  return child
}

async function capture(client, name) {
  try {
    await fs.writeFile(path.join(reportDir, `${name}.png`), Buffer.from(await client.screenshot(), 'base64'))
    result.evidence.push(`${name}.png`)
  } catch (error) { result.evidence.push(`${name}.png（采集失败：${error.message}）`) }
  try {
    await fs.writeFile(path.join(reportDir, `${name}.xml`), await client.source(), 'utf8')
    result.evidence.push(`${name}.xml`)
  } catch (error) { result.evidence.push(`${name}.xml（采集失败：${error.message}）`) }
}

async function findOptional(client, using, value) {
  try {
    const node = await client.find(using, value)
    return node.elementId || node.ELEMENT
  } catch { return null }
}

async function findText(client, text) {
  return findOptional(client, 'xpath', `//*[contains(@text,"${text}")]`)
}

function normalizeRect(rect) {
  if (!rect) return null
  return {
    ...rect,
    left: rect.left ?? rect.x,
    top: rect.top ?? rect.y,
    right: rect.right ?? ((rect.x ?? 0) + (rect.width ?? 0)),
    bottom: rect.bottom ?? ((rect.y ?? 0) + (rect.height ?? 0)),
  }
}

async function tapText(client, text) {
  const id = await findText(client, text)
  if (id) {
    await client.click(id).catch(async () => {
      const rect = await client.rect(id)
      await adb(['shell', 'input', 'tap', String(Math.round(rect.x + rect.width / 2)), String(Math.round(rect.y + rect.height / 2))])
    })
    return
  }
  const resourceFallbacks = {
    岗位招聘: 'home-assistant-jobs',
    联系客服: 'home-assistant-service',
  }
  const resourceId = resourceFallbacks[text]
  if (resourceId) {
    await tapResourceFromUiTree(client, resourceId, `点击 ${text}`)
    return
  }
  await waitFor(`点击 ${text}`, () => findText(client, text))
}

async function tapResourceFromUiTree(client, resourceId, label = resourceId) {
  const source = await waitFor(label, async () => {
    const current = await client.source()
    return boundsForResource(current, resourceId) ? current : null
  })
  const rect = boundsForResource(source, resourceId)
  if (!rect || rect.width <= 0 || rect.height <= 0) throw new Error(`UI 树没有返回 ${resourceId} 的有效边界`)
  await adb(['shell', 'input', 'tap', String(Math.round(rect.left + rect.width / 2)), String(Math.round(rect.top + rect.height / 2))])
}

async function rectFor(client, selectors) {
  for (const selector of selectors) {
    const id = selector.using === 'id'
      ? await findOptional(client, 'id', selector.value)
      : await findOptional(client, 'xpath', selector.value)
    if (!id) continue
    const rect = normalizeRect(await client.rect(id).catch(() => null))
    if (rect && rect.width > 0 && rect.height > 0) return rect
  }
  return null
}

function boundsForResource(source, resourceId) {
  const escaped = resourceId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const matches = [...source.matchAll(new RegExp(`resource-id="${escaped}"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`, 'g'))]
  const match = matches.at(-1)
  if (!match) return null
  const [, left, top, right, bottom] = match.map(Number)
  return { left, top, right, bottom, x: left, y: top, width: right - left, height: bottom - top }
}

async function bottomNavRect(client, size) {
  const source = await client.source()
  const fromSource = boundsForResource(source, 'nav-home')
  if (fromSource) return fromSource
  const direct = await rectFor(client, [
    { using: 'id', value: 'app-bottom-nav' },
    { using: 'id', value: 'nav-home' },
  ])
  if (direct) return direct
  const nodes = await client.findAll('class name', 'android.widget.TextView').catch(() => [])
  const candidates = []
  for (const node of nodes) {
    const id = node.elementId || node.ELEMENT
    const rect = normalizeRect(await client.rect(id).catch(() => null))
    if (rect && rect.top > size.height * 0.82 && rect.width > 80 && rect.height > 24) candidates.push(rect)
  }
  candidates.sort((a, b) => a.left - b.left)
  if (candidates.length >= 3) {
    const first = candidates[0]
    const last = candidates[candidates.length - 1]
    return { left: first.left, top: Math.min(...candidates.map((item) => item.top)), width: last.right - first.left, height: Math.max(...candidates.map((item) => item.bottom)) - Math.min(...candidates.map((item) => item.top)), right: last.right, bottom: Math.max(...candidates.map((item) => item.bottom)) }
  }
  return null
}

async function screenSize() {
  const { stdout } = await adb(['shell', 'wm', 'size'])
  const match = stdout.match(/(?:Physical|Override) size:\s*(\d+)x(\d+)/i)
  if (!match) return { width: 1080, height: 2400 }
  return { width: Number(match[1]), height: Number(match[2]) }
}

async function statusBarBottom() {
  const { stdout } = await adb(['shell', 'dumpsys', 'window', 'windows'], true)
  const matches = [...stdout.matchAll(/StatusBar[^\n]*?mFrame=\[\d+,(\d+)\]\[\d+,([0-9]+)\]/g)]
  return matches.length ? Number(matches[matches.length - 1][2]) : 72
}

async function verifyLayout(client, label, titleText, size, before = null) {
  const nav = await rectFor(client, [
    { using: 'id', value: 'app-top-nav' },
    { using: 'xpath', value: `//*[contains(@text,"${titleText}")]` },
  ])
  if (!nav) throw new Error(`${label} 未找到顶部导航`)
  const title = await findText(client, titleText)
  const titleRect = title ? normalizeRect(await client.rect(title).catch(() => null)) : null
  const safeTop = await statusBarBottom()
  if (titleRect && titleRect.top < safeTop) throw new Error(`${label} 标题进入状态栏/刘海区域：top=${titleRect.top}, safeTop=${safeTop}`)

  const bottom = await bottomNavRect(client, size)
  if (bottom && bottom.bottom > size.height) throw new Error(`${label} 底部导航超出屏幕：bottom=${bottom.bottom}, height=${size.height}`)
  if (before && Math.abs(nav.top - before.nav.top) > 6) throw new Error(`${label} 顶部导航随内容移动：${before.nav.top} -> ${nav.top}`)
  if (before && bottom && before.bottom && Math.abs(bottom.top - before.bottom.top) > 6) throw new Error(`${label} 底部导航随内容移动：${before.bottom.top} -> ${bottom.top}`)
  return { nav, bottom }
}

async function swipeMiddle(size) {
  await adb(['shell', 'input', 'swipe', String(Math.round(size.width / 2)), String(Math.round(size.height * 0.78)), String(Math.round(size.width / 2)), String(Math.round(size.height * 0.28)), '500'])
  await new Promise((resolve) => setTimeout(resolve, 700))
}

async function normalizeHome(client) {
  const currentSource = await client.source()
  const currentPage = activePage(currentSource)
  if (currentPage && currentPage !== 'home') {
    await tapBottom(client, 0).catch(() => {})
    await waitFor('首页', async () => activePage(await client.source()) === 'home').catch(() => {})
  }
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const source = await client.source()
    if (activePage(source) === 'home') {
      await waitFor('首页内容加载', async () => {
        const appiumSource = await client.source()
        return /开始测评|岗位招聘|联系客服|home-assistant-jobs|home-assistant-service/.test(appiumSource)
      })
      return
    }
    await adb(['shell', 'input', 'keyevent', '4'], true)
    await new Promise((resolve) => setTimeout(resolve, 600))
  }
  await waitFor('首页', async () => activePage(await client.source()) === 'home')
}

function activePage(source) {
  const matches = [...source.matchAll(/text="pages\/([^"\[]+)\[\d+\]"/g)]
  return matches.at(-1)?.[1] || ''
}

async function tapBottom(client, index) {
  const ids = ['nav-home', 'nav-center', 'nav-profile']
  const source = await client.source()
  let rect = boundsForResource(source, ids[index])
  const id = rect ? null : await findOptional(client, 'id', ids[index])
  rect = rect || (id ? normalizeRect(await client.rect(id)) : null)
  if (!rect) {
    const size = await screenSize()
    const nodes = await client.findAll('class name', 'android.widget.TextView').catch(() => [])
    const candidates = []
    for (const node of nodes) {
      const nodeId = node.elementId || node.ELEMENT
      const nodeRect = normalizeRect(await client.rect(nodeId).catch(() => null))
      if (nodeRect && nodeRect.top > size.height * 0.82 && nodeRect.width > 80 && nodeRect.height > 24) candidates.push(nodeRect)
    }
    candidates.sort((a, b) => a.left - b.left)
    rect = candidates[index]
  }
  if (!rect) throw new Error(`底部导航入口 ${index} 未找到`)
  await adb(['shell', 'input', 'tap', String(Math.round(rect.x + rect.width / 2)), String(Math.round(rect.y + rect.height / 2))])
}

async function step(number, name, action) {
  const item = { number, name, status: 'running' }
  result.steps.push(item)
  try { await action(); item.status = 'passed' } catch (error) { item.status = 'failed'; item.error = error.message; throw error }
}

async function main() {
  await fs.mkdir(reportDir, { recursive: true })
  result.device = { serial: await findDevice() }
  result.apk = await findApk()
  await launchCleanAppTask(adb, config.app)
  const size = await screenSize()
  const appiumProcess = await ensureAppium()
  const client = new WebDriverClient(config.appium.serverUrl)
  try {
    await client.createSession({ alwaysMatch: {
      platformName: 'Android',
      'appium:automationName': 'UiAutomator2',
      'appium:deviceName': result.device.serial,
      'appium:udid': result.device.serial,
      'appium:appPackage': config.app.packageName,
      'appium:appActivity': config.app.activity,
      'appium:noReset': true,
      'appium:fullReset': false,
      'appium:newCommandTimeout': 180,
      'appium:chromedriverAutodownload': true,
    } })
    await normalizeHome(client)

    await step(1, '首页底部导航安全区', async () => {
      const bottom = await bottomNavRect(client, size)
      if (!bottom) throw new Error('首页未找到底部导航')
      if (bottom.bottom > size.height) throw new Error(`首页底部导航超出屏幕：bottom=${bottom.bottom}, height=${size.height}`)
      await capture(client, '01-home')
    })

    await step(2, '岗位招聘导航固定和中间滚动', async () => {
      await tapText(client, '岗位招聘')
      await waitFor('岗位页面', async () => /岗位招聘|查看详情|暂无匹配岗位|正在加载岗位列表/.test(await client.source()))
      const before = await verifyLayout(client, '岗位招聘', '岗位招聘', size)
      await swipeMiddle(size)
      await verifyLayout(client, '岗位招聘滚动后', '岗位招聘', size, before)
      await capture(client, '02-jobs-scroll')
      await normalizeHome(client)
    })

    await step(3, 'AI 中心导航固定和中间滚动', async () => {
      await tapBottom(client, 1)
      await waitFor('AI 中心页面', async () => /你好，我是小技|输入你的问题|知识库查询中/.test(await client.source()))
      const before = await verifyLayout(client, 'AI 中心', '小技', size)
      await swipeMiddle(size)
      await verifyLayout(client, 'AI 中心滚动后', '小技', size, before)
      await capture(client, '03-center-scroll')
      await normalizeHome(client)
    })

    await step(4, '客服中心导航固定和底部导航', async () => {
      await tapText(client, '联系客服')
      await waitFor('客服页面', async () => /客服中心|我的客服|欢迎咨询|请输入消息/.test(await client.source()))
      const serviceSource = await client.source()
      const serviceTitle = serviceSource.includes('客服中心') ? '客服中心' : '我的客服'
      const before = await verifyLayout(client, '客服中心', serviceTitle, size)
      await swipeMiddle(size)
      await verifyLayout(client, '客服中心滚动后', serviceTitle, size, before)
      await capture(client, '04-service-scroll')
      await normalizeHome(client)
    })

    await step(5, '我的页面底部导航安全区', async () => {
      await tapBottom(client, 2)
      await waitFor('我的页面', async () => /绑定组织|练习记录|联系客服|关于小技/.test(await client.source()))
      // 发行包的 WebView UI 树不一定暴露容器节点，沿用统一的 ADB/UI 树兜底定位。
      const bottom = await bottomNavRect(client, size)
      if (!bottom || bottom.bottom > size.height) throw new Error('我的页面底部导航不在安全区域内')
      await capture(client, '05-profile')
    })

    await step(6, '练习记录和自测记录入口保持顶部导航', async () => {
      const practice = await findText(client, '练习记录')
      const selfTest = await findText(client, '自测记录')
      if (!practice && !selfTest) {
        result.skipped.push('当前账号没有可用的练习记录/自测记录入口')
        return
      }
      await tapText(client, practice ? '练习记录' : '自测记录')
      await waitFor('记录页面', async () => /练习记录|自测记录|暂无练习记录|暂无自测记录/.test(await client.source()))
      const title = practice ? '练习记录' : '自测记录'
      const before = await verifyLayout(client, '记录页面', title, size)
      await swipeMiddle(size)
      await verifyLayout(client, '记录页面滚动后', title, size, before)
      await capture(client, '06-record-scroll')
    })

    result.status = 'passed'
  } finally {
    await client.deleteSession()
    if (appiumProcess) {
      if (process.platform === 'win32' && appiumProcess.pid) await runCommand('taskkill', ['/pid', String(appiumProcess.pid), '/t', '/f'], true)
      else appiumProcess.kill()
    }
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
