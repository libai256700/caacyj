import { createReadStream } from 'node:fs'
import { promises as fs } from 'node:fs'
import { createServer } from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import config from './config.mjs'

const execFileAsync = promisify(execFile)
const testDir = path.dirname(fileURLToPath(import.meta.url))
const workspaceRoot = path.resolve(testDir, '../..')
const reportsRoot = path.join(testDir, 'reports')
const host = '127.0.0.1'
const port = Number(process.env.MOBILE_E2E_PORT || 8765)
const MAX_OUTPUT_LENGTH = 64 * 1024
const MAX_REQUEST_LENGTH = 4 * 1024

// Only these scripts can be triggered from the browser. The API never accepts
// a command, path, or arbitrary process arguments from a request.
const testRegistry = Object.freeze({
  'AUTH-002': { label: '一键登录主流程', script: 'auth-002-univerify.main.mjs', reportDirectory: 'auth-002' },
  'AUTH-003': { label: '短信验证码登录主流程', script: 'auth-003-sms.main.mjs', reportDirectory: 'auth-003' },
  'AGREEMENT-001': { label: '包体内置协议', script: 'agreement-001-bundled-content.main.mjs', reportDirectory: 'agreement-001' },
  'CORE-001': { label: '登录后核心导航', script: 'core-001-navigation.main.mjs', reportDirectory: 'core-001' },
  'SELF-TEST-001': { label: '自测完整主流程', script: 'self-test-001-sms.main.mjs', reportDirectory: 'self-test-001' },
  'JOBS-001': { label: '岗位列表与详情', script: 'jobs-001-list-detail.main.mjs', reportDirectory: 'jobs-001' },
  'JOBS-002': { label: '岗位外部详情返回位置', script: 'jobs-002-external-return-scroll.main.mjs', reportDirectory: 'jobs-002' },
  'JOBS-003': { label: '岗位类型和省份筛选', script: 'jobs-003-filter.main.mjs', reportDirectory: 'jobs-003' },
  'PRACTICE-001': { label: '逐题练习答题入口', script: 'practice-001-start.main.mjs', reportDirectory: 'practice-001' },
  'PRACTICE-002': { label: '章节测试、考试与评测入口', script: 'practice-002-entry.main.mjs', reportDirectory: 'practice-002' },
  'PROFILE-001': { label: '个人头像上传与持久化', script: 'profile-001-avatar-upload.main.mjs', reportDirectory: 'profile-001' },
  'LAYOUT-001': { label: '固定导航与安全区', script: 'layout-001-fixed-navigation.main.mjs', reportDirectory: 'layout-001' },
})

const state = {
  activeRun: null,
  runs: [],
  latestReports: {},
  device: { updatedAt: '', devices: [] },
}

function redact(value) {
  return String(value)
    .replace(/(access[_-]?token|openid|auth[_-]?token|secret|password)["'\s:=]+[^,\s}\]]+/gi, '$1=<redacted>')
    .replace(/\b1\d{10}\b/g, '<phone-redacted>')
}

function appendOutput(run, value) {
  const next = `${run.output}${redact(value)}`
  run.output = next.length > MAX_OUTPUT_LENGTH ? next.slice(-MAX_OUTPUT_LENGTH) : next
  run.updatedAt = new Date().toISOString()
}

function serializeRun(run) {
  if (!run) return null
  return {
    id: run.id,
    testId: run.testId,
    label: run.label,
    status: run.status,
    startedAt: run.startedAt,
    finishedAt: run.finishedAt || null,
    exitCode: run.exitCode ?? null,
    error: run.error || '',
    output: run.output,
    report: run.report || null,
    scriptCount: run.scriptCount || 1,
    updatedAt: run.updatedAt,
  }
}

function responseJson(response, statusCode, body) {
  response.writeHead(statusCode, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  })
  response.end(`${JSON.stringify(body)}\n`)
}

function responseText(response, statusCode, body) {
  response.writeHead(statusCode, {
    'content-type': 'text/plain; charset=utf-8',
    'cache-control': 'no-store',
  })
  response.end(body)
}

function isLocalRequest(request) {
  const address = request.socket.remoteAddress || ''
  return address === '127.0.0.1' || address === '::1' || address === '::ffff:127.0.0.1'
}

async function readJsonBody(request) {
  const chunks = []
  let length = 0
  for await (const chunk of request) {
    length += chunk.length
    if (length > MAX_REQUEST_LENGTH) throw new Error('请求体过大')
    chunks.push(chunk)
  }
  if (!chunks.length) return {}
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'))
  } catch {
    throw new Error('请求不是有效 JSON')
  }
}

async function getConnectedDevices() {
  const now = Date.now()
  const previousAt = Date.parse(state.device.updatedAt || 0)
  if (Number.isFinite(previousAt) && now - previousAt < 2_000) return state.device.devices
  try {
    const { stdout } = await execFileAsync(config.device.adbPath, ['devices'], {
      windowsHide: true,
      maxBuffer: 1024 * 1024,
      timeout: 5_000,
    })
    state.device = {
      updatedAt: new Date().toISOString(),
      devices: stdout.toString().split(/\r?\n/).slice(1)
        .map((line) => line.trim().split(/\s+/))
        .filter(([serial, status]) => serial && status)
        .map(([serial, status]) => ({ serial, status })),
    }
  } catch (error) {
    state.device = {
      updatedAt: new Date().toISOString(),
      devices: [{ serial: 'ADB 不可用', status: redact(error.message) }],
    }
  }
  return state.device.devices
}

async function stopExistingAppium() {
  if (!config.appium.restartExisting || process.platform !== 'win32') return
  const { stdout } = await execFileAsync('netstat', ['-ano', '-p', 'tcp'], {
    windowsHide: true,
    maxBuffer: 1024 * 1024,
  }).catch(() => ({ stdout: '' }))
  const pids = new Set()
  for (const line of stdout.toString().split(/\r?\n/)) {
    const columns = line.trim().split(/\s+/)
    if (columns[0] !== 'TCP' || columns[3] !== 'LISTENING') continue
    if (!columns[1].endsWith(`:${config.appium.port}`)) continue
    if (/^\d+$/.test(columns[4])) pids.add(columns[4])
  }
  for (const pid of pids) {
    appendOutput(state.activeRun, `[控制台] 清理 4723 上残留的 Appium 进程：${pid}\n`)
    await execFileAsync('taskkill', ['/pid', pid, '/t', '/f'], {
      windowsHide: true,
    }).catch(() => {})
  }
  if (pids.size) await new Promise((resolve) => setTimeout(resolve, 500))
}

async function findLatestReport(testId) {
  const definition = testRegistry[testId]
  if (!definition) return null
  const directory = path.join(reportsRoot, definition.reportDirectory)
  let entries
  try {
    entries = await fs.readdir(directory, { withFileTypes: true })
  } catch {
    return null
  }

  const candidates = []
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const reportPath = path.join(directory, entry.name, 'result.json')
    try {
      const [raw, stat] = await Promise.all([fs.readFile(reportPath, 'utf8'), fs.stat(reportPath)])
      const result = JSON.parse(raw)
      candidates.push({
        testId,
        status: result.status || 'unknown',
        startedAt: result.startedAt || null,
        finishedAt: result.finishedAt || stat.mtime.toISOString(),
        reportUrl: `/reports/${encodeURIComponent(definition.reportDirectory)}/${encodeURIComponent(entry.name)}/result.json`,
        directoryUrl: `/reports/${encodeURIComponent(definition.reportDirectory)}/${encodeURIComponent(entry.name)}/`,
        mtimeMs: stat.mtimeMs,
      })
    } catch {}
  }
  candidates.sort((left, right) => right.mtimeMs - left.mtimeMs)
  const latest = candidates[0] || null
  if (latest) delete latest.mtimeMs
  return latest
}

async function refreshLatestReport(testId) {
  const latest = await findLatestReport(testId)
  if (latest) state.latestReports[testId] = latest
  else delete state.latestReports[testId]
  return latest
}

async function refreshAllReports() {
  await Promise.all(Object.keys(testRegistry).map((testId) => refreshLatestReport(testId)))
}

function buildStatePayload() {
  return {
    serverTime: new Date().toISOString(),
    device: state.device,
    activeRun: serializeRun(state.activeRun),
    runs: state.runs.slice(0, 12).map(serializeRun),
    latestReports: state.latestReports,
    tests: Object.fromEntries(Object.entries(testRegistry).map(([testId, definition]) => [testId, {
      testId,
      label: definition.label,
    }])),
  }
}

async function startRun(testId) {
  const definition = testRegistry[testId]
  if (!definition) throw new Error(`未知测试编号：${testId}`)
  if (state.activeRun?.status === 'running') {
    const error = new Error(`设备正在执行 ${state.activeRun.testId}，请等待当前测试结束`)
    error.code = 'RUN_IN_PROGRESS'
    throw error
  }

  const startedAt = new Date().toISOString()
  const run = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    testId,
    label: definition.label,
    status: 'running',
    startedAt,
    output: `[控制台] 已启动 ${testId}：${definition.label}\n`,
    updatedAt: startedAt,
    report: null,
    scriptCount: 1,
  }
  state.activeRun = run
  state.runs.unshift(run)
  state.runs = state.runs.slice(0, 12)

  await stopExistingAppium()

  const scriptPath = path.join(testDir, 'scripts', definition.script)
  const child = spawn(process.execPath, [scriptPath], {
    cwd: workspaceRoot,
    windowsHide: true,
    env: process.env,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  run.child = child
  child.stdout.on('data', (chunk) => appendOutput(run, chunk.toString()))
  child.stderr.on('data', (chunk) => appendOutput(run, chunk.toString()))
  child.on('error', (error) => appendOutput(run, `[控制台] 进程启动失败：${error.message}\n`))
  child.on('close', async (exitCode, signal) => {
    run.exitCode = exitCode
    run.finishedAt = new Date().toISOString()
    run.status = exitCode === 0 ? 'passed' : 'failed'
    if (signal) run.error = `测试进程被 ${signal} 终止`
    if (exitCode !== 0 && !run.error) run.error = `脚本退出码：${exitCode}`
    appendOutput(run, `[控制台] ${testId} 已结束，${run.status === 'passed' ? '通过' : '失败'}。\n`)
    const latest = await refreshLatestReport(testId)
    if (latest && Date.parse(latest.finishedAt || latest.startedAt || 0) >= Date.parse(startedAt) - 2_000) {
      run.report = latest
      if (latest.status === 'failed') run.status = 'failed'
    }
    delete run.child
    if (state.activeRun?.id === run.id) state.activeRun = null
  })
  return run
}

const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.xml': 'application/xml; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.log': 'text/plain; charset=utf-8',
}

async function serveReport(response, pathname) {
  const encodedPath = pathname.slice('/reports/'.length)
  const relativePath = decodeURIComponent(encodedPath).replace(/\\/g, '/')
  const candidate = path.resolve(reportsRoot, relativePath)
  if (!candidate.startsWith(`${reportsRoot}${path.sep}`)) {
    responseText(response, 403, 'Forbidden')
    return
  }
  let stat
  try {
    stat = await fs.stat(candidate)
  } catch {
    responseText(response, 404, 'Not found')
    return
  }
  if (stat.isDirectory()) {
    const suffix = pathname.endsWith('/') ? 'result.json' : '/result.json'
    response.writeHead(302, { location: `${pathname}${suffix}` })
    response.end()
    return
  }
  response.writeHead(200, {
    'content-type': mimeTypes[path.extname(candidate).toLowerCase()] || 'application/octet-stream',
    'cache-control': 'no-store',
  })
  createReadStream(candidate).pipe(response)
}

const server = createServer(async (request, response) => {
  if (!isLocalRequest(request)) {
    responseText(response, 403, 'This test console only accepts local requests.')
    return
  }

  const url = new URL(request.url || '/', `http://${host}:${port}`)
  try {
    if (request.method === 'GET' && url.pathname === '/api/state') {
      await getConnectedDevices()
      responseJson(response, 200, buildStatePayload())
      return
    }
    if (request.method === 'POST' && url.pathname === '/api/runs') {
      const body = await readJsonBody(request)
      const run = await startRun(body.testId)
      responseJson(response, 202, { run: serializeRun(run) })
      return
    }
    if (request.method === 'GET' && url.pathname.startsWith('/reports/')) {
      await serveReport(response, url.pathname)
      return
    }
    if (request.method === 'GET' && (url.pathname === '/' || url.pathname === '/index.html')) {
      const index = await fs.readFile(path.join(testDir, 'index.html'))
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' })
      response.end(index)
      return
    }
    responseText(response, 404, 'Not found')
  } catch (error) {
    const statusCode = error.code === 'RUN_IN_PROGRESS' ? 409 : 400
    responseJson(response, statusCode, { error: redact(error.message) })
  }
})

await refreshAllReports()
server.listen(port, host, () => {
  console.log(`Android 真机测试控制台已启动：http://${host}:${port}/`)
})

function shutdown() {
  if (state.activeRun?.child) state.activeRun.child.kill('SIGTERM')
  server.close(() => process.exit(0))
}

process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
