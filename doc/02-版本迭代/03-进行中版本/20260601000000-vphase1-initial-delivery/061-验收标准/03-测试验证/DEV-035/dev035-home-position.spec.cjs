const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')

const projectRoot = process.cwd()
const requireFromProject = createRequire(path.join(projectRoot, 'package.json'))
const { chromium } = requireFromProject('playwright')
const outputDir = __dirname
const baseline = JSON.parse(fs.readFileSync(path.resolve(outputDir, '../DEV-033/playwright-results.json'), 'utf8'))
const baseUrl = 'http://127.0.0.1:5173/yunjikeji/?dev035pw=1#'
const viewports = [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
]

const round = (value) => Math.round(value * 1000) / 1000
const close = (left, right, tolerance = 1) => Math.abs(left - right) <= tolerance

async function inspect(page) {
  return page.evaluate(() => {
    const rect = (selector) => {
      const element = document.querySelector(selector)
      if (!element) return null
      const value = element.getBoundingClientRect()
      return { x: value.x, y: value.y, width: value.width, height: value.height, right: value.right, bottom: value.bottom }
    }
    const textRect = (selector) => {
      const node = document.querySelector(selector)?.firstChild
      if (!node) return null
      const range = document.createRange()
      range.selectNodeContents(node)
      const value = range.getBoundingClientRect()
      return { x: value.x, y: value.y, width: value.width, height: value.height, right: value.right, bottom: value.bottom }
    }
    const overlap = (left, right) => left && right
      ? Math.max(0, Math.min(left.right, right.right) - Math.max(left.x, right.x)) *
        Math.max(0, Math.min(left.bottom, right.bottom) - Math.max(left.y, right.y))
      : null
    const phone = document.querySelector('.phone-screen')
    const pageRoot = document.querySelector('.preview-page')
    const title = textRect('.welcome-title')
    const subtitle = textRect('.welcome-subtitle')
    const tony = rect('.tony')
    return {
      removedCounts: {
        rewardRow: document.querySelectorAll('.reward-row').length,
        pill: document.querySelectorAll('.pill').length,
        statusBar: document.querySelectorAll('.status-bar').length,
        quickRow: document.querySelectorAll('.quick-row').length,
      },
      removedExactPresent: ['打卡', '273', '×', '5:30', '回访话术', '知识库', '公众号', '图片生成', '数字分身']
        .filter((text) => [...document.querySelectorAll('uni-text')].some((element) => element.textContent.trim() === text)),
      backgrounds: {
        page: getComputedStyle(pageRoot).backgroundColor,
        body: getComputedStyle(document.body).backgroundColor,
        phone: getComputedStyle(phone).backgroundImage,
      },
      rects: {
        top: rect('.top-area'),
        title,
        subtitle,
        tony,
        create: rect('.create-panel'),
        assistant: rect('.assistant-panel'),
        suggestions: rect('.suggestions'),
        ask: rect('.ask-box'),
        nav: rect('.bottom-nav'),
      },
      titleTonyOverlap: overlap(title, tony),
      subtitleTonyOverlap: overlap(subtitle, tony),
      overflow: {
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      },
    }
  })
}

async function verifyRoutes(page, enterprise) {
  await page.evaluate((enterprise) => {
    if (enterprise) uni.setStorageSync('yunjikeji-login-identity', 'enterprise')
    else uni.removeStorageSync('yunjikeji-login-identity')
  }, enterprise)
  await page.reload({ waitUntil: 'networkidle' })
  await page.evaluate(() => {
    window.__dev035Calls = []
    uni.navigateTo = ({ url }) => { window.__dev035Calls.push({ method: 'navigateTo', url }); return Promise.resolve({}) }
    uni.reLaunch = ({ url }) => { window.__dev035Calls.push({ method: 'reLaunch', url }); return Promise.resolve({}) }
  })
  const selectors = enterprise
    ? ['.assistant-card:nth-child(2)']
    : ['.xhs-card', '.assistant-card:nth-child(1)', '.assistant-card:nth-child(2)', '.assistant-card:nth-child(3)']
  for (const selector of selectors) await page.locator(selector).click()
  const calls = await page.evaluate(() => window.__dev035Calls)
  if (enterprise) await page.evaluate(() => uni.removeStorageSync('yunjikeji-login-identity'))
  return calls
}

;(async () => {
  fs.mkdirSync(outputDir, { recursive: true })
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  const results = []
  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport, deviceScaleFactor: 1 })
    const consoleErrors = []
    const pageErrors = []
    const failedRequests = []
    page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
    page.on('pageerror', (error) => pageErrors.push(error.message))
    page.on('requestfailed', (request) => failedRequests.push({ url: request.url(), error: request.failure()?.errorText || 'unknown' }))
    const response = await page.goto(`${baseUrl}/pages/home`, { waitUntil: 'networkidle', timeout: 30000 })
    await page.locator('.phone-screen').waitFor({ state: 'visible' })
    await page.screenshot({ path: path.join(outputDir, `home-${viewport.width}x${viewport.height}.png`) })
    const actual = await inspect(page)
    const before = baseline.results.find((item) => item.viewport.width === viewport.width && item.viewport.height === viewport.height).actual.rects
    const deltas = {
      createY: round(actual.rects.create.y - before.createPanel.y),
      tonyBottom: round(actual.rects.tony.bottom - before.tony.bottom),
      assistantY: round(actual.rects.assistant.y - before.assistantPanel.y),
      suggestionsY: round(actual.rects.suggestions.y - before.suggestions.y),
      askY: round(actual.rects.ask.y - before.askBox.y),
    }
    const checks = {
      httpOk: response?.ok() === true,
      removedCleanly: Object.values(actual.removedCounts).every((count) => count === 0) && actual.removedExactPresent.length === 0,
      warmBackgroundUnchanged:
        actual.backgrounds.page === 'rgb(245, 240, 234)' &&
        actual.backgrounds.body === 'rgb(245, 240, 234)' &&
        actual.backgrounds.phone === 'linear-gradient(rgb(247, 161, 106) 0px, rgb(248, 220, 200) 33%, rgb(245, 240, 234) 76%)',
      topMatchesDev033:
        close(actual.rects.top.height, before.hero.height) && close(actual.rects.create.y, before.createPanel.y),
      tonyMatchesDev033:
        close(actual.rects.tony.width, before.tony.width) && close(actual.rects.tony.height, before.tony.height) &&
        close(actual.rects.tony.bottom, before.tony.bottom),
      downstreamMatchesDev033:
        close(actual.rects.assistant.y, before.assistantPanel.y) &&
        close(actual.rects.suggestions.y, before.suggestions.y) &&
        close(actual.rects.ask.y, before.askBox.y),
      welcomeNotCovered: actual.titleTonyOverlap === 0 && actual.subtitleTonyOverlap === 0,
      noHorizontalOverflow: actual.overflow.scrollWidth <= actual.overflow.clientWidth,
      noBrowserErrors: consoleErrors.length === 0 && pageErrors.length === 0 && failedRequests.length === 0,
    }
    results.push({ viewport, passed: Object.values(checks).every(Boolean), checks, actual, baselineDeltas: deltas, consoleErrors, pageErrors, failedRequests })
    await page.close()
  }

  const routePage = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 })
  await routePage.goto(`${baseUrl}/pages/home`, { waitUntil: 'networkidle', timeout: 30000 })
  const defaultCalls = await verifyRoutes(routePage, false)
  const enterpriseCalls = await verifyRoutes(routePage, true)
  await routePage.close()
  await browser.close()

  const navigation = {
    defaultCalls,
    enterpriseCalls,
    expectedDefault: [
      { method: 'reLaunch', url: '/pages/center' },
      { method: 'navigateTo', url: '/pages/jobs' },
      { method: 'navigateTo', url: '/pages/service/customer-service-chat?conversationId=default' },
      { method: 'reLaunch', url: '/pages/profile' },
    ],
    expectedEnterprise: [{ method: 'navigateTo', url: '/pages/service/customer-service-chat?conversationId=default' }],
  }
  navigation.defaultPassed = JSON.stringify(navigation.defaultCalls) === JSON.stringify(navigation.expectedDefault)
  navigation.enterprisePassed = JSON.stringify(navigation.enterpriseCalls) === JSON.stringify(navigation.expectedEnterprise)

  const output = {
    generatedAt: new Date().toISOString(),
    command: 'pnpm exec node <DEV-035>/dev035-home-position.spec.cjs',
    allPassed: results.every((result) => result.passed) && navigation.defaultPassed && navigation.enterprisePassed,
    results,
  }
  fs.writeFileSync(path.join(outputDir, 'playwright-results.json'), `${JSON.stringify(output, null, 2)}\n`)
  fs.writeFileSync(path.join(outputDir, 'navigation-results.json'), `${JSON.stringify(navigation, null, 2)}\n`)
  console.log(JSON.stringify({ allPassed: output.allPassed, results, navigation }, null, 2))
  process.exitCode = output.allPassed ? 0 : 1
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
