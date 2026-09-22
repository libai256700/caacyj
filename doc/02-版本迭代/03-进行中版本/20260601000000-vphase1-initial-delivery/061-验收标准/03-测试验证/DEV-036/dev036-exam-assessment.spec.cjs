const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const { chromium } = require(require.resolve('playwright', { paths: [process.cwd()] }))

const baseUrl = process.env.DEV036_BASE_URL || 'http://127.0.0.1:5173/yunjikeji/'
const evidenceDir = __dirname
const results = {
  startedAt: new Date().toISOString(),
  baseUrl,
  viewports: [],
  states: {},
  swipe: {},
  race: {},
  actions: {},
  legacy: {},
  visualContract: [],
  failures: [],
  errors: []
}

const topics = [
  { id: 'topic-a', fieldType: 'FT-A', index: '01', title: '判断题', categoryName: '判断题', categoryStatus: true, questionCount: 10, totalScore: 20, wrongQuestionCount: 0 },
  { id: 'topic-b', fieldType: 'FT-B', index: '02', title: '单选题', categoryName: '单选题', categoryStatus: true, questionCount: 20, totalScore: 40, wrongQuestionCount: 2 },
  { id: 'topic-c', index: '03', title: '多选题', categoryName: '多选题', categoryStatus: true, questionCount: 30, totalScore: 60, wrongQuestionCount: 3 },
  { id: 'topic-d', fieldType: 'FT-D', index: '04', title: '填空题', categoryName: '填空题', categoryStatus: true, questionCount: 15, totalScore: 30, wrongQuestionCount: 1 },
  { id: 'topic-e', fieldType: 'FT-E', index: '05', title: '简答题', categoryName: '简答题', categoryStatus: true, questionCount: 5, totalScore: 50, wrongQuestionCount: 1 },
  { id: 'disabled', fieldType: 'DISABLED', index: '06', title: '禁用分类', categoryName: '禁用分类', categoryStatus: false, questionCount: 99, totalScore: 99, wrongQuestionCount: 99 }
]

const sessionValue = JSON.stringify({
  type: 'object',
  data: {
    userId: 999,
    phone: '13800000000',
    name: 'DEV-036',
    role: '测试',
    token: 'dev036-token',
    refreshToken: '',
    expiresTime: '2099-01-01T00:00:00Z',
    loggedInAt: new Date().toISOString()
  }
})

const writeJson = (name, value) => {
  fs.writeFileSync(path.join(evidenceDir, name), `${JSON.stringify(value, null, 2)}\n`, 'utf8')
}

const createHarness = async (browser, viewport, options = {}) => {
  const context = await browser.newContext({ viewport, isMobile: true, hasTouch: true, deviceScaleFactor: 1 })
  await context.addInitScript(({ value }) => localStorage.setItem('yunjikeji-user-session', value), { value: sessionValue })
  const page = await context.newPage()
  const requests = []
  const consoleErrors = []
  const pageErrors = []
  const starts = []
  let wrongCount = options.wrongCount ?? 0

  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', (error) => pageErrors.push(error.message))

  await page.route('**/app-api/yj/practices/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    requests.push({ method: request.method(), path: url.pathname, query: Object.fromEntries(url.searchParams) })

    if (url.pathname.endsWith('/current')) {
      if (options.state === 'loading') await new Promise((resolve) => setTimeout(resolve, 650))
      if (options.state === 'empty') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, data: [] }) })
      if (options.state === 'error') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 500, msg: '测试分类接口失败', data: null }) })

      const topicId = url.searchParams.get('topicId') || ''
      const mode = url.searchParams.get('mode') || 'standard'
      if (options.race && topicId === 'FT-B') await new Promise((resolve) => setTimeout(resolve, 400))
      if (options.race && topicId === 'topic-c') await new Promise((resolve) => setTimeout(resolve, 20))
      const sourceTopics = options.threeTopics ? [...topics.slice(0, 3), topics.at(-1)] : topics
      const payloadTopics = sourceTopics.map((topic) => ({
        ...topic,
        wrongQuestionCount: mode === 'wrongReview' && topic.id === 'topic-a' ? wrongCount : topic.wrongQuestionCount
      }))
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, data: payloadTopics }) })
    }

    if (url.pathname.endsWith('/start')) {
      starts.push({ method: request.method(), path: url.pathname, query: Object.fromEntries(url.searchParams) })
      await new Promise((resolve) => setTimeout(resolve, 100))
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, data: { practiceId: 'uav-basic-001', sessionId: `S-${starts.length}`, mode: url.searchParams.get('mode'), nextPage: '/pages/practice/answer' } })
      })
    }

    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ code: 404, msg: 'DEV-036 unexpected route' }) })
  })

  return { context, page, requests, starts, consoleErrors, pageErrors, setWrongCount: (value) => { wrongCount = value } }
}

const openAssessment = async (page, suffix = '') => {
  await page.goto(`${baseUrl}?dev036=${Date.now()}${suffix}#/pages/practice/exam-assessment`, { waitUntil: 'domcontentloaded' })
}

const waitReady = async (page) => {
  await page.locator('.practice-start-card').waitFor({ state: 'visible', timeout: 10000 })
}

const activeTopicText = (page) => page.locator('.topic-tab--active .topic-tab__title').innerText()

const dispatchSwipe = async (context, page, direction) => {
  const box = await page.locator('.topic-swiper').boundingBox()
  assert(box, 'topic swiper must have a bounding box')
  const y = box.y + box.height / 2
  const startX = direction === 'left' ? box.x + box.width * 0.64 : box.x + box.width * 0.36
  const endX = direction === 'left' ? box.x + box.width * 0.36 : box.x + box.width * 0.64
  const cdp = await context.newCDPSession(page)
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: startX, y }] })
  for (let step = 1; step <= 8; step += 1) {
    const x = startX + ((endX - startX) * step) / 8
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y }] })
    await page.waitForTimeout(24)
  }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
}

const collectLayout = async (page) => page.evaluate(() => {
  const tabs = [...document.querySelectorAll('.topic-tab')]
  const buttons = [...document.querySelectorAll('.practice-start-actions__primary,.practice-start-actions__secondary')]
  const section = document.querySelector('.topic-section')
  const swiper = document.querySelector('.topic-swiper')
  const card = document.querySelector('.practice-start-card')
  const leafTextCount = (text) => [...document.querySelectorAll('*')]
    .filter((element) => element.children.length === 0 && element.textContent?.trim() === text)
    .length
  return {
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    tabCount: tabs.length,
    tabY: tabs.map((element) => Math.round(element.getBoundingClientRect().y)),
    tabWhiteSpace: tabs.map((element) => getComputedStyle(element.querySelector('.topic-tab__title')).whiteSpace),
    introDomCount: document.querySelectorAll('.practice-start__intro').length,
    introTitleTextCount: leafTextCount('确认练习信息'),
    introSubtitleTextCount: leafTextCount('请确认以下练习范围与规则，准备开始练习'),
    categoryHeadingDomCount: document.querySelectorAll('.topic-section__heading').length,
    categoryTitleTextCount: leafTextCount('题型分类'),
    categoryTipTextCount: leafTextCount('左右滑动切换分类'),
    sectionStyle: section ? {
      backgroundColor: getComputedStyle(section).backgroundColor,
      boxShadow: getComputedStyle(section).boxShadow,
      padding: getComputedStyle(section).padding
    } : null,
    swiperToCardGap: swiper && card
      ? card.getBoundingClientRect().top - swiper.getBoundingClientRect().bottom
      : null,
    buttons: buttons.map((element) => {
      const rect = element.getBoundingClientRect()
      return { left: rect.left, right: rect.right, width: rect.width, height: rect.height }
    })
  }
})

const testViewports = async (browser) => {
  for (const viewport of [{ width: 360, height: 800 }, { width: 390, height: 844 }, { width: 430, height: 932 }]) {
    const harness = await createHarness(browser, viewport)
    await openAssessment(harness.page)
    await waitReady(harness.page)
    const layout = await collectLayout(harness.page)
    assert.equal(layout.tabCount, 5)
    assert.equal(await harness.page.getByText('禁用分类').count(), 0)
    assert(layout.scrollWidth <= layout.innerWidth + 1, `horizontal overflow at ${viewport.width}`)
    assert(layout.bodyScrollWidth <= layout.innerWidth + 1, `body horizontal overflow at ${viewport.width}`)
    assert(Math.max(...layout.tabY) - Math.min(...layout.tabY) <= 1, `tabs not aligned at ${viewport.width}`)
    assert(layout.tabWhiteSpace.every((value) => value === 'nowrap'), `tabs wrap at ${viewport.width}`)
    assert(layout.buttons.every((button) => button.left >= 0 && button.right <= viewport.width + 1 && button.width > 0 && button.height > 0), `button clipped at ${viewport.width}`)
    assert.equal(layout.introDomCount, 0, `new-page intro DOM remains at ${viewport.width}`)
    assert.equal(layout.introTitleTextCount, 0, `new-page intro title remains at ${viewport.width}`)
    assert.equal(layout.introSubtitleTextCount, 0, `new-page intro subtitle remains at ${viewport.width}`)
    assert.equal(layout.categoryHeadingDomCount, 0, `category heading DOM remains at ${viewport.width}`)
    assert.equal(layout.categoryTitleTextCount, 0, `category heading text remains at ${viewport.width}`)
    assert.equal(layout.categoryTipTextCount, 0, `category tip text remains at ${viewport.width}`)
    assert.equal(layout.sectionStyle?.backgroundColor, 'rgba(0, 0, 0, 0)')
    assert.equal(layout.sectionStyle?.boxShadow, 'none')
    assert.equal(layout.sectionStyle?.padding, '0px')
    assert(layout.swiperToCardGap >= 0 && layout.swiperToCardGap <= 16, `swiper/card gap is not compact at ${viewport.width}`)
    await harness.page.screenshot({ path: path.join(evidenceDir, `assessment-${viewport.width}x${viewport.height}.png`) })
    await harness.page.screenshot({ path: path.join(evidenceDir, `assessment-${viewport.width}x${viewport.height}-full.png`), fullPage: true })
    results.viewports.push({ viewport, layout, consoleErrors: harness.consoleErrors, pageErrors: harness.pageErrors })
    results.visualContract.push({
      viewport,
      newPageIntroDom: layout.introDomCount,
      forbiddenIntroTexts: layout.introTitleTextCount + layout.introSubtitleTextCount,
      categoryHeadingDom: layout.categoryHeadingDomCount,
      swiperToCardGap: layout.swiperToCardGap
    })
    assert.equal(harness.pageErrors.length, 0)
    await harness.context.close()
  }
}

const testSwipeAndRace = async (browser) => {
  const swipeHarness = await createHarness(browser, { width: 390, height: 844 })
  await openAssessment(swipeHarness.page)
  await waitReady(swipeHarness.page)
  assert.equal(await activeTopicText(swipeHarness.page), '判断题')
  await dispatchSwipe(swipeHarness.context, swipeHarness.page, 'left')
  await swipeHarness.page.waitForTimeout(800)
  const afterLeft = await activeTopicText(swipeHarness.page)
  await swipeHarness.page.screenshot({ path: path.join(evidenceDir, 'swipe-left-to-topic-b.png') })
  if (afterLeft !== '单选题') await swipeHarness.page.locator('.topic-tab').nth(1).click({ force: true })
  await waitReady(swipeHarness.page)
  await dispatchSwipe(swipeHarness.context, swipeHarness.page, 'right')
  await swipeHarness.page.waitForTimeout(800)
  const afterRight = await activeTopicText(swipeHarness.page)
  await swipeHarness.page.screenshot({ path: path.join(evidenceDir, 'swipe-right-to-topic-a.png') })
  const requestedIds = swipeHarness.requests.filter((item) => item.path.endsWith('/current')).map((item) => item.query.topicId || '')
  assert(requestedIds.includes('FT-A'))
  assert(requestedIds.includes('FT-B'))
  results.swipe = {
    configuration: { enabledTopics: 5, displayMultipleItems: 3, circular: true },
    left: { expected: '单选题', actual: afterLeft, passed: afterLeft === '单选题' },
    right: { expected: '判断题', actual: afterRight, passed: afterRight === '判断题' },
    requestedIds
  }
  if (!results.swipe.left.passed || !results.swipe.right.passed) {
    results.failures.push('至少四个启用分类时，双向真实触摸滑动未按预期切换分类。')
  }
  await swipeHarness.context.close()

  const boundaryHarness = await createHarness(browser, { width: 390, height: 844 }, { threeTopics: true })
  await openAssessment(boundaryHarness.page, '&boundary=three')
  await waitReady(boundaryHarness.page)
  const boundary = await boundaryHarness.page.evaluate(() => {
    const viewportWidth = window.innerWidth
    const tabs = [...document.querySelectorAll('.topic-tab')].map((element) => {
      const rect = element.getBoundingClientRect()
      return { text: element.textContent.trim(), left: rect.left, right: rect.right, visible: rect.right > 0 && rect.left < viewportWidth }
    })
    return { count: tabs.length, allVisible: tabs.every((tab) => tab.visible), tabs }
  })
  assert.equal(boundary.count, 3)
  assert.equal(boundary.allVisible, true)
  results.swipe.threeItemBoundary = boundary
  await boundaryHarness.page.screenshot({ path: path.join(evidenceDir, 'swipe-three-item-boundary.png') })
  await boundaryHarness.context.close()

  const raceHarness = await createHarness(browser, { width: 390, height: 844 }, { race: true })
  await openAssessment(raceHarness.page)
  await waitReady(raceHarness.page)
  await raceHarness.page.locator('.topic-tab').nth(1).click({ force: true })
  await raceHarness.page.waitForTimeout(30)
  await raceHarness.page.locator('.topic-tab').nth(2).click({ force: true })
  await raceHarness.page.waitForTimeout(650)
  await waitReady(raceHarness.page)
  assert.equal(await activeTopicText(raceHarness.page), '多选题')
  assert.equal(await raceHarness.page.getByText('30题').count(), 1)
  assert.equal(await raceHarness.page.getByText('60分').count(), 1)
  const raceIds = raceHarness.requests.filter((item) => item.path.endsWith('/current')).map((item) => item.query.topicId || '')
  assert(raceIds.includes('FT-B'))
  assert(raceIds.includes('topic-c'))
  await raceHarness.page.screenshot({ path: path.join(evidenceDir, 'race-latest-topic-wins.png') })
  results.race = { active: await activeTopicText(raceHarness.page), requestedIds: raceIds, retainedSummary: ['30题', '60分'] }
  await raceHarness.context.close()
}

const testStates = async (browser) => {
  for (const state of ['loading', 'empty', 'error']) {
    const harness = await createHarness(browser, { width: 390, height: 844 }, { state })
    await openAssessment(harness.page, `&state=${state}`)
    if (state === 'loading') {
      await harness.page.getByText('正在加载题型').waitFor({ state: 'visible' })
      results.states.loading = { visible: true }
    } else if (state === 'empty') {
      await harness.page.getByText('暂无可用题型').waitFor({ state: 'visible' })
      assert.equal(await harness.page.locator('.topic-tab').count(), 0)
      results.states.empty = { visible: true, fallbackTabs: 0 }
    } else {
      await harness.page.getByText('考题信息暂不可用').waitFor({ state: 'visible' })
      await harness.page.getByText('测试分类接口失败').waitFor({ state: 'visible' })
      assert.equal(await harness.page.locator('.topic-tab').count(), 0)
      results.states.error = { visible: true, message: '测试分类接口失败', fallbackTabs: 0 }
    }
    await harness.page.screenshot({ path: path.join(evidenceDir, `state-${state}.png`), fullPage: true })
    await harness.context.close()
  }
}

const testActions = async (browser) => {
  const harness = await createHarness(browser, { width: 390, height: 844 }, { wrongCount: 0 })
  await openAssessment(harness.page)
  await waitReady(harness.page)
  await harness.page.evaluate(() => {
    window.__dev036NavCalls = []
    window.__dev036Toasts = []
    const uniApi = window.uni
    uniApi.navigateTo = (options) => { window.__dev036NavCalls.push(options.url); options.success?.({}) }
    uniApi.showToast = (options) => { window.__dev036Toasts.push(options.title); options.success?.({}) }
  })

  await harness.page.locator('.practice-start-actions__primary').dblclick({ delay: 15 })
  await harness.page.waitForTimeout(250)
  assert.equal(harness.starts.length, 1)
  assert.equal(harness.starts[0].query.mode, 'standard')
  assert.equal(harness.starts[0].query.topicId, 'FT-A')
  const navAfterStandard = await harness.page.evaluate(() => window.__dev036NavCalls.slice())
  assert.equal(navAfterStandard.length, 1)
  assert(navAfterStandard[0].includes('id=uav-basic-001'))
  assert(navAfterStandard[0].includes('sessionId=S-1'))
  assert(navAfterStandard[0].includes('mode=standard'))
  assert(navAfterStandard[0].includes('topicId=FT-A'))

  await harness.page.locator('.practice-start-actions__secondary').dblclick({ delay: 15 })
  await harness.page.waitForTimeout(180)
  assert.equal(harness.starts.length, 1, 'no-wrong state must not start a practice')
  const toasts = await harness.page.evaluate(() => window.__dev036Toasts.slice())
  assert(toasts.includes('当前练习服务暂无可复习错题'))

  harness.setWrongCount(3)
  await harness.page.locator('.practice-start-actions__secondary').dblclick({ delay: 15 })
  await harness.page.waitForTimeout(300)
  assert.equal(harness.starts.length, 2)
  assert.equal(harness.starts[1].query.mode, 'wrongReview')
  assert.equal(harness.starts[1].query.topicId, 'FT-A')
  const navAfterWrong = await harness.page.evaluate(() => window.__dev036NavCalls.slice())
  assert.equal(navAfterWrong.length, 2)
  assert(navAfterWrong[1].includes('mode=wrongReview'))
  results.actions = { starts: harness.starts, navigation: navAfterWrong, toasts }
  await harness.page.screenshot({ path: path.join(evidenceDir, 'actions-ready.png'), fullPage: true })
  await harness.context.close()
}

const testLegacy = async (browser) => {
  const harness = await createHarness(browser, { width: 390, height: 844 })
  await harness.page.goto(`${baseUrl}?dev036=${Date.now()}#/pages/practice/start?id=uav-basic-001&topicId=FT-A&topicTitle=${encodeURIComponent('判断题')}&mode=standard`, { waitUntil: 'domcontentloaded' })
  await waitReady(harness.page)
  await harness.page.getByText('确认练习信息', { exact: true }).waitFor({ state: 'visible' })
  assert.equal(await harness.page.locator('.practice-start__intro').count(), 1)
  assert.equal(await harness.page.getByText('请确认以下练习范围与规则，准备开始练习', { exact: true }).count(), 1)
  for (const text of ['题目分类', '题目编号', '题量', '总分', '答题时间', '阅卷方式', '开始练习', '错题复练']) {
    assert((await harness.page.getByText(text, { exact: true }).count()) >= 1, `legacy missing ${text}`)
  }
  await harness.page.screenshot({ path: path.join(evidenceDir, 'legacy-start-390x844.png'), fullPage: true })
  results.legacy = { introDomCount: 1, introVisible: true, sharedFields: ['题目分类', '题目编号', '题量', '总分', '答题时间', '阅卷方式'], actions: ['开始练习', '错题复练'], pageErrors: harness.pageErrors }
  assert.equal(harness.pageErrors.length, 0)
  await harness.context.close()
}

;(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.DEV036_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  })
  try {
    await testViewports(browser)
    await testSwipeAndRace(browser)
    await testStates(browser)
    await testActions(browser)
    await testLegacy(browser)
    results.finishedAt = new Date().toISOString()
    results.status = results.failures.length ? 'failed' : 'passed'
  } catch (error) {
    results.finishedAt = new Date().toISOString()
    results.status = 'failed'
    results.errors.push(error?.stack || String(error))
    throw error
  } finally {
    writeJson('playwright-results.json', results)
    await browser.close()
  }
})()
