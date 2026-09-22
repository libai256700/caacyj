import fs from 'node:fs/promises'
import path from 'node:path'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'
import config from '../config.mjs'

const execFileAsync = promisify(execFile)
const scenario = config.scenarios.selfTest
const testDir = path.dirname(fileURLToPath(import.meta.url))
const workspaceRoot = path.resolve(testDir, '../..')
const smsScript = path.join(testDir, 'auth-003-sms.main.mjs')
const startedAt = new Date()
const runId = startedAt.toISOString().replace(/[:.]/g, '-')
const reportDir = path.join(scenario.reportDir, runId)
let cachedQuestionSource = ''
const result = {
  scenarioId: scenario.id,
  status: 'running',
  startedAt: startedAt.toISOString(),
  device: null,
  apk: null,
  steps: [],
  evidence: [],
}

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

  async close() {
    if (this.session) await this.request(`/session/${this.session}`, 'DELETE').catch(() => {})
    this.session = ''
  }

  command(endpoint, method = 'GET', body) { return this.request(`/session/${this.session}${endpoint}`, method, body) }
  context(name) { return this.command('/context', 'POST', { name }) }
  source() { return this.command('/source') }
  screenshot() { return this.command('/screenshot') }
  find(using, value) { return this.command('/element', 'POST', { using, value }) }
  findAll(using, value) { return this.command('/elements', 'POST', { using, value }) }
  rect(elementId) { return this.command(`/element/${elementId}/rect`) }
  click(elementId) { return this.command(`/element/${elementId}/click`, 'POST', {}) }
  clear(elementId) { return this.command(`/element/${elementId}/clear`, 'POST', {}) }
  hideKeyboard() { return this.command('/appium/device/hide_keyboard', 'POST', {}) }
}

const run = (command, args, allowFailure = false) => execFileAsync(command, args, {
  windowsHide: true,
  maxBuffer: 8 * 1024 * 1024,
}).catch((error) => {
  if (allowFailure) return { stdout: error.stdout?.toString() || '', stderr: error.stderr?.toString() || error.message }
  throw error
})

const adb = (args, allowFailure = false) => run(config.device.adbPath, ['-s', result.device.serial, ...args], allowFailure)
const redact = (value) => String(value)
  .replace(/(access[_-]?token|openid|auth[_-]?token|secret|password)["'\s:=]+[^,\s}\]]+/gi, '$1=<redacted>')
  .replace(/\b\d{11}\b/g, '<phone-redacted>')

async function findDevice() {
  const { stdout } = await run(config.device.adbPath, ['devices'])
  const devices = stdout.split(/\r?\n/).slice(1)
    .map((line) => line.trim().split(/\s+/))
    .filter(([, state]) => state === 'device')
    .map(([serial]) => serial)
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

async function syncWebAssets() {
  const extractedDir = path.join(reportDir, 'apk-assets')
  await fs.mkdir(extractedDir, { recursive: true })
  await run('tar', ['-xf', result.apk, '-C', extractedDir])
  const assetsDir = path.join(extractedDir, 'assets', 'apps', config.app.appId, 'www')
  const entries = await fs.readdir(assetsDir)
  if (!entries.length) throw new Error(`前端资源目录为空：${assetsDir}`)
  await adb(['shell', 'mkdir', '-p', config.app.webAssetsRemoteDir])
  await adb(['push', `${assetsDir}${path.sep}.`, `${config.app.webAssetsRemoteDir}/`])
  // Direct ADB pushes are owned by shell. Make the app's external cache
  // traversable/readable without touching any app-private data.
  await adb(['shell', 'find', config.app.webAssetsRemoteDir, '-type', 'd', '-exec', 'chmod', '2775', '{}', '+'])
  await adb(['shell', 'find', config.app.webAssetsRemoteDir, '-type', 'f', '-exec', 'chmod', '664', '{}', '+'])
}

async function waitFor(label, predicate, timeout = scenario.timeoutMs) {
  const deadline = Date.now() + timeout
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
  try { return (await fetch(`${config.appium.serverUrl}/status`, { signal: AbortSignal.timeout(2_000) })).ok } catch { return false }
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
  await waitFor('Appium 服务启动', appiumAvailable, 20_000)
  return child
}

async function stopProcess(child) {
  if (!child) return
  if (process.platform === 'win32' && child.pid) await run('taskkill', ['/pid', String(child.pid), '/t', '/f'], true)
  else child.kill()
}

async function runSmsLogin() {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [smsScript], {
      cwd: workspaceRoot,
      stdio: 'inherit',
      windowsHide: false,
    })
    child.once('error', reject)
    child.once('exit', (code, signal) => resolve({ code: code ?? 1, signal }))
  })
}

async function findElement(driver, using, value) {
  const response = await driver.find(using, value)
  return response.elementId || response.ELEMENT
}

async function findOptionalElement(driver, using, value) {
  try { return await findElement(driver, using, value) } catch { return null }
}

async function findAllElementIds(driver, using, value) {
  const response = await driver.findAll(using, value)
  return response.map((element) => element.elementId || element.ELEMENT).filter(Boolean)
}

async function currentUiSource() {
  await adb(['shell', 'uiautomator', 'dump', '/sdcard/codex-self-test-window.xml'], true)
  const { stdout } = await adb(['shell', 'cat', '/sdcard/codex-self-test-window.xml'], true)
  return stdout
}

async function deviceScreenshot() {
  const { stdout } = await execFileAsync(config.device.adbPath, [
    '-s', result.device.serial,
    'exec-out', 'screencap', '-p',
  ], { windowsHide: true, maxBuffer: 8 * 1024 * 1024, encoding: null })
  return stdout
}

async function tapById(driver, id) {
  const fallbackText = {
    'home-start-assessment': '开始测评',
    'self-test-profile-next': '下一步',
    'self-test-submit': '下一题',
    'self-test-previous': '上一题',
    'self-test-submitted-home': '返回首页',
    'home-assessment-result': '评测结果',
  }[id]
  const bounds = await waitFor(`元素 ${id}`, async () => {
    const source = await currentUiSource()
    const byId = boundsForSourceId(source, id)
    if (byId) {
      if (byId.y >= 2320) {
        await adb(['shell', 'input', 'swipe', '540', '1900', '540', '700', '500'])
        return null
      }
      return byId
    }
    if (fallbackText) {
      const byText = boundsForSourceText(source, fallbackText)
      if (byText) {
        if (byText.y >= 2320) {
          await adb(['shell', 'input', 'swipe', '540', '1900', '540', '700', '500'])
          return null
        }
        return byText
      }
    }
    if (id === 'self-test-submit') {
      const submitBounds = boundsForSourceText(source, '提交并生成报告')
      if (submitBounds?.y >= 2320) {
        await adb(['shell', 'input', 'swipe', '540', '1900', '540', '700', '500'])
        return null
      }
      return submitBounds
    }
    if (id === 'self-test-back') return boundsForSourceText(source, '返回')
    return null
  })
  await tapBounds(bounds)
}

async function tapByIdFromSource(driver, id, source) {
  const fallbackText = {
    'self-test-submit': '下一题',
    'self-test-previous': '上一题',
  }[id]
  const bounds = boundsForSourceId(source, id)
    || (fallbackText ? boundsForSourceText(source, fallbackText) : null)
    || (id === 'self-test-submit' ? boundsForSourceText(source, '提交并生成报告') : null)
  // A WebView can expose controls below the viewport with a zero-height or
  // clipped bounds rectangle. Do not tap that stale coordinate: let tapById
  // reacquire the tree, scroll the control into view, and tap the new bounds.
  if (bounds && bounds.y >= 80 && bounds.y < 2320 && await tapBounds(bounds)) return
  await tapById(driver, id)
}

async function tapByText(driver, text) {
  const bounds = await waitFor(`文本 ${text}`, async () => boundsForSourceText(await currentUiSource(), text))
  await tapBounds(bounds)
}

async function fillTextById(driver, id, value) {
  const bounds = await waitFor(`输入框 ${id}`, async () => {
    const source = await currentUiSource()
    const byId = boundsForSourceId(source, id)
    if (byId) return byId

    // Older release APKs flatten the WebView and omit source-defined IDs.
    // The profile form has one visible EditText at this point, so use its
    // bounds as a compatibility fallback without inspecting its content.
    if (id === 'self-test-profile-name') {
      const match = source.match(/<node[^>]*class="android\.widget\.EditText"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/)
      if (match) {
        const [, left, top, right, bottom] = match.map(Number)
        return { x: Math.round((left + right) / 2), y: Math.round((top + bottom) / 2) }
      }
    }
    return null
  })
  await tapBounds(bounds)
  await adb(['shell', 'input', 'text', String(value)])
  await new Promise((resolve) => setTimeout(resolve, 350))
}

async function capture(driver, name) {
  try { await fs.writeFile(path.join(reportDir, `${name}.png`), await deviceScreenshot()); result.evidence.push(`${name}.png`) } catch {}
  try { await fs.writeFile(path.join(reportDir, `${name}.xml`), redact(await currentUiSource()), 'utf8'); result.evidence.push(`${name}.xml`) } catch {}
}

function activeHome(source) { return source.includes('resource-id="home-page"') || source.includes('resource-id="home-start-assessment"') || /开始测评|岗位招聘/.test(source) }
function questionMarker(source) {
  const node = source.split(/<node\b/).find((fragment) => fragment.includes('self-test-question-count')) || ''
  return node.match(/text="([^"]*)"/)?.[1] || source.match(/text="(\d+\/\d+)"/)?.[1] || ''
}

async function waitForHome(driver) {
  await waitFor('首页', async () => activeHome(await currentUiSource()))
}

function optionBounds(source) {
  // Older release APKs flatten the WebView into non-clickable TextViews and
  // omit the source-defined option IDs. The option labels remain stable
  // accessibility nodes, so use their bounds only as a compatibility path.
  // Release data uses both letter labels (A.) and numeric scale labels (1.).
  const matches = source.matchAll(/<[^>]+text="(?:[A-Z]|\d+)[\.．、)]"[^>]+bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*\/>/g)
  for (const match of matches) {
    const [, left, top, right, bottom] = match.map(Number)
    // Off-screen WebView nodes are occasionally retained with 0x0 bounds or
    // clipped above/below the visible viewport. Use the first option whose
    // center is actually tappable instead of blindly taking the first ID.
    const centerY = Math.round((top + bottom) / 2)
    if (right <= left || bottom <= top || centerY < 100 || centerY >= 2300) continue
    return { x: Math.round((left + right) / 2), y: centerY }
  }
  return null
}

function boundsForSourceId(source, id) {
  const escapedId = id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = source.match(new RegExp(`resource-id="${escapedId}"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`))
  if (!match) return null
  const [, left, top, right, bottom] = match.map(Number)
  return { x: Math.round((left + right) / 2), y: Math.round((top + bottom) / 2) }
}

function boundsForSourceText(source, text) {
  const escapedText = text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const exact = source.match(new RegExp(`text="${escapedText}"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`))
  const match = exact || source.match(new RegExp(`text="[^"]*${escapedText}[^"]*"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`))
  if (!match) return null
  const [, left, top, right, bottom] = match.map(Number)
  return { x: Math.round((left + right) / 2), y: Math.round((top + bottom) / 2) }
}

function boundsForLastSourceText(source, text) {
  const escapedText = text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const matches = [...source.matchAll(new RegExp(`text="${escapedText}"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`, 'g'))]
  if (!matches.length) return null
  const [, left, top, right, bottom] = matches.reduce((lowest, match) => Number(match[2]) > Number(lowest[2]) ? match : lowest)
  return { x: Math.round((Number(left) + Number(right)) / 2), y: Math.round((Number(top) + Number(bottom)) / 2) }
}

async function tapBounds(bounds) {
  if (!bounds) return false
  await adb(['shell', 'input', 'tap', String(bounds.x), String(bounds.y)])
  return true
}

async function tapAnswerOption(driver, source) {
  const sourceIdPattern = /resource-id="self-test-option-[^"]+"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/g
  for (const match of source.matchAll(sourceIdPattern)) {
    const [, left, top, right, bottom] = match.map(Number)
    const centerY = Math.round((top + bottom) / 2)
    if (right <= left || bottom <= top || centerY < 100 || centerY >= 2300) continue
    if (await tapBounds({
      x: Math.round((left + right) / 2),
      y: centerY,
    })) return
  }
  const bounds = optionBounds(source)
  if (await tapBounds(bounds)) return
  throw new Error('当前自测题目没有可操作的选项')
}

async function answerCurrentQuestion(driver, source = null) {
  const currentSource = source || await currentUiSource()
  if (/暂无可用自测题目|自测题目加载失败/.test(currentSource)) throw new Error('自测题目不可用，未进入可答题状态')
  if (currentSource.includes('class="android.widget.EditText"')) {
    const inputMatch = currentSource.match(/class="android\.widget\.EditText"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/)
    if (!inputMatch) throw new Error('文本题输入框未出现在 UI 树')
    await tapBounds({
      x: Math.round((Number(inputMatch[1]) + Number(inputMatch[3])) / 2),
      y: Math.round((Number(inputMatch[2]) + Number(inputMatch[4])) / 2),
    })
    await adb(['shell', 'input', 'text', 'AutoAnswer'])
    await adb(['shell', 'input', 'keyevent', '4'], true)
    // Closing the keyboard can move the action bar back into the viewport.
    // Give the WebView one frame to settle before reacquiring its bounds.
    await new Promise((resolve) => setTimeout(resolve, 350))
    return 'text'
  }
  await tapAnswerOption(driver, currentSource)
  return 'option'
}

async function advanceFromCurrent(driver) {
  // The transition wait already captured the next question's UI tree. Reuse
  // it for the next iteration instead of paying for a second ADB dump.
  const before = cachedQuestionSource || await currentUiSource()
  cachedQuestionSource = ''
  const marker = questionMarker(before)
  console.log(`[${scenario.id}] 处理自测题 ${marker || 'unknown'}`)
  const answerKind = await answerCurrentQuestion(driver, before)
  const isLast = /提交并生成报告/.test(before)
  // Text input opens the IME and changes the viewport after the answer is
  // entered. Re-read the tree in that case so we do not tap stale bounds.
  if (answerKind === 'text') await tapById(driver, 'self-test-submit')
  else await tapByIdFromSource(driver, 'self-test-submit', before)
  if (isLast) {
    await waitFor('自测提交结果', async () => /自测报告正在生成中|返回首页|自测提交失败/.test(await currentUiSource()), 30_000)
    if (/自测提交失败/.test(await currentUiSource())) throw new Error('自测整套答案提交失败')
    return { from: marker || 'unknown', to: 'submitted', isLast: true }
  }
  let nextSource = ''
  const nextMarker = await waitFor('下一道自测题', async () => {
    const after = await currentUiSource()
    const currentMarker = questionMarker(after)
    // The marker is a position indicator when exposed by the UI tree. If a
    // release build omits it, waiting for a changed page source still verifies
    // that the next interaction state rendered without inspecting question data.
    return /self-test-submit|下一题|提交并生成报告/.test(after)
      && ((!marker && after !== before) || (marker && currentMarker !== marker))
      ? (nextSource = after, currentMarker || 'changed')
      : null
  }, 45_000)
  cachedQuestionSource = nextSource
  console.log(`[${scenario.id}] 自测进度 ${nextMarker}`)
  return { from: marker || 'unknown', to: nextMarker || 'unknown', isLast: false }
}

async function completeAllQuestions(driver) {
  let submitted = 0
  while (true) {
    const transition = await advanceFromCurrent(driver)
    submitted += 1
    if (transition.isLast) return submitted
  }
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

  await step(1, '短信验证码登录前置', async () => {
    const login = await runSmsLogin()
    if (login.code !== 0) throw new Error(`短信登录脚本失败（退出码 ${login.code}）`)
    await syncWebAssets()
  })

  await adb(['shell', 'am', 'force-stop', config.app.packageName], true)
  const driver = null
  try {
    await adb(['shell', 'am', 'start', '-n', `${config.app.packageName}/${config.app.activity}`])
    await waitForHome(driver)
    await step(2, '打开自测入口并填写资料', async () => {
      await tapById(driver, 'home-start-assessment')
      await waitFor('自测资料页或重新测评弹窗', async () => /填写基本资料|重新测评|self-test-profile-name/.test(await currentUiSource()))
      if (/重新测评/.test(await currentUiSource())) {
        const restartConfirm = await waitFor('重新测评确认按钮', async () => boundsForLastSourceText(await currentUiSource(), '重新测评'))
        await tapBounds(restartConfirm)
        await waitFor('自测资料页', async () => /填写基本资料|self-test-profile-name/.test(await currentUiSource()))
      }
      await fillTextById(driver, 'self-test-profile-name', 'AutoTest')
      await adb(['shell', 'input', 'keyevent', '4'], true)
      await new Promise((resolve) => setTimeout(resolve, 350))
      await tapById(driver, 'self-test-profile-next')
      await capture(driver, '01-self-test-profile-submitted')
    })
    await step(3, '加载第一道自测题', async () => {
      const source = await waitFor('第一道自测题', async () => {
        const current = await currentUiSource()
        return /self-test-submit|下一题|提交并生成报告|暂无可用自测题目|自测题目加载失败/.test(current) ? current : null
      })
      if (/暂无可用自测题目|自测题目加载失败/.test(source)) throw new Error('自测题目不可用')
    })
    await step(4, '验证当前题目交互并推进', async () => {
      await advanceFromCurrent(driver)
      result.steps[result.steps.length - 1].detail = '完成当前题目的任意答案输入并推进到下一题'
    })
    await step(5, '验证上一题返回', async () => {
      cachedQuestionSource = ''
      await tapById(driver, 'self-test-previous')
      await waitFor('上一题返回完成', async () => /self-test-submit|下一题|提交并生成报告/.test(await currentUiSource()))
      await advanceFromCurrent(driver)
    })
    await step(6, '完成整套答案并提交自测', async () => {
      const answerCount = await completeAllQuestions(driver)
      result.steps[result.steps.length - 1].detail = `已完成整套答案输入并提交（交互次数 ${answerCount}）`
      await capture(driver, '05-self-test-submitted')
    })
    await step(7, '提交后返回首页', async () => {
      await tapById(driver, 'self-test-submitted-home')
      await waitForHome(driver)
      await capture(driver, '06-home-after-self-test')
    })
    result.status = 'passed'
  } finally {
    try {
      const logs = await adb(['logcat', '-d', '-v', 'threadtime'], true)
      await fs.writeFile(path.join(reportDir, 'logcat-filtered.txt'), redact(`${logs.stdout}\n${logs.stderr}`), 'utf8')
      result.evidence.push('logcat-filtered.txt')
    } catch {}
  }
}

main().catch(async (error) => {
  result.status = 'failed'
  result.error = error.message
  try {
    if (result.device?.serial) {
      await fs.writeFile(path.join(reportDir, 'failure-state.xml'), redact(await currentUiSource()), 'utf8')
      result.evidence.push('failure-state.xml')
    }
  } catch {}
  console.error(`[${scenario.id}] 结果：failed`)
  console.error(error.stack || error.message)
  process.exitCode = 1
}).finally(async () => {
  result.finishedAt = new Date().toISOString()
  await fs.mkdir(reportDir, { recursive: true })
  await fs.writeFile(path.join(reportDir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
  console.log(`[${scenario.id}] 报告：${reportDir}`)
})
