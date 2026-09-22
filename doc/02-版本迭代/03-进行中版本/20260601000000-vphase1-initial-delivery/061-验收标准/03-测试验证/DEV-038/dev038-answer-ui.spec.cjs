const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd()] }))

const baseUrl = process.env.DEV038_BASE_URL || 'http://127.0.0.1:5173/yunjikeji/'
const evidenceDir = __dirname
const viewports = [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 }
]
const results = {
  fixture: '确定性视觉夹具：仅 Playwright 上下文设置可控登录存储并拦截练习接口，不写入应用源码，不代表真实账号联调。',
  startedAt: new Date().toISOString(),
  baseUrl,
  viewports: [],
  interactions: [],
  specialChecks: [],
  failures: [],
  errors: []
}

const sessionValue = JSON.stringify({
  type: 'object',
  data: {
    userId: 999,
    phone: '13800000000',
    name: 'DEV-038',
    role: '测试',
    token: 'dev038-token',
    refreshToken: '',
    expiresTime: '2099-01-01T00:00:00Z',
    loggedInAt: new Date().toISOString()
  }
})

const singleQuestion = {
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

const multipleQuestion = {
  id: 'multiple-012',
  type: '多选题',
  title: '您认为上季度的业绩目标未能实现的最重要因素是什么？',
  stem: '可选择多个最符合实际情况的选项。',
  score: 10,
  options: [
    { id: 'A', label: 'A', content: 'KYC' },
    { id: 'B', label: 'B', content: '保险观念铺垫不足' },
    { id: 'C', label: 'C', content: '产品介绍需要加强' },
    { id: 'D', label: 'D', content: '需求激发不足' },
    { id: 'E', label: 'E', content: '异议处理不充分' },
    { id: 'F', label: 'F', content: '促成时机不准确' }
  ]
}

const longMultipleQuestion = {
  ...multipleQuestion,
  id: 'multiple-long-007',
  title: '当客户需求复杂且沟通时间有限时，哪些做法有助于稳定推进服务方案？',
  options: multipleQuestion.options.map((option, index) => ({
    ...option,
    content: `${option.content}，并结合客户当前目标、风险偏好、家庭阶段与后续服务节奏进行完整说明${index + 1}`
  }))
}

const textQuestion = {
  id: 'text-003',
  type: '文本题',
  title: '请简要说明下一阶段最需要提升的客户经营动作。',
  stem: '请输入具体行动，不能为空。',
  score: 10,
  options: []
}

const longExplanation = Array.from(
  { length: 14 },
  (_, index) => `第${index + 1}步应结合客户需求、目标差距、风险偏好和后续跟进节奏进行复盘。`
).join('')

const scenarioConfig = {
  single: { initialIndex: 0, totalQuestions: 12, question: singleQuestion },
  double: { initialIndex: 0, totalQuestions: 12, question: singleQuestion, responseDelay: 250 },
  multiple: { initialIndex: 4, totalQuestions: 12, question: multipleQuestion },
  longMultiple: { initialIndex: 6, totalQuestions: 12, question: longMultipleQuestion, explanation: longExplanation },
  text: { initialIndex: 2, totalQuestions: 12, question: textQuestion },
  last: { initialIndex: 11, totalQuestions: 12, question: multipleQuestion }
}

const writeResults = () => {
  fs.writeFileSync(path.join(evidenceDir, 'playwright-results.json'), `${JSON.stringify(results, null, 2)}\n`, 'utf8')
}

const questionPayload = (config, currentIndex) => ({
  practiceId: 'practice-038',
  sessionId: 'session-038',
  mode: 'standard',
  currentIndex,
  totalQuestions: config.totalQuestions,
  answeredCount: currentIndex,
  correctCount: Math.max(currentIndex - 1, 0),
  progressPercent: Math.round(((currentIndex + 1) / config.totalQuestions) * 100),
  question: currentIndex === config.initialIndex ? config.question : singleQuestion
})

const createHarness = async (browser, viewport, scenario) => {
  const config = scenarioConfig[scenario]
  const context = await browser.newContext({ viewport, isMobile: true, hasTouch: true, deviceScaleFactor: 1 })
  await context.addInitScript(({ value }) => localStorage.setItem('yunjikeji-user-session', value), { value: sessionValue })
  const page = await context.newPage()
  const requests = []
  const pageErrors = []
  const consoleErrors = []
  const requestFailures = []
  let getCount = 0

  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('requestfailed', (request) => requestFailures.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText || 'failed'}`))
  await page.route('**/app-api/yj/practices/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    let body = null
    try {
      body = request.postDataJSON()
    } catch {
      body = request.postData()
    }
    requests.push({ method: request.method(), path: url.pathname, query: Object.fromEntries(url.searchParams), body })

    if (request.method() === 'GET' && url.pathname.endsWith('/question')) {
      const requestedIndex = Number(url.searchParams.get('index') || 0)
      const currentIndex = getCount === 0 ? config.initialIndex : requestedIndex
      getCount += 1
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, data: questionPayload(config, currentIndex) })
      })
    }

    if (request.method() === 'POST' && url.pathname.endsWith('/answers')) {
      if (config.responseDelay) await new Promise((resolve) => setTimeout(resolve, config.responseDelay))
      const selected = Array.isArray(body?.selectedOptionIds) ? body.selectedOptionIds : []
      const isSingle = scenario === 'single' || scenario === 'double'
      const isText = scenario === 'text'
      const isLast = scenario === 'last'
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          data: {
            questionId: config.question.id,
            selectedOptionId: selected[0] || '',
            selectedOptionIds: selected,
            correctOptionId: isSingle ? 'A' : 'C',
            correctOptionIds: isSingle ? ['A'] : ['C', 'F'],
            correct: isSingle || isText,
            explanation: config.explanation || '应先定位客户需求与目标差距，再从认知、产品介绍、需求激发和促成时机等维度复盘。',
            currentIndex: config.initialIndex,
            nextQuestionIndex: Math.min(config.initialIndex + 1, config.totalQuestions - 1),
            totalQuestions: config.totalQuestions,
            answeredCount: Math.min(config.initialIndex + 1, config.totalQuestions),
            correctCount: isSingle || isText ? 1 : Math.max(config.initialIndex - 1, 0),
            progressPercent: Math.round(((config.initialIndex + 1) / config.totalQuestions) * 100),
            completed: isLast
          }
        })
      })
    }

    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ code: 404, msg: 'DEV-038 unexpected route' }) })
  })

  const url = `${baseUrl}?dev038=${Date.now()}-${scenario}#/pages/practice/answer?id=practice-038&sessionId=session-038&mode=standard`
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  await page.locator('.question-card').waitFor({ state: 'visible', timeout: 10000 })
  await page.evaluate(() => {
    window.__dev038NavigateTo = []
    window.__dev038Relaunch = []
    const uniApi = window.uni
    uniApi.navigateTo = (options) => { window.__dev038NavigateTo.push(options.url); options.success?.({}) }
    uniApi.reLaunch = (options) => { window.__dev038Relaunch.push(options.url); options.success?.({}) }
  })
  return { context, page, requests, pageErrors, consoleErrors, requestFailures, config }
}

const collectLayout = async (page) => page.evaluate(async () => {
  const rect = (selector) => {
    const element = document.querySelector(selector)
    if (!element) return null
    const value = element.getBoundingClientRect()
    return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height }
  }
  const options = [...document.querySelectorAll('.question-options__item')]
  const optionRects = options.map((element) => {
    const value = element.getBoundingClientRect()
    return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height }
  })
  const illustrationRoot = document.querySelector('.answer-hero__illustration')
  let illustrationImage = illustrationRoot?.matches('img') ? illustrationRoot : illustrationRoot?.querySelector('img')
  if (!illustrationImage) {
    illustrationImage = new Image()
    illustrationImage.src = new URL('static/practice-answer/person-map.svg', `${location.origin}${location.pathname}`).href
    await illustrationImage.decode()
  }
  let illustrationPixels = null
  if (illustrationImage?.complete && illustrationImage.naturalWidth > 0 && illustrationImage.naturalHeight > 0) {
    const canvas = document.createElement('canvas')
    canvas.width = Math.min(illustrationImage.naturalWidth, 320)
    canvas.height = Math.max(1, Math.round(canvas.width * illustrationImage.naturalHeight / illustrationImage.naturalWidth))
    const context = canvas.getContext('2d', { willReadFrequently: true })
    context.drawImage(illustrationImage, 0, 0, canvas.width, canvas.height)
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
    let opaquePixels = 0
    const colors = new Set()
    for (let index = 0; index < pixels.length; index += 4) {
      if (pixels[index + 3] > 20) {
        opaquePixels += 1
        colors.add(`${pixels[index]},${pixels[index + 1]},${pixels[index + 2]},${pixels[index + 3]}`)
      }
    }
    illustrationPixels = {
      naturalWidth: illustrationImage.naturalWidth,
      naturalHeight: illustrationImage.naturalHeight,
      opaquePixels,
      uniqueColors: colors.size
    }
  }
  const scrollRoot = document.querySelector('.answer-card-scroll')
  const scrollCandidates = scrollRoot ? [scrollRoot, ...scrollRoot.querySelectorAll('*')] : []
  const scrollingElement = scrollCandidates.find((element) => element.scrollHeight > element.clientHeight + 2)
  return {
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    documentScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    navText: document.querySelector('.answer-nav')?.textContent?.trim() || '',
    progressText: document.querySelector('.answer-progress__copy')?.textContent?.replace(/\s+/g, ' ').trim() || '',
    card: rect('.answer-card-scroll'),
    layer: rect('.answer-card-stage__layer'),
    illustration: rect('.answer-hero__illustration'),
    illustrationPixels,
    actions: rect('.answer-actions'),
    primary: rect('.answer-actions__primary'),
    options: optionRects,
    optionDisplay: getComputedStyle(document.querySelector('.question-options')).display,
    optionColumns: getComputedStyle(document.querySelector('.question-options')).gridTemplateColumns,
    background: getComputedStyle(document.querySelector('.answer-page__bg')).backgroundImage,
    scroll: scrollingElement ? {
      tagName: scrollingElement.tagName,
      className: scrollingElement.className,
      clientHeight: scrollingElement.clientHeight,
      scrollHeight: scrollingElement.scrollHeight,
      scrollTop: scrollingElement.scrollTop
    } : null
  }
})

const assertBaseLayout = (layout, viewport, expectedProgress) => {
  assert(layout.documentScrollWidth <= viewport.width + 1, `document overflow at ${viewport.width}`)
  assert(layout.bodyScrollWidth <= viewport.width + 1, `body overflow at ${viewport.width}`)
  assert.equal(layout.navText.includes('返回'), false, 'top nav must not contain return text')
  assert.equal(layout.progressText.replace(/\s+/g, ''), expectedProgress.replace(/\s+/g, ''))
  assert(layout.card && layout.card.width >= viewport.width * 0.84 && layout.card.width <= viewport.width * 0.94)
  assert(layout.card.left >= 0 && layout.card.right <= viewport.width + 1)
  assert(layout.layer && layout.layer.top > layout.card.top && layout.layer.bottom > layout.card.bottom)
  assert(layout.illustration && layout.illustration.width > viewport.width * 0.45)
  assert(layout.illustrationPixels?.naturalWidth > 0 && layout.illustrationPixels?.naturalHeight > 0, 'SVG image must load with non-zero intrinsic dimensions')
  assert(layout.illustrationPixels.opaquePixels > 100 && layout.illustrationPixels.uniqueColors > 10, 'SVG must render non-empty, non-flat pixels')
  assert(layout.actions && layout.actions.bottom <= viewport.height + 1)
  assert(layout.primary && layout.primary.left >= 0 && layout.primary.right <= viewport.width + 1)
  assert(layout.options.every((item) => item.left >= 0 && item.right <= viewport.width + 1 && item.width > 0))
  assert(layout.background.includes('linear-gradient'))
}

const assertNoBrowserErrors = (harness) => {
  assert.deepEqual(harness.pageErrors, [], 'page errors must be empty')
  assert.deepEqual(harness.consoleErrors, [], 'console errors must be empty')
  assert.deepEqual(harness.requestFailures, [], 'request failures must be empty')
}

const testSingle = async (browser, viewport) => {
  const harness = await createHarness(browser, viewport, 'single')
  const layout = await collectLayout(harness.page)
  assertBaseLayout(layout, viewport, '出题1 / 12')
  assert.equal(layout.optionDisplay, 'flex')
  await harness.page.screenshot({ path: path.join(evidenceDir, `single-${viewport.width}x${viewport.height}.png`) })
  await harness.page.locator('.question-options__item').first().click()
  await harness.page.waitForFunction(() => document.querySelector('.answer-progress__copy')?.textContent?.includes('出题2'))
  const posts = harness.requests.filter((item) => item.method === 'POST' && item.path.endsWith('/answers'))
  assert.equal(posts.length, 1, 'single option must submit exactly once')
  assert.deepEqual(posts[0].body.selectedOptionIds, ['A'])
  results.interactions.push({ viewport, scenario: 'single-auto-submit', postCount: posts.length, body: posts[0].body })
  assertNoBrowserErrors(harness)
  await harness.context.close()
  return layout
}

const testMultiple = async (browser, viewport) => {
  const harness = await createHarness(browser, viewport, 'multiple')
  let layout = await collectLayout(harness.page)
  assertBaseLayout(layout, viewport, '出题5 / 12')
  assert.equal(layout.optionDisplay, 'grid')
  const firstRow = layout.options.slice(0, 2)
  assert(Math.abs(firstRow[0].width - firstRow[1].width) <= 1, `multiple columns differ at ${viewport.width}`)
  await harness.page.locator('.question-options__item').nth(1).click()
  await harness.page.locator('.question-options__item').nth(3).click()
  assert.equal(await harness.page.locator('.question-options__item--selected').count(), 2)
  await harness.page.locator('.question-options__item').nth(1).click()
  assert.equal(await harness.page.locator('.question-options__item--selected').count(), 1, 'multiple option must support deselection')
  await harness.page.locator('.question-options__item').nth(1).click()
  await harness.page.screenshot({ path: path.join(evidenceDir, `multiple-selected-${viewport.width}x${viewport.height}.png`) })
  await harness.page.locator('.answer-actions__primary').click()
  await harness.page.getByText('回答错误', { exact: true }).waitFor({ state: 'visible' })
  assert.equal(await harness.page.locator('.question-options__item--wrong').count(), 2)
  assert.equal(await harness.page.locator('.question-options__item--correct').count(), 2)
  assert.equal(await harness.page.getByText('试题详解', { exact: true }).count(), 1)
  assert.equal(await harness.page.getByText('AI 深度解答', { exact: true }).count(), 1)
  await harness.page.locator('.result-detail__ai').click()
  const aiCalls = await harness.page.evaluate(() => window.__dev038NavigateTo.slice())
  assert.equal(aiCalls.length, 1)
  assert(aiCalls[0].includes('/pages/practice/ai-answer'))
  await harness.page.screenshot({ path: path.join(evidenceDir, `multiple-error-${viewport.width}x${viewport.height}.png`) })
  layout = await collectLayout(harness.page)
  assert(layout.documentScrollWidth <= viewport.width + 1)
  await harness.page.getByText('下一题', { exact: true }).click()
  await harness.page.waitForFunction(() => document.querySelector('.answer-progress__copy')?.textContent?.includes('出题6'))
  const nextGets = harness.requests.filter((item) => item.method === 'GET' && item.path.endsWith('/question'))
  assert.equal(nextGets.at(-1).query.index, '5', 'wrong answer next action must fetch returned next index')
  results.interactions.push({ viewport, scenario: 'multiple-error-analysis', selected: ['B', 'D'], aiCalls })
  assertNoBrowserErrors(harness)
  await harness.context.close()
  return layout
}

const testLast = async (browser, viewport) => {
  const harness = await createHarness(browser, viewport, 'last')
  const initialLayout = await collectLayout(harness.page)
  assertBaseLayout(initialLayout, viewport, '出题12 / 12')
  assert.equal(await harness.page.getByText('上一题', { exact: true }).count(), 1)
  await harness.page.locator('.question-options__item').nth(2).click()
  await harness.page.locator('.question-options__item').nth(5).click()
  await harness.page.locator('.answer-actions__primary').click()
  await harness.page.getByText('完成练习', { exact: true }).waitFor({ state: 'visible' })
  await harness.page.screenshot({ path: path.join(evidenceDir, `last-${viewport.width}x${viewport.height}.png`) })
  await harness.page.getByText('完成练习', { exact: true }).click()
  const relaunch = await harness.page.evaluate(() => window.__dev038Relaunch.slice())
  assert.deepEqual(relaunch, ['/pages/practice'])
  results.interactions.push({ viewport, scenario: 'last-complete', relaunch })
  assertNoBrowserErrors(harness)
  await harness.context.close()

  const previousHarness = await createHarness(browser, viewport, 'last')
  await previousHarness.page.getByText('上一题', { exact: true }).click()
  await previousHarness.page.waitForFunction(() => document.querySelector('.answer-progress__copy')?.textContent?.includes('出题11'))
  const previousGets = previousHarness.requests.filter((item) => item.method === 'GET' && item.path.endsWith('/question'))
  assert.equal(previousGets.at(-1).query.index, '10')
  assert.equal(await previousHarness.page.locator('.question-options__item--selected').count(), 0, 'previous question must not fabricate historical selection')
  results.interactions.push({ viewport, scenario: 'previous-real-index', requestedIndex: previousGets.at(-1).query.index })
  assertNoBrowserErrors(previousHarness)
  await previousHarness.context.close()
  return initialLayout
}

const testText = async (browser, viewport) => {
  const harness = await createHarness(browser, viewport, 'text')
  const input = harness.page.locator('.question-text-answer__input textarea, textarea.question-text-answer__input').first()
  await input.fill('   ')
  const primary = harness.page.locator('.answer-actions__primary')
  assert.notEqual(await primary.getAttribute('disabled'), null, 'blank text answer must expose disabled state')
  await primary.evaluate((element) => element.click())
  await harness.page.waitForTimeout(100)
  assert.equal(harness.requests.filter((item) => item.method === 'POST').length, 0)
  await input.fill('每周按客户目标分层复盘，并记录下一次跟进动作。')
  await harness.page.screenshot({ path: path.join(evidenceDir, `text-${viewport.width}x${viewport.height}.png`) })
  await primary.click()
  await harness.page.waitForFunction(() => document.querySelector('.answer-progress__copy')?.textContent?.includes('出题4'))
  const posts = harness.requests.filter((item) => item.method === 'POST' && item.path.endsWith('/answers'))
  assert.equal(posts.length, 1)
  assert.deepEqual(posts[0].body.selectedOptionIds, ['每周按客户目标分层复盘，并记录下一次跟进动作。'])
  results.specialChecks.push({ viewport, scenario: 'text-non-empty-submit', body: posts[0].body })
  assertNoBrowserErrors(harness)
  await harness.context.close()
}

const testDoubleSubmitGuard = async (browser, viewport) => {
  const harness = await createHarness(browser, viewport, 'double')
  await harness.page.locator('.question-options__item').first().evaluate((element) => {
    element.click()
    element.click()
  })
  await harness.page.waitForFunction(() => document.querySelector('.answer-progress__copy')?.textContent?.includes('出题2'))
  const posts = harness.requests.filter((item) => item.method === 'POST' && item.path.endsWith('/answers'))
  assert.equal(posts.length, 1, 'rapid double click must submit once')
  results.specialChecks.push({ viewport, scenario: 'rapid-double-click-guard', postCount: posts.length })
  assertNoBrowserErrors(harness)
  await harness.context.close()
}

const testLongContent = async (browser, viewport) => {
  const harness = await createHarness(browser, viewport, 'longMultiple')
  const before = await collectLayout(harness.page)
  assertBaseLayout(before, viewport, '出题7 / 12')
  assert.equal(before.optionDisplay, 'grid')
  assert(before.options.length >= 2)
  const widths = before.options.map((item) => item.width)
  assert(Math.max(...widths) - Math.min(...widths) <= 1, 'long option copy must not change two-column widths')
  await harness.page.locator('.question-options__item').nth(1).click()
  await harness.page.locator('.question-options__item').nth(3).click()
  await harness.page.locator('.answer-actions__primary').click()
  await harness.page.getByText('回答错误', { exact: true }).waitFor({ state: 'visible' })
  const after = await collectLayout(harness.page)
  assert(after.scroll && after.scroll.scrollHeight > after.scroll.clientHeight + 2, 'long analysis must provide a scrollable content region')
  assert(after.actions.bottom <= viewport.height + 1, 'fixed action bar must stay inside viewport')
  const scrollResult = await harness.page.locator('.answer-card-scroll').evaluate((root) => {
    const candidates = [root, ...root.querySelectorAll('*')]
    const element = candidates.find((item) => item.scrollHeight > item.clientHeight + 2)
    if (!element) return null
    element.scrollTop = element.scrollHeight
    return { scrollTop: element.scrollTop, maxScrollTop: element.scrollHeight - element.clientHeight }
  })
  assert(scrollResult && scrollResult.scrollTop > 0 && scrollResult.scrollTop >= scrollResult.maxScrollTop - 2, 'long analysis must scroll to the end')
  await harness.page.screenshot({ path: path.join(evidenceDir, `long-analysis-${viewport.width}x${viewport.height}.png`) })
  results.specialChecks.push({
    viewport,
    scenario: 'long-option-and-analysis-scroll',
    optionColumns: before.optionColumns,
    optionWidths: widths,
    scroll: after.scroll,
    scrollResult,
    actions: after.actions
  })
  assertNoBrowserErrors(harness)
  await harness.context.close()
}

;(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.DEV038_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  })
  try {
    for (const viewport of viewports) {
      const single = await testSingle(browser, viewport)
      const multiple = await testMultiple(browser, viewport)
      const last = await testLast(browser, viewport)
      results.viewports.push({ viewport, single, multiple, last })
    }
    await testText(browser, { width: 390, height: 844 })
    await testDoubleSubmitGuard(browser, { width: 390, height: 844 })
    await testLongContent(browser, { width: 390, height: 844 })
    await testLongContent(browser, { width: 360, height: 800 })
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
