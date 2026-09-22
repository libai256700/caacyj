import fs from 'node:fs/promises'
import path from 'node:path'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import config from '../config.mjs'
import { launchCleanAppTask } from './lib/app-task.mjs'
import { activePageMatches } from './lib/active-page.mjs'

const execFileAsync = promisify(execFile)
const scenario = config.scenarios.core
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
    })
    const payload = await response.json().catch(() => ({}))
    const error = payload?.value?.error || payload?.value?.message
    if (!response.ok || error) {
      throw new Error(`${method} ${endpoint} failed: ${error || response.statusText}`)
    }
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

  async command(endpoint, method = 'GET', body) {
    if (!this.sessionId) throw new Error('Appium session 尚未建立')
    return this.request(`/session/${this.sessionId}${endpoint}`, method, body)
  }

  source() { return this.command('/source') }
  screenshot() { return this.command('/screenshot') }
  find(using, value) { return this.command('/element', 'POST', { using, value }) }
  findAll(using, value) { return this.command('/elements', 'POST', { using, value }) }
  rect(elementId) { return this.command(`/element/${elementId}/rect`) }
  click(elementId) { return this.command(`/element/${elementId}/click`, 'POST', {}) }
  setValue(elementId, text) { return this.command(`/element/${elementId}/value`, 'POST', { text, value: [...text] }) }
}

function log(message) {
  console.log(`[${scenario.id}] ${message}`)
}

function redact(value) {
  return String(value)
    .replace(/(access[_-]?token|openid|auth[_-]?token|secret|password)["'\s:=]+[^,\s}\]]+/gi, '$1=<redacted>')
    .replace(/\b\d{11}\b/g, '<phone-redacted>')
}

async function runCommand(command, args, allowFailure = false) {
  try {
    const { stdout, stderr } = await execFileAsync(command, args, {
      windowsHide: true,
      maxBuffer: 8 * 1024 * 1024,
    })
    return { stdout: stdout.toString(), stderr: stderr.toString() }
  } catch (error) {
    if (allowFailure) {
      return { stdout: error.stdout?.toString() || '', stderr: error.stderr?.toString() || error.message }
    }
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
    const stat = await fs.stat(fullPath)
    candidates.push({ fullPath, mtimeMs: stat.mtimeMs })
  }
  candidates.sort((a, b) => b.mtimeMs - a.mtimeMs)
  if (!candidates.length) throw new Error(`没有找到 APK：${config.app.apkDir}`)
  return candidates[0].fullPath
}

async function waitFor(label, predicate, timeoutMs = scenario.timeoutMs) {
  const deadline = Date.now() + timeoutMs
  let lastError
  while (Date.now() < deadline) {
    try {
      const value = await predicate()
      if (value) return value
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, 350))
  }
  throw new Error(`${label} 超时${lastError ? `：${lastError.message}` : ''}`)
}

async function appiumAvailable() {
  try {
    const response = await fetch(`${config.appium.serverUrl}/status`)
    return response.ok
  } catch {
    return false
  }
}

async function ensureAppium() {
  if (await appiumAvailable()) return null
  const child = spawn(config.appium.command, [
    '--address', config.appium.host,
    '--port', String(config.appium.port),
    '--base-path', '/',
    '--allow-insecure', config.appium.allowInsecure.join(','),
  ], {
    shell: true,
    windowsHide: true,
    env: { ...process.env, JAVA_HOME: config.appium.javaHome },
  })
  const appiumLog = []
  child.stdout?.on('data', (chunk) => appiumLog.push(redact(chunk.toString())))
  child.stderr?.on('data', (chunk) => appiumLog.push(redact(chunk.toString())))
  try {
    await waitFor('Appium 服务启动', appiumAvailable, 20_000)
  } catch (error) {
    await fs.writeFile(path.join(reportDir, 'appium-startup.log'), appiumLog.join(''), 'utf8')
    child.kill()
    throw error
  }
  return child
}

async function stopProcessTree(child) {
  if (!child) return
  if (process.platform === 'win32' && child.pid) {
    await runCommand('taskkill', ['/pid', String(child.pid), '/t', '/f'], true)
  } else {
    child.kill()
  }
}

async function captureEvidence(client, name) {
  const safeName = name.replace(/[^a-z0-9-_]/gi, '-')
  try {
    const source = await client.source()
    await fs.writeFile(path.join(reportDir, `${safeName}.xml`), redact(source), 'utf8')
    result.evidence.push(`${safeName}.xml`)
    const screenshot = await client.screenshot()
    await fs.writeFile(path.join(reportDir, `${safeName}.png`), Buffer.from(screenshot, 'base64'))
    result.evidence.push(`${safeName}.png`)
  } catch (error) {
    result.evidence.push(`${safeName}.xml（采集失败：${error.message}）`)
  }
}

async function appendLogcat() {
  const { stdout, stderr } = await adb(['logcat', '-d', '-v', 'threadtime'], true)
  const filtered = `${stdout}\n${stderr}`.split(/\r?\n/)
    .filter((line) => /customerAuth|practice|jobs|service|AndroidRuntime|FATAL EXCEPTION|chromium|WebView/i.test(line))
    .map(redact).join('\n')
  await fs.writeFile(path.join(reportDir, 'logcat-filtered.txt'), `${filtered}\n`, 'utf8')
  result.evidence.push('logcat-filtered.txt')
}

async function findElement(client, using, value) {
  const response = await client.find(using, value)
  return response.elementId || response.ELEMENT
}

async function findOptionalElement(client, using, value) {
  try {
    return await findElement(client, using, value)
  } catch {
    return null
  }
}

async function tapElement(client, elementId) {
  try {
    await client.click(elementId)
    return
  } catch {
    const rect = await client.rect(elementId)
    await adb(['shell', 'input', 'tap', String(Math.round(rect.x + rect.width / 2)), String(Math.round(rect.y + rect.height / 2))])
  }
}

async function tapElementByBounds(client, elementId) {
  const rect = await client.rect(elementId)
  if (!rect || rect.width <= 0 || rect.height <= 0) throw new Error('元素没有有效边界')
  await adb(['shell', 'input', 'tap', String(Math.round(rect.x + rect.width / 2)), String(Math.round(rect.y + rect.height / 2))])
}

async function tapText(client, text, label = text) {
  const element = await waitFor(label, () => findOptionalElement(client, 'xpath', `//*[contains(@text,"${text}")]`))
  await tapElement(client, element)
}

async function tapExactText(client, text, label = text) {
  const element = await waitFor(label, () => findOptionalElement(client, 'xpath', `//*[@text="${text}"]`))
  await tapElement(client, element)
}

async function tapLastText(client, text, label = text) {
  const element = await waitFor(label, async () => {
    const elements = await client.findAll('xpath', `//*[contains(@text,"${text}")]`)
    return elements.length ? (elements[elements.length - 1].elementId || elements[elements.length - 1].ELEMENT) : null
  })
  await tapElement(client, element)
}

async function setValueById(client, id, value) {
  const element = await waitFor(`输入框 ${id}`, () => findOptionalElement(client, 'id', id))
  await client.setValue(element, value)
}

async function setValueByHint(client, hint, value) {
  const element = await waitFor(`输入框 ${hint}`, async () =>
    findOptionalElement(client, 'xpath', `//*[@hint="${hint}"]`)
      || findOptionalElement(client, 'xpath', '//android.widget.EditText')
      || findOptionalElement(client, '-android uiautomator', 'new UiSelector().className("android.widget.EditText")'))
  await client.setValue(element, value)
}

async function inputTextFromUiTree(client, value) {
  const source = await waitFor('客服输入节点', async () => {
    const current = await client.source()
    return /<android.widget.EditText\b[^>]*bounds="\[\d+,\d+\]\[\d+,\d+\]"/.test(current) ? current : null
  })
  const match = source.match(/<android.widget.EditText\b[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/)
  if (!match) throw new Error('UI 树没有返回客服输入节点边界')
  const [, left, top, right, bottom] = match.map(Number)
  await adb(['shell', 'input', 'tap', String(Math.round((left + right) / 2)), String(Math.round((top + bottom) / 2))])
  await adb(['shell', 'input', 'text', value.replace(/\s/g, '%s')])
  await adb(['shell', 'input', 'keyevent', '66'])
}

async function tapResourceFromUiTree(client, resourceId) {
  const source = await waitFor(`UI 树元素 ${resourceId}`, async () => {
    const current = await client.source()
    return new RegExp(`resource-id="${resourceId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"[^>]*bounds="\\[\\d+,\\d+\\]\\[\\d+,\\d+\\]"`).test(current) ? current : null
  })
  const escapedId = resourceId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = source.match(new RegExp(`resource-id="${escapedId}"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`))
  if (!match) throw new Error(`UI 树没有返回 ${resourceId} 的边界`)
  const [, left, top, right, bottom] = match.map(Number)
  await adb(['shell', 'input', 'tap', String(Math.round((left + right) / 2)), String(Math.round((top + bottom) / 2))])
}

async function waitForSource(client, label, pattern) {
  return waitFor(label, async () => {
    const source = await client.source()
    return activePageMatches(source, pattern) ? source : null
  })
}

function activeRoute(source) {
  const pageRoutes = [...source.matchAll(/text="(pages\/[^"]+)\[\d+\]"/g)].map((match) => match[1])
  const pageRoute = {
    'pages/home': 'home-page',
    'pages/center': 'center-page',
    'pages/profile': 'profile-page',
    'pages/jobs': 'jobs-page',
    'pages/practice/exam-topics': 'practice-topics-page',
    'pages/practice/exam-assessment': 'practice-assessment-page',
    'pages/practice/answer': 'practice-answer-page',
  }[pageRoutes.at(-1)]
  if (pageRoute) return pageRoute
  const routes = ['home-page', 'center-page', 'profile-page', 'jobs-page', 'practice-topics-page', 'practice-assessment-page', 'practice-answer-page']
  return routes.reduce((active, route) => {
    const index = source.lastIndexOf(`resource-id="${route}"`)
    return index > active.index ? { route, index } : active
  }, { route: '', index: -1 }).route
}

async function normalizeToHome(client) {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const source = await client.source()
    if (activeRoute(source) === 'home-page') return
    await adb(['shell', 'input', 'keyevent', '4'], true)
    await new Promise((resolve) => setTimeout(resolve, 600))
  }
  await waitForSource(client, '返回首页', /开始测评|逐题练习|岗位招聘/)
}

async function tapBottomNav(client, targetIndex) {
  const ids = ['nav-home', 'nav-center', 'nav-profile']
  const labels = ['首页', 'AI助手', '我的']
  const resourceId = ids[targetIndex]
  if (!resourceId) throw new Error(`未知底部导航序号：${targetIndex}`)
  const source = await client.source()
  const escapedId = resourceId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  if (new RegExp(`resource-id="${escapedId}"[^>]*bounds="\\[\\d+,\\d+\\]\\[\\d+,\\d+\\]"`).test(source)) {
    await tapResourceFromUiTree(client, resourceId)
    return
  }
  await tapExactText(client, labels[targetIndex], `底部导航 ${labels[targetIndex]}`)
}

async function pressBack() {
  await adb(['shell', 'input', 'keyevent', '4'])
}

async function restartApp(client) {
  // launchCleanAppTask also stops UiAutomator2. That is appropriate before a
  // new Appium session, but invalidates the session this scenario continues
  // to use between navigation checks.
  await adb(['shell', 'am', 'force-stop', config.app.packageName])
  await adb([
    'shell',
    'am',
    'start',
    '-f',
    '0x10008000',
    '-n',
    `${config.app.packageName}/${config.app.activity}`,
  ])
  await waitForSource(client, '应用重启后首页', /开始测评|逐题练习|岗位招聘/)
}

async function recordStep(id, name, action) {
  const step = { id, name, status: 'running' }
  result.steps.push(step)
  try {
    await action()
    step.status = 'passed'
  } catch (error) {
    step.status = 'failed'
    step.error = error.message
    throw error
  }
}

async function runMainFlow() {
  await fs.mkdir(reportDir, { recursive: true })
  result.device = { serial: await findDevice() }
  result.apk = await findApk()
  await launchCleanAppTask(adb, config.app)
  const appiumProcess = await ensureAppium()
  const client = new WebDriverClient(config.appium.serverUrl)
  try {
    await client.createSession({
      alwaysMatch: {
        platformName: 'Android',
        'appium:automationName': 'UiAutomator2',
        'appium:deviceName': result.device.serial,
        'appium:udid': result.device.serial,
        'appium:app': result.apk,
        'appium:appPackage': config.app.packageName,
        'appium:appActivity': config.app.activity,
        'appium:noReset': true,
        'appium:fullReset': false,
        'appium:newCommandTimeout': 180,
        'appium:chromedriverAutodownload': true,
      },
    })
    await normalizeToHome(client)

    await recordStep(1, '登录后首页可用', async () => {
      await waitForSource(client, '首页渲染', /开始测评|逐题练习|岗位招聘/)
      await captureEvidence(client, '01-home')
    })

    await recordStep(2, '岗位招聘主入口', async () => {
      await tapText(client, '岗位招聘')
      await waitForSource(client, '岗位页面', /岗位招聘|查看详情|暂无招聘岗位|岗位信息暂不可用|正在加载岗位列表/)
      await captureEvidence(client, '02-jobs')
      await restartApp(client)
    })

    await recordStep(3, '客服主入口', async () => {
      await tapText(client, '联系客服')
      await waitForSource(client, '客服页面', /我的客服|欢迎咨询|请输入消息/)
      await captureEvidence(client, '03-customer-service')
      await inputTextFromUiTree(client, 'auto-test-service-20260824')
      await waitForSource(client, '客服消息发送结果', /auto-test-service-20260824|发送中|消息发送失败/)
      await captureEvidence(client, '03-customer-service-sent')
      await restartApp(client)
    })

    await recordStep(4, 'AI 中心底部导航', async () => {
      await tapBottomNav(client, 1)
      await waitFor('AI 中心页面', async () => {
        const source = await client.source()
        return activeRoute(source) === 'center-page' && /你好，我是小技|输入你的问题|知识库查询中/.test(source)
      })
      await captureEvidence(client, '04-center')
    })

    await recordStep(5, 'AI 中心发送问题并验证响应', async () => {
      await inputTextFromUiTree(client, 'uav-preflight-checklist')
      const source = await client.source()
      if (/resource-id="center-send"/.test(source)) await tapResourceFromUiTree(client, 'center-send')
      else await tapText(client, '发送', 'AI 发送按钮')
      await waitForSource(client, 'AI 查询结果', /uav-preflight-checklist|知识库查询中|暂未查询到|知识库服务暂不可用/)
      await captureEvidence(client, '05-center-response')
    })

    await recordStep(6, '我的底部导航', async () => {
      await tapBottomNav(client, 2)
      await waitFor('我的页面', async () => {
        const source = await client.source()
        return activeRoute(source) === 'profile-page' && /我的|绑定组织|退出登录/.test(source)
      })
      await captureEvidence(client, '06-profile')
    })

    await recordStep(7, '关于小技弹窗', async () => {
      await tapBottomNav(client, 2)
      await waitFor('我的页面', async () => activeRoute(await client.source()) === 'profile-page')
      await tapText(client, '关于小技')
      await waitForSource(client, '关于小技弹窗', /关于小技|无人机学习与职业成长助手/)
      await captureEvidence(client, '07-about')
      await tapText(client, '知道了')
      await restartApp(client)
    })

    await recordStep(8, '返回首页底部导航', async () => {
      await tapBottomNav(client, 0)
      await waitFor('首页页面', async () => {
        const source = await client.source()
        return activeRoute(source) === 'home-page' && /开始测评|逐题练习|岗位招聘/.test(source)
      })
    })

    await recordStep(9, '逐题练习分类入口', async () => {
      await tapText(client, '逐题练习')
      await waitForSource(client, '逐题练习分类页', /逐题练习|正在加载逐题练习分类|暂无可用题目主题|逐题练习暂不可用/)
      await captureEvidence(client, '09-practice-topics')
    })

    await recordStep(10, '退出登录并验证回到登录页', async () => {
      await normalizeToHome(client)
      await tapBottomNav(client, 2)
      await waitForSource(client, '我的页面', /退出登录/)
      await tapText(client, '退出登录')
      await waitForSource(client, '退出登录确认弹窗', /确认退出当前账号并返回登录页吗|退出后，再次使用小技需要重新登录/)
      await captureEvidence(client, '10-logout-dialog')
      await tapLastText(client, '退出登录', '确认退出登录')
      await waitForSource(client, '返回登录页', /auth-login-page|一键登录|短信登录|本机号码一键登录/)
      await captureEvidence(client, '10-login-after-logout')
    })

    result.status = 'passed'
  } finally {
    await appendLogcat()
    await client.deleteSession()
    await stopProcessTree(appiumProcess)
    await fs.writeFile(path.join(reportDir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
  }
}

runMainFlow().catch(async (error) => {
  result.status = 'failed'
  result.error = error.message
  await fs.mkdir(reportDir, { recursive: true })
  await appendLogcat().catch(() => {})
  await fs.writeFile(path.join(reportDir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
  console.error(`[${scenario.id}] 结果：failed`)
  console.error(error.stack || error.message)
  process.exitCode = 1
})
