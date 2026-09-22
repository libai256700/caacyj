const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd()] }))

const baseUrl = process.env.DEV039_BASE_URL || 'http://127.0.0.1:5173/yunjikeji/'
const evidenceDir = __dirname
const baselinePath = path.join(evidenceDir, '..', 'DEV-038', 'playwright-results.json')
const baseline = JSON.parse(fs.readFileSync(baselinePath, 'utf8'))
const viewports = [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 }
]
const results = {
  fixture: '确定性视觉夹具：仅 Playwright 上下文设置登录存储并拦截练习接口，不写入产品源码。',
  baseline: 'DEV-038/playwright-results.json single geometry',
  startedAt: new Date().toISOString(),
  baseUrl,
  viewports: [],
  errors: []
}

const sessionValue = JSON.stringify({
  type: 'object',
  data: {
    userId: 999,
    phone: '13800000000',
    name: 'DEV-039',
    role: '测试',
    token: 'dev039-token',
    refreshToken: '',
    expiresTime: '2099-01-01T00:00:00Z',
    loggedInAt: new Date().toISOString()
  }
})

const question = {
  id: 'single-001',
  type: '单选题',
  title: '目前管户中，熟客（指了解除年龄和我行资产情况以外的客户信息）占比多少？',
  stem: '请选择最符合实际情况的一项。',
  score: 5,
  options: [
    { id: 'A', label: 'A', content: '10%（含）以下' },
    { id: 'B', label: 'B', content: '10% - 30%（含）' },
    { id: 'C', label: 'C', content: '30% - 50%（含）' },
    { id: 'D', label: 'D', content: '50%以上' }
  ]
}

const writeResults = () => {
  fs.writeFileSync(path.join(evidenceDir, 'playwright-results.json'), `${JSON.stringify(results, null, 2)}\n`, 'utf8')
}

const createHarness = async (browser, viewport) => {
  const context = await browser.newContext({ viewport, isMobile: true, hasTouch: true, deviceScaleFactor: 1 })
  await context.addInitScript(({ value }) => localStorage.setItem('yunjikeji-user-session', value), { value: sessionValue })
  const page = await context.newPage()
  const pageErrors = []
  const consoleErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  await page.route('**/app-api/yj/practices/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'GET' && url.pathname.endsWith('/question')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          data: {
            practiceId: 'practice-039',
            sessionId: 'session-039',
            mode: 'standard',
            currentIndex: 0,
            totalQuestions: 12,
            answeredCount: 0,
            correctCount: 0,
            progressPercent: 8,
            question
          }
        })
      })
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ code: 404, msg: 'DEV-039 unexpected route' }) })
  })
  const target = `${baseUrl}?dev039=${Date.now()}#/pages/practice/answer?id=practice-039&sessionId=session-039&mode=standard`
  await page.goto(target, { waitUntil: 'domcontentloaded' })
  await page.locator('.question-card').waitFor({ state: 'visible', timeout: 10000 })
  return { context, page, pageErrors, consoleErrors }
}

const collectLayout = async (page) => page.evaluate(() => {
  const rect = (selector) => {
    const element = document.querySelector(selector)
    if (!element) return null
    const value = element.getBoundingClientRect()
    return {
      left: value.left,
      top: value.top,
      right: value.right,
      bottom: value.bottom,
      width: value.width,
      height: value.height
    }
  }
  return {
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    documentScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    card: rect('.answer-card-scroll'),
    layer: rect('.answer-card-stage__layer'),
    illustration: rect('.answer-hero__illustration'),
    actions: rect('.answer-actions'),
    primary: rect('.answer-actions__primary'),
    options: [...document.querySelectorAll('.question-options__item')].map((element) => {
      const value = element.getBoundingClientRect()
      return {
        left: value.left,
        top: value.top,
        right: value.right,
        bottom: value.bottom,
        width: value.width,
        height: value.height
      }
    }),
    pageBackground: getComputedStyle(document.querySelector('.answer-page')).backgroundColor,
    rootBackground: getComputedStyle(document.documentElement).backgroundColor,
    gradient: getComputedStyle(document.querySelector('.answer-page__bg')).backgroundImage
  }
})

const compareRect = (actual, expected, label) => {
  assert(actual, `${label} missing`)
  assert(expected, `${label} baseline missing`)
  for (const key of ['left', 'top', 'right', 'bottom', 'width', 'height']) {
    assert(Math.abs(actual[key] - expected[key]) <= 0.05, `${label}.${key} changed: ${actual[key]} vs ${expected[key]}`)
  }
}

const compareGeometry = (actual, expected) => {
  for (const key of ['card', 'layer', 'illustration', 'actions', 'primary']) {
    compareRect(actual[key], expected[key], key)
  }
  assert.equal(actual.options.length, expected.options.length)
  actual.options.forEach((item, index) => compareRect(item, expected.options[index], `options[${index}]`))
}

;(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.DEV039_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  })
  try {
    for (const viewport of viewports) {
      const harness = await createHarness(browser, viewport)
      const layout = await collectLayout(harness.page)
      const baselineEntry = baseline.viewports.find((item) => item.viewport.width === viewport.width && item.viewport.height === viewport.height)
      assert(baselineEntry, `DEV-038 baseline missing for ${viewport.width}x${viewport.height}`)
      compareGeometry(layout, baselineEntry.single)
      assert.equal(layout.documentScrollWidth, viewport.width)
      assert.equal(layout.bodyScrollWidth, viewport.width)
      assert.equal(layout.pageBackground, 'rgb(245, 240, 234)')
      assert(layout.gradient.includes('rgb(247, 161, 106) 0%'))
      assert(layout.gradient.includes('rgb(239, 125, 59) 27%'))
      assert(layout.gradient.includes('rgb(248, 220, 200) 61%'))
      assert(layout.gradient.includes('rgb(245, 240, 234) 100%'))
      assert.equal((layout.gradient.match(/%/g) || []).length, 4)
      assert.equal(layout.gradient.includes('rgb(243, 173, 123)'), false)
      assert.equal(harness.pageErrors.length, 0)
      assert.equal(harness.consoleErrors.length, 0)
      await harness.page.screenshot({ path: path.join(evidenceDir, `answer-warm-${viewport.width}x${viewport.height}.png`) })
      results.viewports.push({
        viewport,
        layout,
        baselineGeometry: baselineEntry.single,
        pageErrors: harness.pageErrors,
        consoleErrors: harness.consoleErrors
      })
      await harness.context.close()
    }
    results.status = 'passed'
  } catch (error) {
    results.status = 'failed'
    results.errors.push(error?.stack || String(error))
    throw error
  } finally {
    results.finishedAt = new Date().toISOString()
    writeResults()
    await browser.close()
  }
})()
