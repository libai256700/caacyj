import fs from 'node:fs/promises'
import path from 'node:path'
import { spawn, execFile } from 'node:child_process'
import { promisify } from 'node:util'
import config from '../config.mjs'
import { launchCleanAppTask } from './lib/app-task.mjs'

const execFileAsync = promisify(execFile)
const startedAt = new Date()
const runId = startedAt.toISOString().replace(/[:.]/g, '-')
const reportDir = path.join(config.test.reportDir, runId)
const result = {
  scenarioId: config.test.id,
  status: 'running',
  startedAt: startedAt.toISOString(),
  device: null,
  apk: null,
  steps: [],
  evidence: [],
}

class ManualAuthorizationRequired extends Error {
  constructor() {
    super('运营商授权页已出现，等待人工确认；config.mjs 中 autoConfirmAuthorization 默认为 false')
    this.name = 'ManualAuthorizationRequired'
  }
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
    return this.sessionId
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

  contexts() { return this.command('/contexts') }
  context(name) { return this.command('/context', 'POST', { name }) }
  source() { return this.command('/source') }
  screenshot() { return this.command('/screenshot') }
  find(using, value) { return this.command('/element', 'POST', { using, value }) }
  findAll(using, value) { return this.command('/elements', 'POST', { using, value }) }
  click(elementId) { return this.command(`/element/${elementId}/click`, 'POST', {}) }
  rect(elementId) { return this.command(`/element/${elementId}/rect`) }
  attribute(elementId, name) { return this.command(`/element/${elementId}/attribute/${name}`) }
  text(elementId) { return this.command(`/element/${elementId}/text`) }
}

function log(message) {
  console.log(`[AUTH-002] ${message}`)
}

function redact(value) {
  return String(value)
    .replace(/(access[_-]?token|openid|auth[_-]?token|secret|password)["'\s:=]+[^,\s}\]]+/gi, '$1=<redacted>')
    .replace(/\b\d{11}\b/g, '<phone-redacted>')
}

async function writeJson(filename, value) {
  await fs.writeFile(path.join(reportDir, filename), `${JSON.stringify(value, null, 2)}\n`, 'utf8')
}

async function runCommand(command, args, allowFailure = false) {
  try {
    const { stdout, stderr } = await execFileAsync(command, args, { windowsHide: true, maxBuffer: 8 * 1024 * 1024 })
    return { stdout: stdout.toString(), stderr: stderr.toString() }
  } catch (error) {
    if (allowFailure) return { stdout: error.stdout?.toString() || '', stderr: error.stderr?.toString() || error.message }
    throw error
  }
}

async function adb(args, allowFailure = false) {
  const prefix = result.device?.serial ? ['-s', result.device.serial] : []
  return runCommand(config.device.adbPath, [...prefix, ...args], allowFailure)
}

async function findDevice() {
  const { stdout } = await runCommand(config.device.adbPath, ['devices'], false)
  const devices = stdout.split(/\r?\n/)
    .slice(1)
    .map((line) => line.trim().split(/\s+/))
    .filter(([serial, state]) => serial && state === 'device')
    .map(([serial]) => serial)
  const serial = config.device.serial || (devices.length === 1 ? devices[0] : '')
  if (!serial) {
    if (!devices.length) throw new Error('没有发现 Android 真机。请先完成 ADB 配对/连接，再运行此脚本。')
    throw new Error(`发现多个 Android 设备（${devices.join(', ')}），请在 config.mjs 中填写 device.serial。`)
  }
  if (!devices.includes(serial)) throw new Error(`配置的设备 ${serial} 当前没有处于 device 状态。`)
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

async function waitFor(label, predicate, timeoutMs = config.test.timeoutMs) {
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
  if (!config.appium.autoStart) throw new Error('Appium 服务未启动，且 config.mjs 禁止自动启动。')

  log('Appium 未运行，正在启动本地服务')
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
    throw new Error(`${error.message}；详见 appium-startup.log`)
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
  } catch (error) {
    result.evidence.push(`${safeName}.xml（采集失败：${error.message}）`)
  }
}

async function appendLogcat() {
  if (!result.device) {
    await fs.writeFile(
      path.join(reportDir, 'logcat-filtered.txt'),
      '未采集 logcat：执行开始前没有发现处于 device 状态的 Android 真机。\n',
      'utf8',
    )
    result.evidence.push('logcat-filtered.txt')
    return
  }
  const { stdout, stderr } = await adb(['logcat', '-d', '-v', 'threadtime'], true)
  const filtered = `${stdout}\n${stderr}`
    .split(/\r?\n/)
    .filter((line) => /univerify|yj-univerify|GeTui|OAuth|PandoraEntry|AndroidRuntime|FATAL EXCEPTION|JSONException|System\.err|chromium|WebView/i.test(line))
    .map(redact)
    .join('\n')
  await fs.writeFile(path.join(reportDir, 'logcat-filtered.txt'), `${filtered}\n`, 'utf8')
  result.evidence.push('logcat-filtered.txt')
}

async function findWebviewContext(client) {
  const contexts = await client.contexts()
  const packageName = config.app.packageName.toLowerCase()
  return contexts.find((context) => (
    /^WEBVIEW/i.test(context) && context.toLowerCase().includes(packageName)
  )) || null
}

async function getScreenSize() {
  const { stdout } = await adb(['shell', 'wm', 'size'])
  const matches = [...stdout.matchAll(/(?:Physical|Override) size:\s*(\d+)x(\d+)/gi)]
  if (!matches.length) throw new Error(`无法读取设备屏幕尺寸：${stdout.trim()}`)
  const [, width, height] = matches[matches.length - 1]
  return { width: Number(width), height: Number(height) }
}

async function nativeTap(point) {
  const size = await getScreenSize()
  const { referenceWidth, referenceHeight } = config.nativeCoordinates
  const x = Math.round(point.x * size.width / referenceWidth)
  const y = Math.round(point.y * size.height / referenceHeight)
  await adb(['shell', 'input', 'tap', String(x), String(y)])
}

async function currentActivity() {
  const { stdout } = await adb(['shell', 'dumpsys', 'activity', 'activities'], true)
  return stdout
}

async function findElement(client, using, value) {
  const response = await client.find(using, value)
  return response.elementId || response['ELEMENT']
}

async function findOptionalElement(client, using, value) {
  try {
    return await findElement(client, using, value)
  } catch {
    return null
  }
}

async function findLastElement(client, using, value) {
  const response = await client.findAll(using, value)
  const elements = response.map((element) => element.elementId || element.ELEMENT).filter(Boolean)
  return elements.at(-1) || null
}

async function tapElementCenter(client, elementId) {
  const rect = await client.rect(elementId)
  if (!rect || rect.width <= 0 || rect.height <= 0) {
    throw new Error(`元素没有有效边界：${elementId}`)
  }
  const x = Math.round(rect.x + rect.width / 2)
  const y = Math.round(rect.y + rect.height / 2)
  await adb(['shell', 'input', 'tap', String(x), String(y)])
}

async function assertLoginSurface(client) {
  const webview = await waitFor('目标应用 WebView 上下文', () => findWebviewContext(client), 5_000).catch(() => null)
  if (webview) {
    await client.context(webview)
    await waitFor('登录页', () => findOptionalElement(client, 'css selector', config.selectors.loginPage))
    await waitFor('学员角色', () => findOptionalElement(client, 'css selector', config.selectors.studentRole))
    await waitFor('一键登录面板', () => findOptionalElement(client, 'css selector', config.selectors.oneClickPanel))
    const button = await waitFor('一键登录按钮', () => findOptionalElement(client, 'css selector', config.selectors.oneClickButton))
    const agreement = await waitFor('用户协议区域', () => findOptionalElement(client, 'css selector', config.selectors.agreement))
    return { mode: 'webview', button, agreement }
  }

  // Release APKs may expose only the WebView container to UiAutomator2. The
  // accessible text is still available in the native UI tree, so locate the
  // source-defined controls there and derive the tap point from their bounds.
  await client.context('NATIVE_APP')
  await waitFor('登录页原生容器', async () => {
    const source = await client.source()
    return source.includes(`package="${config.app.packageName}"`) && source.includes('android.webkit.WebView')
  }, config.test.timeoutMs)
  const agreement = await waitFor(
    '用户协议区域（原生 UI 树）',
    () => findOptionalElement(client, 'xpath', config.nativeSelectors.agreement),
  )
  const button = await waitFor(
    '一键登录按钮（原生 UI 树）',
    // The panel title and the button share the same text in the WebView's
    // accessibility tree; the button is the last matching node.
    () => findLastElement(client, 'xpath', config.nativeSelectors.oneClickButton),
  )
  return { mode: 'native', button, agreement }
}

async function dismissNativePrivacy(client) {
  await client.context('NATIVE_APP')
  const button = await findOptionalElement(client, 'id', config.nativePrivacyButtonId)
  if (button) {
    await client.click(button)
    return true
  }
  const source = await client.source()
  if (source.includes('btn_custom_privacy_sure')) {
    await nativeTap(config.nativeCoordinates.privacyButton)
    return true
  }
  return false
}

async function waitForNativeAuthorization(client) {
  await client.context('NATIVE_APP')
  return waitFor('运营商授权页', async () => {
    const source = await client.source()
    return config.nativeAuthorizationTexts.some((text) => source.includes(text)) ? source : null
  })
}

async function confirmNativeAuthorization(client) {
  const selector = `//*[contains(@text,"${config.nativeAuthorizationTexts[0]}") or contains(@content-desc,"${config.nativeAuthorizationTexts[0]}")]`
  const element = await waitFor('运营商授权按钮', () => findOptionalElement(client, 'xpath', selector), 5_000).catch(() => null)
  if (element) {
    await client.click(element)
  } else {
    await nativeTap(config.nativeCoordinates.authorizationButton)
  }
}

async function waitForNativeHome(client) {
  await client.context('NATIVE_APP')
  await waitFor('登录完成并回到首页 Activity', async () => {
    const activity = await currentActivity()
    const resumedLine = activity.split(/\r?\n/).find((line) => /topResumedActivity|ResumedActivity/.test(line)) || ''
    return resumedLine.includes(`${config.app.packageName}/${config.app.homeActivity}`)
  })
  // UiAutomator exposes the WebView's accessible text even when the release
  // build does not expose a WEBVIEW context. Use stable business copy as the
  // primary assertion; the screenshot remains supplementary evidence.
  await waitFor('首页内容实际渲染', async () => {
    const source = await client.source()
    return /开始测评|题库训练|岗位招聘|首页/.test(source)
  })
}

async function runMainFlow() {
  await fs.mkdir(reportDir, { recursive: true })
  result.device = await findDevice()
  result.apk = await findApk()
  log(`设备：${result.device}`)
  log(`APK：${result.apk}`)
  await launchCleanAppTask(adb, config.app)
  const appiumProcess = await ensureAppium()
  const client = new WebDriverClient(config.appium.serverUrl)

  try {
    await client.createSession({
      alwaysMatch: {
        platformName: 'Android',
        'appium:automationName': 'UiAutomator2',
        'appium:deviceName': result.device,
        'appium:udid': result.device,
        'appium:app': result.apk,
        'appium:appPackage': config.app.packageName,
        'appium:appActivity': config.app.activity,
        'appium:autoGrantPermissions': true,
        'appium:noReset': false,
        'appium:fullReset': false,
        'appium:newCommandTimeout': 180,
        'appium:chromedriverAutodownload': true,
      },
    })
    result.steps.push({ id: 1, name: '启动应用', status: 'passed' })
    const privacyDismissed = await dismissNativePrivacy(client)
    if (privacyDismissed) await waitFor('隐私弹窗关闭', async () => {
      const activity = await currentActivity()
      return activity.includes(config.app.packageName)
    })
    result.steps.push({ id: 2, name: '处理首次隐私弹窗', status: 'passed', detail: privacyDismissed ? '已点击同意' : '未出现' })
    const loginSurface = await assertLoginSurface(client)
    const { mode, button, agreement } = loginSurface
    result.loginSurface = mode
    result.steps.push({ id: 3, name: '确认学员角色、一键登录入口和协议前置', status: 'passed' })
    await captureEvidence(client, '01-login-page-before-auth')

    if (mode === 'webview') {
      const activeAgreement = await findOptionalElement(client, 'css selector', config.selectors.agreementChecked)
      if (!activeAgreement) {
        await client.click(agreement)
        await waitFor('协议勾选状态', () => findOptionalElement(client, 'css selector', config.selectors.agreementChecked))
      }
    } else {
      await tapElementCenter(client, agreement)
    }
    result.steps.push({ id: 4, name: '同意用户协议和隐私政策', status: 'passed' })
    if (mode === 'webview') await client.click(button)
    else await tapElementCenter(client, button)
    result.steps.push({ id: 5, name: '点击本机号码一键登录', status: 'passed' })
    await waitForNativeAuthorization(client)
    await captureEvidence(client, '02-carrier-authorization')
    result.steps.push({ id: 6, name: '运营商授权页出现', status: 'passed' })

    if (!config.test.autoConfirmAuthorization) throw new ManualAuthorizationRequired()
    await confirmNativeAuthorization(client)
    result.steps.push({ id: 7, name: '确认运营商授权', status: 'passed' })
    await captureEvidence(client, '03-carrier-confirm-clicked')

    if (mode === 'webview') {
      const webview = await waitFor('授权后返回目标 WebView', () => findWebviewContext(client))
      await client.context(webview)
      await waitFor('登录完成并进入首页', () => findOptionalElement(client, 'css selector', config.selectors.homePage))
    } else {
      await waitForNativeHome(client)
    }
    await captureEvidence(client, '04-home-after-login')
    result.steps.push({ id: 8, name: '后端校验完成并进入首页', status: 'passed' })
    result.status = 'passed'
  } finally {
    await client.deleteSession()
    await stopProcessTree(appiumProcess)
  }
}

try {
  await runMainFlow()
} catch (error) {
  result.status = error instanceof ManualAuthorizationRequired ? 'blocked' : 'failed'
  result.error = error.message
  log(error.message)
  if (!(error instanceof ManualAuthorizationRequired)) process.exitCode = 1
} finally {
  await appendLogcat().catch(() => {})
  result.finishedAt = new Date().toISOString()
  await fs.mkdir(reportDir, { recursive: true })
  await writeJson('result.json', result)
  log(`结果：${result.status}`)
  log(`报告：${reportDir}`)
}
