const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')

const projectRoot = process.cwd()
const requireFromProject = createRequire(path.join(projectRoot, 'package.json'))
const { chromium } = requireFromProject('playwright')
const outputDir = __dirname
const baseUrl = 'http://127.0.0.1:5173/yunjikeji/#'
const viewports = [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
]

const expectedMappedTexts = [
  '考题测试', '考题自测', '考题测评', '错题测评',
  '常用功能', '岗位查询', '联系客服', '个人资料',
]
const expectedStableTexts = [
  '5:30', '打卡', '273', 'Hi 我是Tony!', '你的智能创作AI助手',
  '一键智能生成爆款文案', '小红书种草图文', '抖音视频脚本', '朋友圈每日问候',
  '回访话术', '知识库', '公众号', '图片生成', '数字分身',
  '一句话完成顾客营销与开单', '帮我查一下今天的预约',
  '帮我分析下今天的数据', '有什么想法尽管问我',
  '首页', 'AI助手', '我的',
]
const forbiddenTexts = [
  'AI创作', '小红书创作', '抖音创作', '朋友圈创作', '智能助理',
  '开单收银', '学习', '练口语', '会员',
]

const round = (value) => Math.round(value * 1000) / 1000

async function inspectPage(page) {
  return page.evaluate(({ expectedMappedTexts, expectedStableTexts, forbiddenTexts }) => {
    const text = document.body.innerText
    const rect = (selector) => {
      const element = document.querySelector(selector)
      if (!element) return null
      const value = element.getBoundingClientRect()
      return {
        x: value.x,
        y: value.y,
        width: value.width,
        height: value.height,
        right: value.right,
        bottom: value.bottom,
      }
    }
    const textRect = (selector) => {
      const element = document.querySelector(selector)
      const node = element?.firstChild
      if (!node) return null
      const range = document.createRange()
      range.selectNodeContents(node)
      const value = range.getBoundingClientRect()
      return {
        x: value.x,
        y: value.y,
        width: value.width,
        height: value.height,
        right: value.right,
        bottom: value.bottom,
      }
    }
    const navItems = [...document.querySelectorAll('.bottom-nav .nav-item')].map((element) => {
      const value = element.getBoundingClientRect()
      return { text: element.innerText.trim(), x: value.x, width: value.width }
    })
    const images = [...document.querySelectorAll('.preview-page img')].map((image) => ({
      src: image.getAttribute('src'),
      complete: image.complete,
      naturalWidth: image.naturalWidth,
      naturalHeight: image.naturalHeight,
    }))
    const mappedMissing = expectedMappedTexts.filter((value) => !text.includes(value))
    const stableMissing = expectedStableTexts.filter((value) => !text.includes(value))
    const forbiddenPresent = forbiddenTexts.filter((value) => text.includes(value))
    const assistant = rect('.assistant-panel')
    const suggestions = rect('.suggestions')
    const title = textRect('.moments-card .creation-title')
    const art = rect('.moments-art')
    const layoutBackground = getComputedStyle(document.querySelector('.phone-screen')).backgroundImage
    return {
      viewport: { width: innerWidth, height: innerHeight },
      mappedMissing,
      stableMissing,
      forbiddenPresent,
      counts: {
        statusBar: document.querySelectorAll('.status-bar').length,
        rewardPills: document.querySelectorAll('.reward-row .pill').length,
        creationCards: document.querySelectorAll('.creation-card').length,
        quickItems: document.querySelectorAll('.quick-item').length,
        assistantCards: document.querySelectorAll('.assistant-card').length,
        suggestions: document.querySelectorAll('.suggestions > uni-view, .suggestions > view').length,
        navItems: navItems.length,
        images: images.length,
      },
      rects: {
        phone: rect('.phone-screen'),
        hero: rect('.top-area'),
        tony: rect('.tony'),
        createPanel: rect('.create-panel'),
        xhsCard: rect('.xhs-card'),
        douyinCard: rect('.douyin-card'),
        momentsCard: rect('.moments-card'),
        quickRow: rect('.quick-row'),
        assistantPanel: assistant,
        suggestions,
        askBox: rect('.ask-box'),
        bottomNav: rect('.bottom-nav'),
        owl: rect('.owl-ring'),
        momentsTitle: title,
        momentsArt: art,
      },
      assistantToSuggestionsGap: assistant && suggestions ? suggestions.y - assistant.bottom : null,
      momentsTitleArtOverlap: title && art
        ? Math.max(0, Math.min(title.right, art.right) - Math.max(title.x, art.x)) *
          Math.max(0, Math.min(title.bottom, art.bottom) - Math.max(title.y, art.y))
        : null,
      navItems,
      navWidthSpread: navItems.length
        ? Math.max(...navItems.map((item) => item.width)) - Math.min(...navItems.map((item) => item.width))
        : null,
      overflow: {
        documentScrollWidth: document.documentElement.scrollWidth,
        documentClientWidth: document.documentElement.clientWidth,
        bodyScrollWidth: document.body.scrollWidth,
      },
      images,
      layoutBackground,
      owlSource: document.querySelector('.owl-ring img')?.getAttribute('src') || null,
      bodyTextLength: text.length,
    }
  }, { expectedMappedTexts, expectedStableTexts, forbiddenTexts })
}

function geometryDifferences(actual, reference) {
  const selectors = [
    'phone', 'hero', 'tony', 'createPanel', 'xhsCard', 'douyinCard', 'momentsCard',
    'quickRow', 'assistantPanel', 'suggestions', 'askBox', 'bottomNav', 'owl',
  ]
  const differences = []
  for (const selector of selectors) {
    const left = actual.rects[selector]
    const right = reference.rects[selector]
    if (!left || !right) {
      differences.push({ selector, reason: 'missing rect' })
      continue
    }
    for (const key of ['x', 'y', 'width', 'height']) {
      const delta = round(left[key] - right[key])
      if (Math.abs(delta) > 1) differences.push({ selector, property: key, delta })
    }
  }
  return differences
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
  const actual = await inspectPage(page)

  const referencePage = await browser.newPage({ viewport, deviceScaleFactor: 1 })
  const referenceErrors = []
  referencePage.on('console', (message) => {
    if (message.type() === 'error') referenceErrors.push(message.text())
  })
  const referenceResponse = await referencePage.goto(`${baseUrl}/pages/home-reference-preview`, {
    waitUntil: 'networkidle', timeout: 30000,
  })
  await referencePage.locator('.phone-screen').waitFor({ state: 'visible' })
  await referencePage.screenshot({ path: path.join(outputDir, `reference-${viewport.width}x${viewport.height}.png`) })
  const reference = await inspectPage(referencePage)
  const geometryDiffs = geometryDifferences(actual, reference)
  await referencePage.close()

  const expectedCounts = {
    statusBar: 1, rewardPills: 2, creationCards: 3, quickItems: 5,
    assistantCards: 3, suggestions: 2, navItems: 3, images: 5,
  }
  const checks = {
    httpOk: response?.ok() === true,
    mappedTextsComplete: actual.mappedMissing.length === 0,
    stableTextsComplete: actual.stableMissing.length === 0,
    forbiddenTextsAbsent: actual.forbiddenPresent.length === 0,
    countsComplete: Object.entries(expectedCounts).every(([key, value]) => actual.counts[key] === value),
    imagesLoaded: actual.images.every((image) => image.complete && image.naturalWidth > 0 && image.naturalHeight > 0),
    owlUsesBrandAsset: actual.owlSource?.includes('/static/brand/jixiangwu-logo.png') === true,
    noHorizontalOverflow:
      actual.overflow.documentScrollWidth <= actual.overflow.documentClientWidth &&
      actual.overflow.bodyScrollWidth <= viewport.width,
    threeEqualNavAreas: actual.navItems.length === 3 && actual.navWidthSpread <= 1,
    continuousFlow: actual.assistantToSuggestionsGap >= 9 && actual.assistantToSuggestionsGap <= 15,
    momentsArtDoesNotCoverTitle: actual.momentsTitleArtOverlap === 0,
    frozenGeometryMatches: geometryDiffs.length === 0,
    frozenBackgroundMatches: actual.layoutBackground === reference.layoutBackground,
    referenceHttpOk: referenceResponse?.ok() === true,
    noBrowserErrors:
      consoleErrors.length === 0 && pageErrors.length === 0 && failedRequests.length === 0 && referenceErrors.length === 0,
  }

  const result = {
    viewport,
    passed: Object.values(checks).every(Boolean),
    status: response?.status() || null,
    checks,
    actual,
    reference,
    geometryDiffs,
    consoleErrors,
    pageErrors,
    failedRequests,
    referenceErrors,
  }
  await page.close()
  return result
}

async function verifyNavigation(browser) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 })
  await page.goto(`${baseUrl}/pages/home`, { waitUntil: 'networkidle', timeout: 30000 })
  await page.evaluate(() => {
    window.__dev033Calls = []
    uni.navigateTo = ({ url }) => { window.__dev033Calls.push({ method: 'navigateTo', url }); return Promise.resolve({}) }
    uni.reLaunch = ({ url }) => { window.__dev033Calls.push({ method: 'reLaunch', url }); return Promise.resolve({}) }
  })
  const selectors = [
    '.xhs-card', '.douyin-card', '.moments-card',
    '.assistant-card:nth-child(1)', '.assistant-card:nth-child(2)', '.assistant-card:nth-child(3)',
    '.nav-ai', '.bottom-nav .nav-item:nth-child(3)',
  ]
  for (const selector of selectors) await page.locator(selector).click()
  const defaultCalls = await page.evaluate(() => window.__dev033Calls)

  await page.evaluate(() => uni.setStorageSync('yunjikeji-login-identity', 'enterprise'))
  await page.reload({ waitUntil: 'networkidle' })
  await page.evaluate(() => {
    window.__dev033EnterpriseCalls = []
    uni.navigateTo = ({ url }) => { window.__dev033EnterpriseCalls.push({ method: 'navigateTo', url }); return Promise.resolve({}) }
    uni.reLaunch = ({ url }) => { window.__dev033EnterpriseCalls.push({ method: 'reLaunch', url }); return Promise.resolve({}) }
  })
  await page.locator('.assistant-card:nth-child(2)').click()
  const enterpriseCalls = await page.evaluate(() => {
    const calls = window.__dev033EnterpriseCalls
    uni.removeStorageSync('yunjikeji-login-identity')
    return calls
  })
  await page.close()

  const expectedDefault = [
    { method: 'reLaunch', url: '/pages/center' },
    { method: 'navigateTo', url: '/pages/practice' },
    { method: 'navigateTo', url: '/pages/practice' },
    { method: 'navigateTo', url: '/pages/jobs' },
    { method: 'navigateTo', url: '/pages/service/customer-service-chat?conversationId=default' },
    { method: 'reLaunch', url: '/pages/profile' },
    { method: 'reLaunch', url: '/pages/center' },
    { method: 'reLaunch', url: '/pages/profile' },
  ]
  const expectedEnterprise = [{ method: 'reLaunch', url: '/pages/service/customer-service' }]
  return {
    defaultCalls,
    enterpriseCalls,
    expectedDefault,
    expectedEnterprise,
    defaultPassed: JSON.stringify(defaultCalls) === JSON.stringify(expectedDefault),
    enterprisePassed: JSON.stringify(enterpriseCalls) === JSON.stringify(expectedEnterprise),
  }
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
    command: 'pnpm exec node <DEV-033>/dev033-home-mapping.spec.cjs',
    allPassed:
      results.every((result) => result.passed) &&
      navigation.defaultPassed && navigation.enterprisePassed,
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
