const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const repoRoot = path.resolve(__dirname, '../../../../../../..')
const appDir = path.join(repoRoot, 'code/develop/yunjikeji')
const jobsSourcePath = path.join(appDir, 'src/pages/jobs.vue')
const { chromium } = require(require.resolve('playwright', { paths: [appDir] }))

const baseUrl = process.env.DEV061_BASE_URL || 'http://127.0.0.1:5173/yunjikeji/'
const chromePath = process.env.DEV061_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const evidenceDir = __dirname
const results = {
  fixture: 'Playwright route 提供确定性岗位列表与 /app-api/yj/student-audit/my 响应；只驱动真实 jobs.vue 和正式弹框组件。',
  startedAt: new Date().toISOString(),
  baseUrl,
  checks: [],
  failures: [],
  browserErrors: []
}

const sessionValue = JSON.stringify({
  type: 'object',
  data: {
    userId: 9061,
    phone: '13800000061',
    name: 'DEV-061',
    role: '学员',
    token: 'dev061-token',
    refreshToken: '',
    expiresTime: '2099-01-01T00:00:00Z',
    loggedInAt: new Date().toISOString()
  }
})

const makeJob = (detailUrl = 'https://jobs.example.com/positions/61?source=app') => ({
  id: 61,
  name: '无人机飞手',
  companyName: 'DEV-061 招聘企业',
  sourceCode: 'fixture',
  externalPostId: 'dev061',
  salaryRange: '8k-12k',
  workArea: '杭州',
  publishDate: '2026-08-18',
  detailUrl,
  status: true,
  createTime: '2026-08-18T00:00:00Z'
})

const writeResults = () => {
  fs.writeFileSync(path.join(evidenceDir, 'playwright-results.json'), `${JSON.stringify(results, null, 2)}\n`, 'utf8')
}

const createHarness = async (browser, options = {}) => {
  const {
    auditData = null,
    auditStatusCode = 200,
    auditDelay = 0,
    detailUrl = 'https://jobs.example.com/positions/61?source=app',
    runtime = 'h5',
    viewport = { width: 390, height: 844 },
    name = 'scenario'
  } = options
  const context = await browser.newContext({ viewport, isMobile: true, hasTouch: true, deviceScaleFactor: 1 })
  await context.addInitScript(({ value }) => localStorage.setItem('yunjikeji-user-session', value), { value: sessionValue })
  const page = await context.newPage()
  page.setDefaultTimeout(2000)
  const requests = []
  const pageErrors = []
  const requestFailures = []

  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('requestfailed', (request) => requestFailures.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText || 'failed'}`))

  await page.route('**/app-api/yj/posts**', async (route) => {
    const url = new URL(route.request().url())
    requests.push({ method: route.request().method(), path: url.pathname })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, data: { list: [makeJob(detailUrl)], total: 1 } })
    })
  })

  await page.route('**/app-api/yj/student-audit/my**', async (route) => {
    const url = new URL(route.request().url())
    requests.push({ method: route.request().method(), path: url.pathname })
    if (auditDelay) await new Promise((resolve) => setTimeout(resolve, auditDelay))
    await route.fulfill({
      status: auditStatusCode,
      contentType: 'application/json',
      body: JSON.stringify(auditStatusCode >= 400
        ? { code: auditStatusCode, msg: '组织申请状态加载失败' }
        : { code: 0, data: auditData })
    })
  })

  await page.goto(`${baseUrl}?dev061=${Date.now()}-${name}#/pages/jobs`, { waitUntil: 'domcontentloaded' })
  await page.getByText('查看详情', { exact: true }).waitFor({ state: 'visible', timeout: 10000 })
  await page.evaluate(({ runtimeMode }) => {
    window.__dev061 = { open: [], clipboard: [], toast: [], navigateTo: [] }
    window.uni.showToast = (options) => { window.__dev061.toast.push(options.title); options.success?.({}) }
    window.uni.navigateTo = (options) => { window.__dev061.navigateTo.push(options.url); options.success?.({}) }
    window.uni.setClipboardData = (options) => { window.__dev061.clipboard.push(options.data); options.success?.({}) }
    window.open = runtimeMode === 'clipboard'
      ? undefined
      : (url, target) => { window.__dev061.open.push({ url, target }); return null }
    if (runtimeMode === 'plus') {
      window.plus = { runtime: { openURL: (url) => window.__dev061.open.push({ url, target: 'plus' }) } }
    } else {
      delete window.plus
    }
  }, { runtimeMode: runtime })

  return { context, page, requests, pageErrors, requestFailures, name, viewport }
}

const auditRequests = (harness) => harness.requests.filter((item) => item.path.endsWith('/app-api/yj/student-audit/my'))
const browserState = (harness) => harness.page.evaluate(() => window.__dev061)

const assertNoBrowserErrors = (harness) => {
  const errors = [...harness.pageErrors, ...harness.requestFailures]
  results.browserErrors.push({ scenario: harness.name, errors })
  assert.deepEqual(errors, [], `${harness.name} browser errors must be empty`)
}

const clickDetail = (page) => page.getByText('查看详情', { exact: true }).click()

const testBlocked = async (browser, auditData, name) => {
  const harness = await createHarness(browser, { auditData, name })
  await clickDetail(harness.page)
  await harness.page.waitForTimeout(450)
  const state = await browserState(harness)
  assert.equal(auditRequests(harness).length, 1, `${name} must request the real audit endpoint once`)
  assert.equal(state.open.length + state.clipboard.length, 0, `${name} must block the external detail`)
  assert.equal(await harness.page.locator('.binding-required-dialog').count(), 1, `${name} must render one formal dialog`)

  await harness.page.locator('.detail-button').evaluate((element) => element.click())
  await harness.page.waitForTimeout(100)
  assert.equal(auditRequests(harness).length, 1, `${name} visible dialog must suppress another audit request`)
  assert.equal(await harness.page.locator('.binding-required-dialog').count(), 1, `${name} must not stack dialogs`)
  await harness.page.locator('.binding-required-dialog__close').click()
  assert.equal(await harness.page.locator('.binding-required-dialog').count(), 0, `${name} close must hide dialog`)
  assertNoBrowserErrors(harness)
  results.checks.push({ scenario: name, auditRequests: 1, externalCalls: 0, dialogInstances: 1, close: true })
  await harness.context.close()
}

const testDelayedDoubleClick = async (browser) => {
  const harness = await createHarness(browser, { auditData: null, auditDelay: 300, name: 'delayedDoubleClick' })
  await harness.page.locator('.detail-button').evaluate((element) => { element.click(); element.click() })
  await harness.page.waitForTimeout(100)
  assert.equal(auditRequests(harness).length, 1, 'pending double click must issue exactly one audit request')
  await harness.page.waitForTimeout(350)
  assert.equal(await harness.page.locator('.binding-required-dialog').count(), 1)
  assertNoBrowserErrors(harness)
  results.checks.push({ scenario: 'delayedDoubleClick', auditRequests: 1, dialogInstances: 1 })
  await harness.context.close()
}

const testBoundRuntime = async (browser, runtime, detailUrl, expectedUrl = detailUrl) => {
  const harness = await createHarness(browser, { auditData: { auditStatus: 2 }, runtime, detailUrl, name: `bound-${runtime}` })
  await clickDetail(harness.page)
  await harness.page.waitForTimeout(200)
  const state = await browserState(harness)
  assert.equal(auditRequests(harness).length, 1)
  assert.equal(await harness.page.locator('.binding-required-dialog').count(), 0)
  if (runtime === 'clipboard') {
    assert.deepEqual(state.clipboard, [expectedUrl])
    assert(state.toast.includes('链接已复制'))
  } else {
    assert.deepEqual(state.open, [{ url: expectedUrl, target: runtime === 'plus' ? 'plus' : '_blank' }])
  }
  assertNoBrowserErrors(harness)
  results.checks.push({ scenario: `bound-${runtime}`, auditRequests: 1, url: expectedUrl })
  await harness.context.close()
}

const testInvalidUrl = async (browser) => {
  const harness = await createHarness(browser, { auditData: { auditStatus: 2 }, detailUrl: 'invalid detail', name: 'invalidUrl' })
  await clickDetail(harness.page)
  await harness.page.waitForTimeout(200)
  const state = await browserState(harness)
  assert.equal(auditRequests(harness).length, 1)
  assert.equal(state.open.length + state.clipboard.length, 0)
  assert(state.toast.includes('暂无岗位详情链接'))
  results.checks.push({ scenario: 'invalidUrl', auditRequests: 1, originalToastPreserved: true })
  await harness.context.close()
}

const testAuditFailure = async (browser) => {
  const harness = await createHarness(browser, { auditStatusCode: 500, name: 'audit500' })
  await clickDetail(harness.page)
  await harness.page.waitForTimeout(300)
  const state = await browserState(harness)
  assert.equal(auditRequests(harness).length, 1)
  assert.equal(state.open.length + state.clipboard.length, 0)
  assert.equal(await harness.page.locator('.binding-required-dialog').count(), 0)
  assert(state.toast.some((item) => item.includes('组织申请状态加载失败')), '500 must show the existing audit error')
  assertNoBrowserErrors(harness)
  results.checks.push({ scenario: 'audit500', externalCalls: 0, dialogInstances: 0, errorToast: true })
  await harness.context.close()
}

const testDialogAction = async (browser, action, expectedUrl) => {
  const harness = await createHarness(browser, { auditData: null, name: `dialog-${action}` })
  await clickDetail(harness.page)
  await harness.page.waitForTimeout(200)
  await harness.page.locator(`.binding-required-dialog__${action}`).click()
  const state = await browserState(harness)
  assert.deepEqual(state.navigateTo, [expectedUrl])
  assert.equal(await harness.page.locator('.binding-required-dialog').count(), 0)
  results.checks.push({ scenario: `dialog-${action}`, navigateTo: expectedUrl, dialogClosed: true })
  await harness.context.close()
}

const testResponsiveDialog = async (browser, viewport) => {
  const harness = await createHarness(browser, { auditData: null, viewport, name: `responsive-${viewport.width}x${viewport.height}` })
  await clickDetail(harness.page)
  await harness.page.waitForTimeout(200)
  const layout = await harness.page.evaluate(() => {
    const panel = document.querySelector('.binding-required-dialog__panel')?.getBoundingClientRect()
    return {
      documentScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      panel: panel && { top: panel.top, right: panel.right, bottom: panel.bottom, left: panel.left }
    }
  })
  assert(layout.panel, 'dialog panel must exist')
  assert(layout.documentScrollWidth <= viewport.width + 1 && layout.bodyScrollWidth <= viewport.width + 1, 'dialog must not create horizontal overflow')
  assert(layout.panel.left >= 0 && layout.panel.right <= viewport.width + 1, 'dialog panel must stay within viewport width')
  assert(layout.panel.top >= 0 && layout.panel.bottom <= viewport.height + 1, 'dialog panel must stay within viewport height')
  await harness.page.screenshot({ path: path.join(evidenceDir, `binding-dialog-${viewport.width}x${viewport.height}.png`) })
  assertNoBrowserErrors(harness)
  results.checks.push({ scenario: 'responsiveDialog', viewport, layout })
  await harness.context.close()
}

const testSourceContract = () => {
  const source = fs.readFileSync(jobsSourcePath, 'utf8')
  assert(source.includes("import OrganizationBindingRequiredDialog from '@/components/OrganizationBindingRequiredDialog.vue'"), 'jobs.vue must directly import the formal dialog')
  assert(source.includes("import { fetchCurrentStudentAudit } from '@/services/customerAuth'"), 'jobs.vue must directly import the real audit service')
  assert.equal((source.match(/<OrganizationBindingRequiredDialog\b/g) || []).length, 1, 'template must contain exactly one formal dialog instance')
  for (const eventName of ['cancel', 'close', 'service', 'bind']) {
    assert(source.includes(`@${eventName}=`), `formal dialog must listen to ${eventName}`)
  }
  assert(source.includes('studentAudit?.auditStatus === 2'), 'only auditStatus === 2 may pass')
  assert(source.includes('plus.runtime.openURL(detailUrl)'))
  assert(source.includes("window.open(detailUrl, '_blank')"))
  assert(source.includes('uni.setClipboardData({'))
  results.checks.push({ scenario: 'sourceContract', directImports: true, dialogInstances: 1, events: ['cancel', 'close', 'service', 'bind'], runtimes: ['plus', 'h5', 'clipboard'] })
}

const runCheck = async (name, check) => {
  try {
    await check()
  } catch (error) {
    results.failures.push({ name, message: error?.message || String(error), stack: error?.stack || String(error) })
  }
}

;(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: chromePath })
  try {
    await runCheck('unbound-null', () => testBlocked(browser, null, 'unbound-null'))
    await runCheck('unbound-non2', () => testBlocked(browser, { auditStatus: 1 }, 'unbound-non2'))
    await runCheck('delayed-double-click', () => testDelayedDoubleClick(browser))
    await runCheck('bound-h5', () => testBoundRuntime(browser, 'h5', 'https://jobs.example.com/positions/61?source=app'))
    await runCheck('bound-plus', () => testBoundRuntime(browser, 'plus', 'jobs.example.com/positions/61', 'https://jobs.example.com/positions/61'))
    await runCheck('bound-clipboard', () => testBoundRuntime(browser, 'clipboard', 'https://jobs.example.com/positions/61?source=clipboard'))
    await runCheck('invalid-url', () => testInvalidUrl(browser))
    await runCheck('audit-500', () => testAuditFailure(browser))
    await runCheck('dialog-service', () => testDialogAction(browser, 'service', '/pages/service/customer-service-chat?conversationId=default'))
    await runCheck('dialog-confirm', () => testDialogAction(browser, 'confirm', '/pages/enterprise/organization-bind?entry=direct'))
    for (const viewport of [{ width: 360, height: 800 }, { width: 390, height: 844 }, { width: 430, height: 932 }]) {
      await runCheck(`responsive-${viewport.width}x${viewport.height}`, () => testResponsiveDialog(browser, viewport))
    }
    await runCheck('source-contract', testSourceContract)
  } finally {
    await browser.close()
    results.finishedAt = new Date().toISOString()
    results.status = results.failures.length ? 'failed' : 'passed'
    writeResults()
  }

  if (results.failures.length) {
    throw new Error(`DEV-061 failed ${results.failures.length} check(s): ${results.failures.map((item) => `${item.name}: ${item.message}`).join(' | ')}`)
  }
})()
