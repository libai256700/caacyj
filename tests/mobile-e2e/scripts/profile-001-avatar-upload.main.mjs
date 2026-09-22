import fs from 'node:fs/promises'
import path from 'node:path'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import config from '../config.mjs'
import { launchCleanAppTask } from './lib/app-task.mjs'
import { activePageMatches } from './lib/active-page.mjs'

const execFileAsync = promisify(execFile)
const scenario = config.scenarios.profileAvatar
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
let avatarMarkerBeforeUpload = ''
let avatarSourcesBeforeUpload = []
let uploadedAvatarSource = ''
let devToolsCommandId = 0
const cachedUiTreeTextBounds = new Map()

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

  context(name) { return this.command('/context', 'POST', { name }) }
  contexts() { return this.command('/contexts') }
  source() { return this.command('/source') }
  screenshot() { return this.command('/screenshot') }
  find(using, value) { return this.command('/element', 'POST', { using, value }) }
  findAll(using, value) { return this.command('/elements', 'POST', { using, value }) }
  rect(elementId) { return this.command(`/element/${elementId}/rect`) }
  click(elementId) { return this.command(`/element/${elementId}/click`, 'POST', {}) }
  clear(elementId) { return this.command(`/element/${elementId}/clear`, 'POST', {}) }
  execute(script, args = []) { return this.command('/execute/sync', 'POST', { script, args }) }
  setValue(elementId, value) {
    return this.command(`/element/${elementId}/value`, 'POST', { text: String(value), value: [String(value)] })
  }
}

function log(message) {
  console.log(`[${scenario.id}] ${message}`)
}

function redact(value) {
  return String(value)
    .replace(/(access[_-]?token|openid|auth[_-]?token|secret|password)["'\s:=]+[^,\s}\]]+/gi, '$1=<redacted>')
    .replace(/\b\d{11}\b/g, '<phone-redacted>')
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function imageMarkerFromResource(source, resourceId) {
  const resourcePattern = new RegExp(
    `<[^>]*\\bresource-id="${escapeRegExp(resourceId)}"[^>]*>[\\s\\S]*?<android\\.widget\\.Image\\b[^>]*\\btext="([^"]*)"`,
    'i',
  )
  return String(source).match(resourcePattern)?.[1] || ''
}

function avatarImageMarker(source, resourceId = '') {
  const scopedMarker = resourceId ? imageMarkerFromResource(source, resourceId) : ''
  if (scopedMarker) return scopedMarker

  const imageTexts = [...String(source).matchAll(/<android\.widget\.Image\b[^>]*\btext="([^"]*)"/g)]
    .map((match) => match[1])
    .filter(Boolean)
  return imageTexts.find((value) => !/^(profile-|settings-|logout$|search$|home$|assistant$)/i.test(value)) || ''
}

async function writeJson(filename, value) {
  await fs.writeFile(path.join(reportDir, filename), `${JSON.stringify(value, null, 2)}\n`, 'utf8')
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
  const prefix = result.device ? ['-s', result.device] : []
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
  const args = [
    '--address', config.appium.host,
    '--port', String(config.appium.port),
    '--base-path', '/',
    '--allow-insecure', config.appium.allowInsecure.join(','),
  ]
  const appiumEntry = config.appium.entryPath
  const child = spawn(appiumEntry ? process.execPath : config.appium.command, appiumEntry ? [appiumEntry, ...args] : args, {
    shell: !appiumEntry,
    windowsHide: true,
    env: { ...process.env, JAVA_HOME: config.appium.javaHome },
  })
  const appiumLog = []
  child.stdout?.on('data', (chunk) => appiumLog.push(redact(chunk.toString())))
  child.stderr?.on('data', (chunk) => appiumLog.push(redact(chunk.toString())))
  try {
    await waitFor('Appium 服务启动', appiumAvailable, 45_000)
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

async function findOptionalBusinessId(client, id) {
  return await findOptionalElement(client, 'id', id)
    || await findOptionalElement(client, 'xpath', `//*[@resource-id="${id}"]`)
}

async function tapElement(client, elementId) {
  try {
    await client.click(elementId)
    return
  } catch {
    const rect = await client.rect(elementId)
    if (!rect || rect.width <= 0 || rect.height <= 0) throw new Error('元素没有有效边界')
    await adb(['shell', 'input', 'tap', String(Math.round(rect.x + rect.width / 2)), String(Math.round(rect.y + rect.height / 2))])
  }
}

async function tapElementByBounds(client, elementId) {
  const rect = await client.rect(elementId)
  if (!rect || rect.width <= 0 || rect.height <= 0) throw new Error('元素没有有效边界')
  await adb(['shell', 'input', 'tap', String(Math.round(rect.x + rect.width / 2)), String(Math.round(rect.y + rect.height / 2))])
}

async function findUiTreeTextBounds(text) {
  const remotePath = '/sdcard/profile-e2e-ui-tree.xml'
  await adb(['shell', 'uiautomator', 'dump', remotePath], true)
  const { stdout } = await adb(['exec-out', 'cat', remotePath], true)
  const pattern = new RegExp(
    `<node\\b(?=[^>]*\\btext="${escapeRegExp(text)}")(?=[^>]*\\bbounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]")[^>]*>`,
  )
  const match = String(stdout).match(pattern)
  if (!match) return null
  const [, left, top, right, bottom] = match.map(Number)
  if (right <= left || bottom <= top) return null
  return { left, top, right, bottom }
}

async function findUiTreeTextContainer(text) {
  const remotePath = '/sdcard/profile-e2e-ui-tree.xml'
  await adb(['shell', 'uiautomator', 'dump', remotePath], true)
  const { stdout } = await adb(['exec-out', 'cat', remotePath], true)
  const tags = String(stdout).match(/<\/?node\b[^>]*>/g) || []
  const stack = []
  for (const tag of tags) {
    if (tag.startsWith('</node')) {
      stack.pop()
      continue
    }
    const textValue = tag.match(/\btext="([^"]*)"/)?.[1] || ''
    const boundsMatch = tag.match(/\bbounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/)
    const bounds = boundsMatch
      ? { left: Number(boundsMatch[1]), top: Number(boundsMatch[2]), right: Number(boundsMatch[3]), bottom: Number(boundsMatch[4]) }
      : null
    if (textValue === text && bounds) {
      return { textBounds: bounds, containerBounds: stack.at(-1)?.bounds || bounds }
    }
    if (!tag.endsWith('/>')) stack.push({ bounds })
  }
  return null
}

async function cacheLoginUiTreeBounds() {
  const smsLoginTabText = '短信验证码登录'
  const formTexts = ['我已阅读并同意', '登录 / 注册']
  cachedUiTreeTextBounds.clear()
  const smsLoginTabBounds = await waitFor('短信验证码登录入口', () => findUiTreeTextBounds(smsLoginTabText), 20_000)
  await tapUiTreeBounds(smsLoginTabBounds)
  await waitFor('短信登录表单原生 UI 树', async () => {
    for (const text of formTexts) {
      const bounds = await findUiTreeTextBounds(text)
      if (bounds) cachedUiTreeTextBounds.set(text, bounds)
    }
    return formTexts.every((text) => cachedUiTreeTextBounds.has(text)) ? true : null
  }, 20_000)
  log(`已缓存登录控件 UI 树边界：${[...cachedUiTreeTextBounds.keys()].join('、')}`)
}

async function nativeUiTreeSource() {
  const remotePath = '/sdcard/profile-e2e-ui-tree.xml'
  await adb(['shell', 'uiautomator', 'dump', remotePath], true)
  const { stdout } = await adb(['exec-out', 'cat', remotePath], true)
  return String(stdout)
}

function isNativeHomeSource(source) {
  return /text="pages\/home\[\d+\]"|开始测评|岗位招聘|题库训练/.test(source)
}

async function waitForHomeFromNativeUiTree() {
  await waitFor('短信登录后首页', async () => {
    const source = await nativeUiTreeSource()
    return isNativeHomeSource(source) ? source : null
  })
}

async function tapUiTreeBounds(bounds) {
  await adb([
    'shell',
    'input',
    'tap',
    String(Math.round((bounds.left + bounds.right) / 2)),
    String(Math.round((bounds.top + bounds.bottom) / 2)),
  ])
}

async function activeDevToolsTarget(routePattern, pageLabel) {
  const { stdout: pidOutput } = await adb(['shell', 'pidof', config.app.packageName])
  const processId = pidOutput.trim().split(/\s+/)[0]
  if (!processId) throw new Error('无法读取小技应用进程，不能连接 WebView DevTools')

  const { stdout: sockets } = await adb(['shell', 'cat', '/proc/net/unix'])
  const socketName = `webview_devtools_remote_${processId}`
  if (!sockets.includes(`@${socketName}`)) {
    throw new Error(`应用没有暴露 WebView DevTools socket：${socketName}`)
  }

  const port = config.devtools.localPort
  await adb(['forward', '--remove', `tcp:${port}`], true)
  await adb(['forward', `tcp:${port}`, `localabstract:${socketName}`])
  const response = await fetch(`http://127.0.0.1:${port}/json`)
  if (!response.ok) throw new Error(`读取 WebView DevTools 页面失败：HTTP ${response.status}`)
  const pages = await response.json()
  const page = pages.find((item) => item.type === 'page' && routePattern.test(item.title || ''))
  if (!page?.webSocketDebuggerUrl) throw new Error(`WebView DevTools 中没有${pageLabel}页面`)
  log(`WebView DevTools 目标：进程 ${processId}，页面 ${page.title}`)
  return { port, webSocketDebuggerUrl: page.webSocketDebuggerUrl }
}

async function evaluateDevToolsPage(expression, routePattern, pageLabel, awaitPromise = false) {
  let lastError
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    let port
    let webSocket
    try {
      const target = await activeDevToolsTarget(routePattern, pageLabel)
      port = target.port
      webSocket = new WebSocket(target.webSocketDebuggerUrl)
      await new Promise((resolve, reject) => {
        webSocket.addEventListener('open', resolve, { once: true })
        webSocket.addEventListener('error', () => reject(new Error('连接 WebView DevTools 失败')), { once: true })
      })
      log(`WebView DevTools 已连接（第 ${attempt} 次）`)
      const payload = await new Promise((resolve, reject) => {
        devToolsCommandId = devToolsCommandId >= 2_000_000_000 ? 0 : devToolsCommandId + 1
        const id = devToolsCommandId
        const timeout = setTimeout(() => reject(new Error('WebView DevTools 执行超时')), 8_000)
        const onMessage = (event) => {
          const message = JSON.parse(event.data)
          if (message.id !== id) return
          webSocket.onmessage = null
          clearTimeout(timeout)
          resolve(message)
        }
        webSocket.onmessage = onMessage
        webSocket.send(JSON.stringify({
          id,
          method: 'Runtime.evaluate',
          params: { expression, returnByValue: true, awaitPromise },
        }))
      })
      if (payload.result?.exceptionDetails) {
        throw new Error(payload.result.exceptionDetails.text || 'WebView DevTools 执行失败')
      }
      return payload.result?.result?.value
    } catch (error) {
      lastError = error
      if (attempt === 3) break
      log(`WebView DevTools 暂不可用，准备重试：${error.message}`)
      await new Promise((resolve) => setTimeout(resolve, 1_500))
    } finally {
      webSocket?.close()
      if (port) await adb(['forward', '--remove', `tcp:${port}`], true)
    }
  }
  throw lastError || new Error('WebView DevTools 执行失败')
}

async function evaluateLoginPage(expression, awaitPromise = false) {
  return evaluateDevToolsPage(expression, /^pages\/auth\/login/, '登录', awaitPromise)
}

async function readProfileImageSources(scopeSelector = '') {
  const scope = JSON.stringify(scopeSelector)
  const result = await evaluateDevToolsPage(`
    (() => {
      const root = ${scope} ? document.querySelector(${scope}) : document
      if (!root) return JSON.stringify([])
      const sources = [...root.querySelectorAll('[src]')]
        .map((element) => element.getAttribute('src') || element.src || '')
        .filter(Boolean)
      return JSON.stringify([...new Set(sources)])
    })()
  `, /^pages\/profile/, '个人中心')
  return JSON.parse(result || '[]')
}

const findNewRemoteAvatar = (sources) => sources.find((source) =>
  /^https?:\/\//i.test(source) && !avatarSourcesBeforeUpload.includes(source)
)

async function loginWithSmsThroughDevTools() {
  const phone = JSON.stringify(config.scenarios.sms.phone)
  const code = JSON.stringify(config.scenarios.sms.code)
  const inputOutcome = await evaluateLoginPage(`
    (() => {
      const inputs = [
        document.querySelector('#auth-sms-phone input'),
        document.querySelector('#auth-sms-code input'),
      ]
      if (inputs.some((input) => !input)) return JSON.stringify({ reason: '登录输入框源码节点不完整' })
      const setInput = (input, value) => {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
        if (!setter) throw new Error('浏览器未提供 input value setter')
        setter.call(input, value)
        input.dispatchEvent(new Event('input', { bubbles: true }))
        input.dispatchEvent(new Event('change', { bubbles: true }))
      }
      setInput(inputs[0], ${phone})
      setInput(inputs[1], ${code})
      return JSON.stringify({ phoneLength: inputs[0].value.length, codeLength: inputs[1].value.length })
    })()
  `)
  const inputResult = JSON.parse(inputOutcome || '{}')
  if (inputResult.phoneLength !== 11 || inputResult.codeLength !== 6) {
    throw new Error(`短信登录 DevTools 输入失败：${inputResult.reason || '输入值未生效'}`)
  }

  await evaluateLoginPage(`
    (() => {
      const agreement = document.querySelector('#auth-agreement')
      const check = document.querySelector('.login-agreement__check')
      if (!agreement || !check) return false
      if (!check.classList.contains('login-agreement__check--active')) agreement.click()
      return true
    })()
  `)
  await waitFor('短信登录协议已勾选', async () => {
    return await evaluateLoginPage('Boolean(document.querySelector(".login-agreement__check--active"))')
  }, 5_000)

  const submitted = await evaluateLoginPage(`
    (() => {
      const submit = document.querySelector('#auth-sms-submit')
      if (!submit) return false
      submit.click()
      return true
    })()
  `)
  if (!submitted) throw new Error('短信登录 DevTools 提交按钮不可用')
  log('已通过源码选择器完成短信登录输入、协议确认和提交')
}

async function agreeToLoginTerms(client) {
  try {
    const contexts = await client.contexts()
    const webViews = contexts.filter((name) => name.startsWith('WEBVIEW_'))
    for (const webView of webViews) {
      log(`检查协议 WebView：${webView}`)
      try {
        await client.context(webView)
        const agreementReady = await waitFor('协议源码节点', async () => {
          try {
            return await client.execute('return document.querySelectorAll(".login-agreement").length > 0')
          } catch {
            return null
          }
        }, 4_000).catch(() => false)
        log(`协议源码节点可用（${webView}）：${agreementReady}`)
        if (agreementReady) {
          const activeSelector = '.login-agreement__check--active'
          log(`协议初始勾选状态：${Boolean(await client.execute(`return Boolean(document.querySelector("${activeSelector}"))`))}`)
          await client.execute('document.querySelector(".login-agreement")?.click(); return true')
          await waitFor('协议已勾选（DOM）', () => client.execute(`return Boolean(document.querySelector("${activeSelector}"))`), 3_000)
          await client.context('NATIVE_APP')
          log(`已通过源码选择器勾选用户协议和隐私政策（${webView}）`)
          return
        }
      } catch (error) {
        log(`跳过不可用 WebView（${webView}）：${error.message}`)
      }
    }
    log('协议源码选择器未暴露，回退到原生 UI 树')
  } finally {
    await client.context('NATIVE_APP').catch(() => {})
  }

  const agreement = await waitFor('协议勾选区域', () => findUiTreeTextContainer('我已阅读并同意'))
  const container = agreement.containerBounds
  const textBounds = agreement.textBounds
  const checkboxBounds = {
    left: container.left,
    top: container.top,
    right: textBounds.left,
    bottom: container.bottom,
  }
  await tapUiTreeBounds(checkboxBounds)
  await waitFor('协议已勾选', async () => {
    const remotePath = '/sdcard/profile-e2e-ui-tree.xml'
    await adb(['shell', 'uiautomator', 'dump', remotePath], true)
    const { stdout } = await adb(['exec-out', 'cat', remotePath], true)
    return String(stdout).includes('text="✓"') ? true : null
  }, 3_000)
  log('已通过原生 UI 树勾选用户协议和隐私政策')
}

async function tapById(client, id, label = id) {
  const fallbackText = {
    'nav-profile': '我的',
    'profile-edit-avatar': '点击更换头像',
    'profile-avatar-upload': '点击上传头像',
    'profile-editor-save': '保存',
  }[id]
  const element = await waitFor(`业务元素 ${id}`, async () => {
    return await findOptionalBusinessId(client, id)
      || (fallbackText
        ? await findOptionalElement(client, 'xpath', `//*[contains(@text,"${fallbackText}")]`)
        : null)
  })
  // Uni-app's WebView nodes can acknowledge an Appium click without dispatching
  // the page's tap handler. Use the element bounds resolved from the UI tree.
  await tapElementByBounds(client, element)
  log(`已点击 ${label}（源码 ID：${id}）`)
}

async function tapByText(client, text, label = text) {
  const target = await waitFor(label, async () => {
    const element = await findOptionalElement(client, 'xpath', `//*[contains(@text,"${text}")]`)
    if (element) return { element }
    const bounds = cachedUiTreeTextBounds.get(text) || await findUiTreeTextBounds(text)
    return bounds ? { bounds } : null
  })
  if (target.element) {
    await tapElement(client, target.element)
  } else {
    await tapUiTreeBounds(target.bounds)
    log(`已通过原生 UI 树点击 ${label}`)
  }
}

async function waitForSource(client, label, pattern, timeoutMs = scenario.timeoutMs) {
  return waitFor(label, async () => {
    const source = await client.source()
    return activePageMatches(source, pattern) ? source : null
  }, timeoutMs)
}

async function captureEvidence(client, name) {
  const safeName = name.replace(/[^a-z0-9-_]/gi, '-')
  const visualEvidence = /^(05-avatar-uploaded|07-profile-after-restart|04-avatar-upload-timeout)$/.test(safeName)
  if (visualEvidence) {
    try {
      const screenshot = await client.screenshot()
      await fs.writeFile(path.join(reportDir, `${safeName}.png`), Buffer.from(screenshot, 'base64'))
      result.evidence.push(`${safeName}.png`)
    } catch (error) {
      result.evidence.push(`${safeName}.png（采集失败：${error.message}）`)
    }
  }
  try {
    const source = await client.source()
    await fs.writeFile(path.join(reportDir, `${safeName}.xml`), redact(source), 'utf8')
    result.evidence.push(`${safeName}.xml`)
  } catch (error) {
    result.evidence.push(`${safeName}.xml（采集失败：${error.message}）`)
  }
}

async function dismissPrivacy(client) {
  await client.context('NATIVE_APP')
  const button = await findOptionalElement(client, 'id', config.nativePrivacyButtonId)
  if (!button) return false
  await tapElement(client, button)
  await waitForSource(client, '隐私弹窗关闭', /android\.webkit\.WebView|auth-login-page|开始测评|短信验证码登录/)
  return true
}

async function fillInput(client, elementId, value) {
  await tapElement(client, elementId)
  await client.clear(elementId).catch(() => {})
  await adb(['shell', 'input', 'text', String(value)])
  await new Promise((resolve) => setTimeout(resolve, 350))
}

async function waitForHome(client) {
  return waitFor('登录后首页', async () => {
    const source = await client.source()
    if (isHomeSource(source)) return source
    // On some WebView builds the page source lags behind the native UI tree
    // after navigation. The stable business node is a more reliable signal.
    const home = await findOptionalBusinessId(client, 'home-page')
      || await findOptionalBusinessId(client, 'nav-profile')
    return home ? source : null
  })
}

function isHomeSource(source) {
  return /resource-id="home-page"|resource-id="nav-profile"|text="pages\/home\[\d+\]"/.test(source)
}

async function returnToHome(client) {
  const source = await client.source()
  if (isHomeSource(source)) return

  // The app restores the last route after a force-stop. Return through the
  // page's semantic control instead of assuming the restored route is home.
  const homeButton = await findOptionalElement(client, 'xpath', '//*[contains(@text,"返回首页") or contains(@content-desc,"返回首页")]')
  const homeTab = homeButton || await findOptionalElement(client, 'xpath', '//*[contains(@text,"首页")]')
  if (!homeTab) throw new Error('当前已登录但不在首页，且当前页面没有返回首页控件')
  await tapElementByBounds(client, homeTab)
  await waitForHome(client)
}

async function ensureLoggedIn(client) {
  await client.context('NATIVE_APP')
  try {
    const contexts = await client.contexts()
    log(`可用自动化 context：${JSON.stringify(contexts)}`)
  } catch (error) {
    log(`读取自动化 context 失败：${error.message}`)
  }
  let source = await client.source()
  if (/从相册选择|拍摄/.test(source)) {
    const cancel = await findOptionalElement(client, 'xpath', '//*[contains(@text,"取消")]')
    if (cancel) await tapElement(client, cancel)
    source = await client.source()
  }
  if (isHomeSource(source)) return
  if (source.includes('tv_custom_privacy_title')) {
    await dismissPrivacy(client)
  }
  const afterPrivacy = await client.source()
  if (isHomeSource(afterPrivacy)) return
  if (!/短信验证码登录|一键登录|auth-login-page/.test(afterPrivacy)) {
    await returnToHome(client)
    return
  }
  throw new Error('头像场景的短信登录前置未完成')
}

async function pushTestImage() {
  const image = scenario.testImage
  await fs.access(image.localPath)
  // Avoid Android's limited-photo selection left by an earlier run.
  await adb(['shell', 'pm', 'grant', config.app.packageName, 'android.permission.READ_MEDIA_IMAGES'], true)
  await adb(['shell', 'pm', 'grant', config.app.packageName, 'android.permission.READ_EXTERNAL_STORAGE'], true)
  await adb(['shell', 'mkdir', '-p', '/sdcard/Pictures/HuiyiTechE2E'])
  await adb(['push', image.localPath, image.devicePath])
  await adb(['shell', 'am', 'broadcast', '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE', '-d', `file://${image.devicePath}`], true)
  await runCommand(config.device.adbPath, ['-s', result.device, 'shell', 'ls', '-l', image.devicePath])
}

async function chooseTestImage(client) {
  const image = scenario.testImage
  await client.context('NATIVE_APP')
  const albumChoice = await findOptionalElement(client, 'xpath', '//*[contains(@text,"从相册选择")]')
  if (albumChoice) {
    await tapElement(client, albumChoice)
  }
  await new Promise((resolve) => setTimeout(resolve, 700))
  await waitFor('系统图片选择器', async () => {
    const source = await client.source()
    return /DocumentsUI|Photo|照片|图片|最近|Pictures|选择|完成|Done/i.test(source) ? source : null
  })
  await captureEvidence(client, '03b-system-picker-before-selection')

  const selectors = [
    ['xpath', `//*[contains(@text,"${image.displayName}")]`],
    ['xpath', `//*[contains(@content-desc,"${image.displayName}")]`],
    ['xpath', '//*[contains(@text,"profile-avatar-test")]'],
    ['xpath', '//*[contains(@content-desc,"profile-avatar-test")]'],
  ]
  let fileElement = null
  for (const [using, value] of selectors) {
    fileElement = await findOptionalElement(client, using, value)
    if (fileElement) break
  }
  if (!fileElement) {
    fileElement = await findOptionalBusinessId(client, 'com.caacyj.app:id/media_image')
  }
  if (!fileElement) {
    const source = await client.source()
    await fs.writeFile(path.join(reportDir, 'picker-not-found.xml'), redact(source), 'utf8')
    throw new Error(`系统图片选择器中没有找到专用测试图片 ${image.displayName}`)
  }
  await tapElement(client, fileElement)

  const selectedSource = await waitFor('图片已选中', async () => {
    const source = await client.source()
    return /resource-id="[^"]+:id\/done"[^>]*text="完成\(1\/1\)"|resource-id="[^"]+:id\/preview"[^>]*text="预览\(1\)"|完成\s*\(\s*1\s*\/\s*1\s*\)|预览\s*\(\s*1\s*\)|已选中/i.test(source)
      ? source
      : null
  }, 3_000).catch(() => null)

  if (!selectedSource) {
    // Some MIUI picker builds acknowledge UiAutomator's click without
    // dispatching the tap. Retry the same UI-tree element by its bounds.
    const rect = await client.rect(fileElement)
    await adb(['shell', 'input', 'tap', String(Math.round(rect.x + rect.width / 2)), String(Math.round(rect.y + rect.height / 2))])
    await waitForSource(client, '图片已选中', /完成\s*\(\s*1\s*\/\s*1\s*\)|预览\s*\(\s*1\s*\)|已选中/)
  }

  const doneButton = await findOptionalBusinessId(client, 'com.caacyj.app:id/done')
    || await findOptionalElement(client, 'xpath', '//*[contains(@text,"完成(")]')
    || await findOptionalElement(client, 'xpath', '//*[contains(@text,"使用此照片")]')
    || await findOptionalElement(client, 'xpath', '//*[contains(@text,"Done")]')
  if (!doneButton) {
    throw new Error('图片已选中，但系统图片选择器没有返回完成按钮')
  }
  await tapElement(client, doneButton)
  const editorPattern = /profile-avatar-preview-image|profile-editor|编辑资料|点击上传头像|上传中/
  const returnedToEditor = await waitForSource(client, '返回编辑资料抽屉并显示新头像', editorPattern, 3_000).catch(() => null)
  if (!returnedToEditor) {
    // MIUI's picker can acknowledge the element click without dispatching
    // the action. Retry with the same UI-tree bounds instead of a coordinate.
    const rect = await client.rect(doneButton)
    await adb(['shell', 'input', 'tap', String(Math.round(rect.x + rect.width / 2)), String(Math.round(rect.y + rect.height / 2))])
    await waitForSource(client, '重试完成并返回编辑资料', editorPattern)
  }
  await captureEvidence(client, '03c-system-picker-after-selection')
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

async function appendLogcat() {
  if (!result.device) return
  const { stdout, stderr } = await adb(['logcat', '-d', '-v', 'threadtime'], true)
  const filtered = `${stdout}\n${stderr}`.split(/\r?\n/)
    .filter((line) => /customerAuth|upload|profile|DocumentsUI|AndroidRuntime|FATAL EXCEPTION|chromium|WebView/i.test(line))
    .map(redact).join('\n')
  await fs.writeFile(path.join(reportDir, 'logcat-filtered.txt'), `${filtered}\n`, 'utf8')
  result.evidence.push('logcat-filtered.txt')
}

async function runMainFlow() {
  await fs.mkdir(reportDir, { recursive: true })
  result.device = await findDevice()
  const reuseInstalledCustomBase = Boolean(scenario.reuseInstalledCustomBase)
  result.apk = reuseInstalledCustomBase ? 'installed-custom-base' : await findApk()
  log(`设备：${result.device}`)
  log(reuseInstalledCustomBase ? '测试目标：设备上已运行的自定义基座' : `APK：${result.apk}`)
  await launchCleanAppTask(adb, config.app)
  const initialSource = await waitFor('应用启动后的首页或登录页', async () => {
    const source = await nativeUiTreeSource()
    return isNativeHomeSource(source) || /短信验证码登录|一键登录|auth-login-page/.test(source)
      ? source
      : null
  }, 20_000)
  if (!isNativeHomeSource(initialSource)) {
    await cacheLoginUiTreeBounds()
    await loginWithSmsThroughDevTools()
    await waitForHomeFromNativeUiTree()
  } else {
    log('设备已保留登录态，跳过短信登录前置')
  }
  await pushTestImage()
  const appiumProcess = await ensureAppium()
  const client = new WebDriverClient(config.appium.serverUrl)
  const capabilities = {
    alwaysMatch: {
      platformName: 'Android',
      'appium:automationName': 'UiAutomator2',
      'appium:deviceName': result.device,
      'appium:udid': result.device,
      ...(reuseInstalledCustomBase ? {} : { 'appium:app': result.apk }),
      'appium:appPackage': config.app.packageName,
      'appium:appActivity': config.app.activity,
      'appium:autoGrantPermissions': true,
      'appium:noReset': true,
      'appium:fullReset': false,
      'appium:newCommandTimeout': 180,
      'appium:chromedriverAutodownload': true,
    },
  }
  try {
    await client.createSession(capabilities)

    await recordStep(1, '确保登录态并进入首页', async () => {
      await ensureLoggedIn(client)
      await waitForHome(client)
      await captureEvidence(client, '01-home-before-profile')
    })

    await recordStep(2, '进入个人中心并打开编辑资料', async () => {
      await tapById(client, 'nav-profile', '个人中心底部导航')
      await waitForSource(client, '个人中心页面', /text="pages\/profile\[\d+\]"|点击更换头像/)
      await tapById(client, 'profile-edit-avatar', '头像编辑入口')
      await waitForSource(client, '编辑资料抽屉', /resource-id="profile-editor"|编辑资料|点击上传头像/)
      avatarMarkerBeforeUpload = avatarImageMarker(await client.source(), 'profile-avatar-preview-image')
      avatarSourcesBeforeUpload = await readProfileImageSources('#profile-avatar-upload')
      log(`上传前头像来源：${avatarSourcesBeforeUpload.join(', ') || '无'}`)
      await captureEvidence(client, '02-profile-editor-before-upload')
    })

    await recordStep(3, '通过系统图片选择器选择专用测试图片', async () => {
      await tapById(client, 'profile-avatar-upload', '头像上传区域')
      await waitForSource(client, '头像来源选择菜单', /拍摄|从相册选择|取消/)
      await captureEvidence(client, '03-avatar-source-menu')
      await chooseTestImage(client)
      await captureEvidence(client, '04-avatar-selected')
    })

    await recordStep(4, '等待头像上传完成', async () => {
      let observedUploading = false
      let completed = false
      try {
        await waitFor('头像上传完成或失败', async () => {
          const source = await client.source()
          if (/头像上传失败|上传失败/.test(source)) {
            throw new Error('头像上传失败')
          }
          if (/头像上传成功/.test(source)) {
            completed = true
            return source
          }
          if (/上传中\.\.\./.test(source)) {
            observedUploading = true
            return null
          }
          const remoteAvatar = findNewRemoteAvatar(await readProfileImageSources('#profile-avatar-upload'))
          if (remoteAvatar) {
            uploadedAvatarSource = remoteAvatar
            completed = true
            return source
          }
          const marker = avatarImageMarker(source, 'profile-avatar-preview-image')
          if (marker && marker !== avatarMarkerBeforeUpload) {
            completed = true
            return source
          }
          // A fast native upload can finish between two UI-tree polls. Once
          // the editor is back and no error is exposed, the changed image
          // node is the available success signal for this APK build.
          if (!observedUploading && /编辑资料|点击上传头像/.test(source) && marker) return null
          return null
        }, scenario.timeoutMs)
      } catch (error) {
        await captureEvidence(client, '04-avatar-upload-timeout')
        const source = await client.source()
        const state = source.match(/上传中\.\.\.|头像上传失败|上传失败/)?.[0]
        try {
          const sources = await readProfileImageSources('#profile-avatar-upload')
          await writeJson('04-avatar-dom-sources.json', sources)
          result.evidence.push('04-avatar-dom-sources.json')
        } catch (domError) {
          log(`读取头像 DOM 来源失败：${domError.message}`)
        }
        throw new Error(`${error.message}${state ? `（状态：${state}）` : ''}`)
      }
      if (!completed) throw new Error('头像上传未确认完成')
      await captureEvidence(client, '05-avatar-uploaded')
    })

    await recordStep(5, '保存头像并验证个人中心展示', async () => {
      await tapById(client, 'profile-editor-save', '保存个人资料')
      await waitFor('编辑资料抽屉关闭', async () => {
        const source = await client.source()
        return /text="pages\/profile\[\d+\]"|点击更换头像/.test(source) && !source.includes('点击上传头像')
      })
      await waitFor('个人中心头像图片节点', async () => avatarImageMarker(await client.source()))
      await waitFor('个人中心展示保存后的头像 URL', async () => {
        const sources = await readProfileImageSources()
        return uploadedAvatarSource && sources.includes(uploadedAvatarSource) ? sources : null
      })
      await captureEvidence(client, '06-profile-after-save')
    })

    await recordStep(6, '重启应用后验证头像持久化', async () => {
      // Restarting the app also restarts UiAutomator2 on this device. Recreate
      // the session so a stale accessibility connection cannot mask the
      // persistence assertion.
      await client.deleteSession()
      await launchCleanAppTask(adb, config.app)
      await client.createSession(capabilities)
      await ensureLoggedIn(client)
      await waitForHome(client)
      await tapById(client, 'nav-profile', '重启后进入个人中心')
      await waitForSource(client, '重启后个人中心页面', /text="pages\/profile\[\d+\]"|点击更换头像/)
      await waitFor('重启后头像图片节点', async () => avatarImageMarker(await client.source()))
      await waitFor('重启后头像 URL 持久化', async () => {
        const sources = await readProfileImageSources()
        return uploadedAvatarSource && sources.includes(uploadedAvatarSource) ? sources : null
      })
      await captureEvidence(client, '07-profile-after-restart')
    })

    result.status = 'passed'
  } finally {
    await appendLogcat()
    await client.deleteSession()
    await stopProcessTree(appiumProcess)
  }
}

try {
  await runMainFlow()
} catch (error) {
  result.status = 'failed'
  result.error = error.message
  log(`结果：failed：${error.message}`)
  process.exitCode = 1
} finally {
  result.finishedAt = new Date().toISOString()
  await fs.mkdir(reportDir, { recursive: true })
  await writeJson('result.json', result)
  log(`报告：${reportDir}`)
}
