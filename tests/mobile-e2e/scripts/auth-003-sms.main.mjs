import fs from 'node:fs/promises'
import path from 'node:path'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import config from '../config.mjs'
import { launchCleanAppTask } from './lib/app-task.mjs'

const execFileAsync = promisify(execFile)
const scenario = config.scenarios.sms
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

  context(name) { return this.command('/context', 'POST', { name }) }
  source() { return this.command('/source') }
  screenshot() { return this.command('/screenshot') }
  find(using, value) { return this.command('/element', 'POST', { using, value }) }
  findAll(using, value) { return this.command('/elements', 'POST', { using, value }) }
  rect(elementId) { return this.command(`/element/${elementId}/rect`) }
  hideKeyboard() { return this.command('/appium/device/hide_keyboard', 'POST', {}) }
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
      return {
        stdout: error.stdout?.toString() || '',
        stderr: error.stderr?.toString() || error.message,
      }
    }
    throw error
  }
}

async function adb(args, allowFailure = false) {
  // findDevice() stores the selected serial as a string. Always scope ADB
  // commands to that serial so a second connected device cannot steal a call.
  const prefix = result.device ? ['-s', result.device] : []
  return runCommand(config.device.adbPath, [...prefix, ...args], allowFailure)
}

async function findDevice() {
  const { stdout } = await runCommand(config.device.adbPath, ['devices'])
  const devices = stdout.split(/\r?\n/)
    .slice(1)
    .map((line) => line.trim().split(/\s+/))
    .filter(([serial, state]) => serial && state === 'device')
    .map(([serial]) => serial)
  const serial = config.device.serial || (devices.length === 1 ? devices[0] : '')
  if (!serial) {
    if (!devices.length) throw new Error('没有发现 Android 真机。请先完成 ADB 配对/连接。')
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
    const response = await fetch(`${config.appium.serverUrl}/status`, { signal: AbortSignal.timeout(2_000) })
    if (!response.ok) return false
    const payload = await response.json().catch(() => null)
    return payload?.value?.ready !== false
  } catch {
    return false
  }
}

async function stopExistingAppium() {
  if (process.platform !== 'win32') return
  const { stdout } = await runCommand('netstat', ['-ano', '-p', 'tcp'], true)
  const pids = new Set()
  for (const line of stdout.split(/\r?\n/)) {
    const columns = line.trim().split(/\s+/)
    if (columns[0] !== 'TCP' || columns[3] !== 'LISTENING') continue
    if (!columns[1].endsWith(`:${config.appium.port}`)) continue
    if (/^\d+$/.test(columns[4])) pids.add(columns[4])
  }
  for (const pid of pids) {
    log(`清理 4723 上残留的 Appium 进程：${pid}`)
    await runCommand('taskkill', ['/pid', pid, '/t', '/f'], true)
  }
  if (pids.size) await new Promise((resolve) => setTimeout(resolve, 500))
}

async function ensureAppium() {
  if (!config.appium.autoStart) throw new Error('Appium 服务未启动，且 config.mjs 禁止自动启动。')

  if (config.appium.restartExisting) await stopExistingAppium()
  if (await appiumAvailable()) return null

  log('Appium 未运行，正在启动本地服务')
  const javaBin = path.join(config.appium.javaHome, 'bin')
  const child = spawn(config.appium.command, [
    '--address', config.appium.host,
    '--port', String(config.appium.port),
    '--base-path', '/',
    '--allow-insecure', config.appium.allowInsecure.join(','),
  ], {
    shell: true,
    windowsHide: true,
    env: {
      ...process.env,
      JAVA_HOME: config.appium.javaHome,
      Path: `${javaBin};${process.env.Path || ''}`,
    },
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

async function findAllElementIds(client, using, value) {
  const response = await client.findAll(using, value)
  return response.map((element) => element.elementId || element.ELEMENT).filter(Boolean)
}

async function tapElementCenter(client, elementId) {
  const rect = await client.rect(elementId)
  if (!rect || rect.width <= 0 || rect.height <= 0) {
    throw new Error(`元素没有有效边界：${elementId}`)
  }
  await adb([
    'shell', 'input', 'tap',
    String(Math.round(rect.x + rect.width / 2)),
    String(Math.round(rect.y + rect.height / 2)),
  ])
}

async function currentActivity() {
  const { stdout } = await adb(['shell', 'dumpsys', 'activity', 'activities'], true)
  return stdout
}

async function dismissNativePrivacy(client) {
  await client.context('NATIVE_APP')
  const button = await findOptionalElement(client, 'id', config.nativePrivacyButtonId)
  if (button) {
    await client.command(`/element/${button}/click`, 'POST', {})
    return true
  }
  const source = await client.source()
  if (source.includes('btn_custom_privacy_sure')) {
    await adb(['shell', 'input', 'tap', '540', '1475'])
    return true
  }
  return false
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
  if (!result.device) return
  const { stdout, stderr } = await adb(['logcat', '-d', '-v', 'threadtime'], true)
  const filtered = `${stdout}\n${stderr}`
    .split(/\r?\n/)
    .filter((line) => /customerAuth|login|AndroidRuntime|FATAL EXCEPTION|chromium|WebView/i.test(line))
    .map(redact)
    .join('\n')
  await fs.writeFile(path.join(reportDir, 'logcat-filtered.txt'), `${filtered}\n`, 'utf8')
  result.evidence.push('logcat-filtered.txt')
}

async function waitForHome(client) {
  await client.context('NATIVE_APP')
  await waitFor('登录完成并回到首页 Activity', async () => {
    const activity = await currentActivity()
    const resumedLine = activity.split(/\r?\n/).find((line) => /topResumedActivity|ResumedActivity/.test(line)) || ''
    return resumedLine.includes(`${config.app.packageName}/${config.app.homeActivity}`)
  })
  await waitFor('首页内容实际渲染', async () => {
    const source = await client.source()
    return /开始测评|题库训练|岗位招聘|首页/.test(source)
  })
}

async function fillInput(client, elementId, value) {
  // The release WebView exposes EditText nodes, but Appium's /value command
  // does not always dispatch the input event that updates Uni-app v-model.
  // Focus the UI-tree element first, then use ADB input to generate a real
  // Android keyboard event.
  await client.command(`/element/${elementId}/click`, 'POST', {})
  await adb(['shell', 'input', 'text', String(value)])
  await new Promise((resolve) => setTimeout(resolve, 300))
}

async function runMainFlow() {
  await fs.mkdir(reportDir, { recursive: true })
  result.device = await findDevice()
  result.apk = await findApk()
  log(`设备：${result.device}`)
  log(`APK：${result.apk}`)
  // Start from a deterministic logged-out state while preserving the
  // successful login for the authenticated scenarios that run afterwards.
  await adb(['shell', 'pm', 'clear', config.app.packageName], true)
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
        'appium:noReset': true,
        'appium:fullReset': false,
        'appium:newCommandTimeout': 180,
        'appium:chromedriverAutodownload': true,
      },
    })
    result.steps.push({ id: 1, name: '启动应用', status: 'passed' })

    const privacyDismissed = await dismissNativePrivacy(client)
    if (privacyDismissed) {
      await waitFor('隐私弹窗关闭', async () => {
        const source = await client.source()
        return !source.includes('tv_custom_privacy_title') && source.includes('android.webkit.WebView')
      })
    }
    result.steps.push({
      id: 2,
      name: '处理首次隐私弹窗',
      status: 'passed',
      detail: privacyDismissed ? '已点击同意' : '未出现',
    })

    await client.context('NATIVE_APP')
    await waitFor('短信登录入口', async () => {
      const source = await client.source()
      return source.includes('android.webkit.WebView') && source.includes('短信验证码登录')
    })
    const smsTab = await waitFor(
      '短信验证码登录入口',
      () => findOptionalElement(client, 'xpath', '//*[contains(@text,"短信验证码登录")]'),
    )
    await tapElementCenter(client, smsTab)
    const inputIds = await waitFor(
      '短信登录表单输入框',
      async () => {
        const ids = await findAllElementIds(client, 'class name', 'android.widget.EditText')
        return ids.length >= 2 ? ids : null
      },
    )
    result.steps.push({ id: 3, name: '切换到短信验证码登录', status: 'passed' })
    await captureEvidence(client, '01-sms-login-form')

    await fillInput(client, inputIds[0], scenario.phone)
    result.steps.push({ id: 4, name: '填写测试手机号', status: 'passed' })
    await fillInput(client, inputIds[1], scenario.code)
    await client.hideKeyboard().catch(async () => {
      await adb(['shell', 'input', 'keyevent', '4'])
    })
    await new Promise((resolve) => setTimeout(resolve, 300))
    result.steps.push({
      id: 5,
      name: '填写固定验证码',
      status: 'passed',
      detail: '使用测试配置中的固定验证码，未点击获取验证码，不发送真实短信',
    })

    const agreement = await waitFor(
      '短信登录协议区域',
      () => findOptionalElement(client, 'xpath', '//*[contains(@text,"我已阅读并同意")]'),
    )
    await tapElementCenter(client, agreement)
    result.steps.push({ id: 6, name: '同意用户协议和隐私政策', status: 'passed' })

    const submit = await waitFor(
      '短信登录提交按钮',
      () => findOptionalElement(client, 'xpath', '//*[contains(@text,"登录 / 注册")]'),
    )
    await tapElementCenter(client, submit)
    result.steps.push({ id: 7, name: '提交短信登录', status: 'passed' })
    await waitForHome(client)
    await captureEvidence(client, '02-home-after-sms-login')
    result.steps.push({ id: 8, name: '后端校验完成并进入首页', status: 'passed' })
    result.status = 'passed'
  } catch (error) {
    await captureEvidence(client, 'failure-state').catch(() => {})
    throw error
  } finally {
    await client.deleteSession()
    await stopProcessTree(appiumProcess)
  }
}

try {
  await runMainFlow()
} catch (error) {
  result.status = 'failed'
  result.error = error.message
  log(error.message)
  process.exitCode = 1
} finally {
  await appendLogcat().catch(() => {})
  result.finishedAt = new Date().toISOString()
  await fs.mkdir(reportDir, { recursive: true })
  await writeJson('result.json', result)
  log(`结果：${result.status}`)
  log(`报告：${reportDir}`)
}
