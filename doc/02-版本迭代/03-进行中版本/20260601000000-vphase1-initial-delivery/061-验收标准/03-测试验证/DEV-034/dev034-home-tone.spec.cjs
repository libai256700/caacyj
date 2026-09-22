const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')

const projectRoot = process.cwd()
const requireFromProject = createRequire(path.join(projectRoot, 'package.json'))
const { chromium } = requireFromProject('playwright')
const outputDir = __dirname
const baseUrl = 'http://127.0.0.1:5173/yunjikeji/#'
const baselinePath = path.resolve(outputDir, '../DEV-033/playwright-results.json')
const baseline = JSON.parse(fs.readFileSync(baselinePath, 'utf8'))
const viewports = [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
]

const expectedTexts = [
  '打卡', '273', 'Hi 我是Tony!', '你的智能创作AI助手',
  '考题测试', '考题自测', '考题测评', '错题测评',
  '常用功能', '岗位查询', '联系客服', '个人资料',
  '帮我查一下今天的预约', '帮我分析下今天的数据', '有什么想法尽管问我',
  '首页', 'AI助手', '我的',
]
const removedExactTexts = ['5:30', '回访话术', '知识库', '公众号', '图片生成', '数字分身']

const round = (value) => Math.round(value * 1000) / 1000
const close = (left, right, tolerance = 1) => Math.abs(left - right) <= tolerance

async function inspect(page) {
  return page.evaluate(({ expectedTexts, removedExactTexts }) => {
    const rect = (selector) => {
      const element = document.querySelector(selector)
      if (!element) return null
      const value = element.getBoundingClientRect()
      return {
        x: value.x, y: value.y, width: value.width, height: value.height,
        right: value.right, bottom: value.bottom,
      }
    }
    const bodyText = document.body.innerText
    const exactTexts = [...document.querySelectorAll('uni-text')].map((element) => element.textContent.trim())
    const phone = document.querySelector('.phone-screen')
    const pageRoot = document.querySelector('.preview-page')
    const nav = [...document.querySelectorAll('.bottom-nav .nav-item')].map((element) => {
      const value = element.getBoundingClientRect()
      return { text: element.innerText.trim(), x: value.x, width: value.width }
    })
    const images = [...document.querySelectorAll('.preview-page img')].map((image) => ({
      src: image.getAttribute('src'), complete: image.complete,
      naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight,
    }))
    const rects = {
      phone: rect('.phone-screen'),
      top: rect('.top-area'),
      reward: rect('.reward-row'),
      welcome: rect('.welcome-copy'),
      tony: rect('.tony'),
      create: rect('.create-panel'),
      xhs: rect('.xhs-card'),
      douyin: rect('.douyin-card'),
      moments: rect('.moments-card'),
      assistant: rect('.assistant-panel'),
      suggestions: rect('.suggestions'),
      ask: rect('.ask-box'),
      nav: rect('.bottom-nav'),
      owl: rect('.owl-ring'),
    }
    return {
      viewport: { width: innerWidth, height: innerHeight },
      expectedMissing: expectedTexts.filter((text) => !bodyText.includes(text)),
      removedTextPresent: removedExactTexts.filter((text) => exactTexts.includes(text)),
      removedCounts: {
        statusBar: document.querySelectorAll('.status-bar').length,
        signal: document.querySelectorAll('.signal').length,
        wifi: document.querySelectorAll('.wifi').length,
        battery: document.querySelectorAll('.battery').length,
        quickRow: document.querySelectorAll('.quick-row').length,
        quickItems: document.querySelectorAll('.quick-item').length,
      },
      counts: {
        creationCards: document.querySelectorAll('.creation-card').length,
        assistantCards: document.querySelectorAll('.assistant-card').length,
        suggestions: document.querySelectorAll('.suggestions > uni-view, .suggestions > view').length,
        navItems: nav.length,
        images: images.length,
      },
      backgrounds: {
        page: getComputedStyle(pageRoot).backgroundColor,
        phone: getComputedStyle(phone).backgroundImage,
        body: getComputedStyle(document.body).backgroundColor,
      },
      rects,
      topToCreateGap: rects.create.y - rects.top.bottom,
      createToAssistantGap: rects.assistant.y - rects.create.bottom,
      assistantToSuggestionsGap: rects.suggestions.y - rects.assistant.bottom,
      askToNavGap: rects.nav.y - rects.ask.bottom,
      robotClipBottom: rects.tony.bottom - rects.top.bottom,
      robotAspect: rects.tony.width / rects.tony.height,
      nav,
      navWidthSpread: nav.length
        ? Math.max(...nav.map((item) => item.width)) - Math.min(...nav.map((item) => item.width))
        : null,
      overflow: {
        documentScrollWidth: document.documentElement.scrollWidth,
        documentClientWidth: document.documentElement.clientWidth,
        bodyScrollWidth: document.body.scrollWidth,
      },
      images,
    }
  }, { expectedTexts, removedExactTexts })
}

function baselineChecks(actual, before) {
  const beforeRects = before.actual.rects
  const expectedTopReduction = 34
  const expectedQuickReduction = 62
  const expectedCombinedShift = expectedTopReduction + expectedQuickReduction
  const scaleX = actual.rects.tony.width / beforeRects.tony.width
  const scaleY = actual.rects.tony.height / beforeRects.tony.height
  return {
    topReducedBy34: close(beforeRects.hero.height - actual.rects.top.height, expectedTopReduction),
    createStarts34Earlier: close(beforeRects.createPanel.y - actual.rects.create.y, expectedTopReduction),
    createReducedByQuickRow62: close(beforeRects.createPanel.height - actual.rects.create.height, expectedQuickReduction),
    cardsKeepDimensions:
      close(actual.rects.xhs.width, beforeRects.xhsCard.width) &&
      close(actual.rects.xhs.height, beforeRects.xhsCard.height) &&
      close(actual.rects.douyin.width, beforeRects.douyinCard.width) &&
      close(actual.rects.douyin.height, beforeRects.douyinCard.height) &&
      close(actual.rects.moments.width, beforeRects.momentsCard.width) &&
      close(actual.rects.moments.height, beforeRects.momentsCard.height),
    downstreamMovesBy96:
      close(beforeRects.assistantPanel.y - actual.rects.assistant.y, expectedCombinedShift) &&
      close(beforeRects.suggestions.y - actual.rects.suggestions.y, expectedCombinedShift) &&
      close(beforeRects.askBox.y - actual.rects.ask.y, expectedCombinedShift),
    downstreamDimensionsUnchanged:
      close(actual.rects.assistant.width, beforeRects.assistantPanel.width) &&
      close(actual.rects.assistant.height, beforeRects.assistantPanel.height) &&
      close(actual.rects.suggestions.width, beforeRects.suggestions.width) &&
      close(actual.rects.suggestions.height, beforeRects.suggestions.height) &&
      close(actual.rects.ask.width, beforeRects.askBox.width) &&
      close(actual.rects.ask.height, beforeRects.askBox.height),
    bottomNavUnchanged:
      close(actual.rects.nav.y, beforeRects.bottomNav.y) &&
      close(actual.rects.nav.width, beforeRects.bottomNav.width) &&
      close(actual.rects.nav.height, beforeRects.bottomNav.height) &&
      close(actual.rects.owl.width, beforeRects.owl.width) &&
      close(actual.rects.owl.height, beforeRects.owl.height),
    robotScaledProportionally: Math.abs(scaleX - scaleY) <= 0.01,
    robotClipUnchanged: close(actual.robotClipBottom, beforeRects.tony.bottom - beforeRects.hero.bottom),
    scale: { x: round(scaleX), y: round(scaleY) },
  }
}

async function capture(browser, viewport) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 })
  const consoleErrors = []
  const pageErrors = []
  const failedRequests = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('requestfailed', (request) => failedRequests.push({
    url: request.url(), error: request.failure()?.errorText || 'unknown',
  }))

  const response = await page.goto(`${baseUrl}/pages/home`, { waitUntil: 'networkidle', timeout: 30000 })
  await page.locator('.phone-screen').waitFor({ state: 'visible' })
  await page.screenshot({ path: path.join(outputDir, `home-${viewport.width}x${viewport.height}.png`) })
  const actual = await inspect(page)
  const before = baseline.results.find((result) =>
    result.viewport.width === viewport.width && result.viewport.height === viewport.height)
  const comparison = baselineChecks(actual, before)
  const comparisonPassed = Object.entries(comparison)
    .filter(([key]) => key !== 'scale')
    .every(([, value]) => value === true)
  const checks = {
    httpOk: response?.ok() === true,
    targetDomRemoved: Object.values(actual.removedCounts).every((value) => value === 0),
    targetTextsRemoved: actual.removedTextPresent.length === 0,
    expectedContentPreserved: actual.expectedMissing.length === 0,
    contentCountsPreserved:
      actual.counts.creationCards === 3 && actual.counts.assistantCards === 3 &&
      actual.counts.suggestions === 2 && actual.counts.navItems === 3 && actual.counts.images === 5,
    exactWarmBackground:
      actual.backgrounds.page === 'rgb(245, 240, 234)' &&
      actual.backgrounds.body === 'rgb(245, 240, 234)' &&
      actual.backgrounds.phone === 'linear-gradient(rgb(247, 161, 106) 0px, rgb(248, 220, 200) 33%, rgb(245, 240, 234) 76%)',
    contentMovesNaturally: actual.topToCreateGap === 0 && actual.createToAssistantGap === 10 && actual.assistantToSuggestionsGap === 10,
    robotAndCardsNotClipped:
      actual.robotClipBottom <= 7.1 && actual.rects.xhs.bottom <= actual.rects.create.bottom &&
      actual.rects.douyin.bottom <= actual.rects.create.bottom && actual.rects.moments.bottom <= actual.rects.create.bottom,
    threeEqualNavAreas: actual.nav.length === 3 && actual.navWidthSpread <= 1,
    noHorizontalOverflow:
      actual.overflow.documentScrollWidth <= actual.overflow.documentClientWidth &&
      actual.overflow.bodyScrollWidth <= viewport.width,
    imagesLoaded: actual.images.every((image) => image.complete && image.naturalWidth > 0 && image.naturalHeight > 0),
    baselineComparisonPassed: comparisonPassed,
    noBrowserErrors: consoleErrors.length === 0 && pageErrors.length === 0 && failedRequests.length === 0,
  }

  await page.close()
  return {
    viewport,
    status: response?.status() || null,
    passed: Object.values(checks).every(Boolean),
    checks,
    actual,
    baselineComparison: comparison,
    consoleErrors,
    pageErrors,
    failedRequests,
  }
}

async function verifyNavigation(browser) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 })
  await page.goto(`${baseUrl}/pages/home`, { waitUntil: 'networkidle', timeout: 30000 })
  await page.evaluate(() => {
    window.__dev034Calls = []
    uni.navigateTo = ({ url }) => { window.__dev034Calls.push({ method: 'navigateTo', url }); return Promise.resolve({}) }
    uni.reLaunch = ({ url }) => { window.__dev034Calls.push({ method: 'reLaunch', url }); return Promise.resolve({}) }
  })
  const selectors = [
    '.xhs-card', '.douyin-card', '.moments-card',
    '.assistant-card:nth-child(1)', '.assistant-card:nth-child(2)', '.assistant-card:nth-child(3)',
    '.nav-ai', '.bottom-nav .nav-item:nth-child(3)',
  ]
  for (const selector of selectors) await page.locator(selector).click()
  const calls = await page.evaluate(() => window.__dev034Calls)
  await page.close()
  const expected = [
    { method: 'reLaunch', url: '/pages/center' },
    { method: 'navigateTo', url: '/pages/practice' },
    { method: 'navigateTo', url: '/pages/practice' },
    { method: 'navigateTo', url: '/pages/jobs' },
    { method: 'navigateTo', url: '/pages/service/customer-service-chat?conversationId=default' },
    { method: 'reLaunch', url: '/pages/profile' },
    { method: 'reLaunch', url: '/pages/center' },
    { method: 'reLaunch', url: '/pages/profile' },
  ]
  return { calls, expected, passed: JSON.stringify(calls) === JSON.stringify(expected) }
}

;(async () => {
  fs.mkdirSync(outputDir, { recursive: true })
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  const results = []
  for (const viewport of viewports) results.push(await capture(browser, viewport))
  const navigation = await verifyNavigation(browser)
  await browser.close()
  const output = {
    generatedAt: new Date().toISOString(),
    command: 'pnpm exec node <DEV-034>/dev034-home-tone.spec.cjs',
    allPassed: results.every((result) => result.passed) && navigation.passed,
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
