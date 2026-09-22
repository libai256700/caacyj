const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd()] }))

const baseUrl = process.env.DEV060_BASE_URL || 'http://127.0.0.1:5173/yunjikeji/'
const chromePath = process.env.DEV060_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const evidenceDir = __dirname
const primaryViewport = { width: 390, height: 844 }
const results = {
  fixture: 'Playwright route 提供确定性练习接口响应；使用真实 answer.vue 组件状态，不向应用源码写入测试开关或假数据。',
  startedAt: new Date().toISOString(),
  baseUrl,
  checks: [],
  failures: [],
  browserErrors: []
}

const sessionValue = JSON.stringify({
  type: 'object',
  data: {
    userId: 999,
    phone: '13800000000',
    name: 'DEV-060',
    role: '测试',
    token: 'dev060-token',
    refreshToken: '',
    expiresTime: '2099-01-01T00:00:00Z',
    loggedInAt: new Date().toISOString()
  }
})

const questions = {
  single: {
    id: 'single-060',
    type: '单选题',
    title: '客户需求识别的首要动作是什么？',
    stem: '请选择一个答案。',
    score: 5,
    options: [
      { id: 'A', label: 'A', content: '先确认客户目标' },
      { id: 'B', label: 'B', content: '直接介绍产品' },
      { id: 'C', label: 'C', content: '跳过需求分析' },
      { id: 'D', label: 'D', content: '仅记录联系方式' }
    ]
  },
  multiple: {
    id: 'multiple-060',
    type: '多选题',
    title: '哪些动作有助于形成完整服务方案？',
    stem: '请选择所有正确答案。',
    score: 10,
    options: [
      { id: 'A', label: 'A', content: '忽略风险偏好' },
      { id: 'B', label: 'B', content: '只陈述产品收益' },
      { id: 'C', label: 'C', content: '确认目标与差距' },
      { id: 'D', label: 'D', content: '省略后续跟进' },
      { id: 'E', label: 'E', content: '替客户作出决定' },
      { id: 'F', label: 'F', content: '约定后续服务节奏' }
    ]
  },
  text: {
    id: 'text-060',
    type: '文本题',
    title: '请写出下一阶段客户经营动作。',
    stem: '请输入具体行动。',
    score: 10,
    options: []
  }
}

const scenarios = {
  correctSingle: { question: questions.single, initialIndex: 0, totalQuestions: 3, correct: true, correctIds: ['A'] },
  correctMultiple: { question: questions.multiple, initialIndex: 1, totalQuestions: 3, correct: true, correctIds: ['C', 'F'] },
  correctText: { question: questions.text, initialIndex: 0, totalQuestions: 2, correct: true, correctIds: ['参考要点'] },
  correctLast: { question: questions.multiple, initialIndex: 2, totalQuestions: 3, correct: true, correctIds: ['C', 'F'], completed: true },
  wrongMultiple: { question: questions.multiple, initialIndex: 0, totalQuestions: 2, correct: false, correctIds: ['C', 'F'] },
  duplicateSingle: { question: questions.single, initialIndex: 0, totalQuestions: 2, correct: true, correctIds: ['A'], responseDelay: 300 }
}

const writeResults = () => {
  fs.writeFileSync(path.join(evidenceDir, 'playwright-results.json'), `${JSON.stringify(results, null, 2)}\n`, 'utf8')
}

const responseBody = (config, body) => ({
  questionId: config.question.id,
  selectedOptionId: body.selectedOptionIds?.[0] || '',
  selectedOptionIds: body.selectedOptionIds || [],
  correctOptionId: config.correctIds.join('、'),
  correctOptionIds: config.correctIds,
  correct: config.correct,
  explanation: '先确认客户目标与差距，再结合风险偏好形成方案，并约定后续服务节奏。',
  currentIndex: config.initialIndex,
  nextQuestionIndex: Math.min(config.initialIndex + 1, config.totalQuestions - 1),
  totalQuestions: config.totalQuestions,
  answeredCount: Math.min(config.initialIndex + 1, config.totalQuestions),
  correctCount: config.correct ? Math.min(config.initialIndex + 1, config.totalQuestions) : config.initialIndex,
  progressPercent: Math.round(((config.initialIndex + 1) / config.totalQuestions) * 100),
  completed: Boolean(config.completed)
})

const questionBody = (config, index) => ({
  practiceId: 'practice-060',
  sessionId: 'session-060',
  mode: 'standard',
  currentIndex: index,
  totalQuestions: config.totalQuestions,
  answeredCount: index,
  correctCount: index,
  progressPercent: Math.round(((index + 1) / config.totalQuestions) * 100),
  question: index === config.initialIndex ? config.question : questions.single
})

const createHarness = async (browser, scenarioName, viewport = primaryViewport) => {
  const config = scenarios[scenarioName]
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
      const index = getCount === 0 ? config.initialIndex : requestedIndex
      getCount += 1
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, data: questionBody(config, index) })
      })
    }

    if (request.method() === 'POST' && url.pathname.endsWith('/answers')) {
      if (config.responseDelay) await new Promise((resolve) => setTimeout(resolve, config.responseDelay))
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, data: responseBody(config, body) })
      })
    }

    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ code: 404, msg: 'DEV-060 unexpected route' }) })
  })

  const url = `${baseUrl}?dev060=${Date.now()}-${scenarioName}-${viewport.width}#/pages/practice/answer?id=practice-060&sessionId=session-060&mode=standard`
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  await page.locator('.question-card').waitFor({ state: 'visible', timeout: 10000 })
  await page.evaluate(() => {
    window.__dev060NavigateTo = []
    window.__dev060Relaunch = []
    window.uni.navigateTo = (options) => { window.__dev060NavigateTo.push(options.url); options.success?.({}) }
    window.uni.reLaunch = (options) => { window.__dev060Relaunch.push(options.url); options.success?.({}) }
  })
  return { context, page, requests, pageErrors, consoleErrors, requestFailures, config, scenarioName, viewport }
}

const getRequests = (harness, method, suffix) => harness.requests.filter((item) => item.method === method && item.path.endsWith(suffix))

const assertNoBrowserErrors = (harness) => {
  const errors = [...harness.pageErrors, ...harness.consoleErrors, ...harness.requestFailures]
  results.browserErrors.push({ scenario: harness.scenarioName, viewport: harness.viewport, errors })
  assert.deepEqual(errors, [], `${harness.scenarioName} browser errors must be empty`)
}

const assertResultDetails = async (harness, expectedTitle) => {
  await harness.page.waitForTimeout(250)
  const resultTitleCount = await harness.page.getByText(expectedTitle, { exact: true }).count()
  const questionGetCount = getRequests(harness, 'GET', '/question').length
  assert.equal(
    resultTitleCount,
    1,
    `${harness.scenarioName} must retain ${expectedTitle} on the submitted question; observed resultTitleCount=${resultTitleCount}, questionGetCount=${questionGetCount}`
  )
  assert.equal(await harness.page.getByText('正确答案', { exact: true }).count(), 1)
  assert.equal(await harness.page.getByText('试题详解', { exact: true }).count(), 1)
  assert.equal(await harness.page.getByText('AI 深度解答', { exact: true }).count(), 1)
}

const selectCorrect = async (harness) => {
  if (harness.config.question.type === '单选题') {
    await harness.page.locator('.question-options__item').first().click()
    return
  }
  if (harness.config.question.type === '多选题') {
    await harness.page.locator('.question-options__item').nth(2).click()
    await harness.page.locator('.question-options__item').nth(5).click()
    await harness.page.getByText('提交', { exact: true }).click()
    return
  }
  const input = harness.page.locator('.question-text-answer__input textarea, textarea.question-text-answer__input').first()
  await input.fill('每周复盘客户目标并记录后续动作。')
  await harness.page.getByText('提交', { exact: true }).click()
}

const testCorrectOrdinary = async (browser, scenarioName) => {
  const harness = await createHarness(browser, scenarioName)
  await selectCorrect(harness)
  await assertResultDetails(harness, '回答正确')
  assert.equal(getRequests(harness, 'GET', '/question').length, 1, `${scenarioName} must not GET the next question before explicit action`)
  assert.equal(await harness.page.getByText('下一题', { exact: true }).count(), 1)
  const progressBefore = await harness.page.locator('.answer-progress__copy').textContent()
  await harness.page.locator('.result-detail__ai').click()
  const aiCalls = await harness.page.evaluate(() => window.__dev060NavigateTo.slice())
  assert.equal(aiCalls.length, 1)
  assert(aiCalls[0].includes('/pages/practice/ai-answer'))
  await harness.page.getByText('下一题', { exact: true }).click()
  await harness.page.waitForFunction(() => !document.querySelector('.result-card'))
  const gets = getRequests(harness, 'GET', '/question')
  assert.equal(gets.length, 2, `${scenarioName} must GET once after explicit next action`)
  assert.equal(gets.at(-1).query.index, String(harness.config.initialIndex + 1))
  results.checks.push({ scenario: scenarioName, progressBefore, getCountBeforeNext: 1, getCountAfterNext: gets.length, aiCalls })
  assertNoBrowserErrors(harness)
  await harness.context.close()
}

const testCorrectLast = async (browser) => {
  const harness = await createHarness(browser, 'correctLast')
  await selectCorrect(harness)
  await assertResultDetails(harness, '回答正确')
  assert.equal(getRequests(harness, 'GET', '/question').length, 1, 'correct last question must not GET another question')
  assert.deepEqual(await harness.page.evaluate(() => window.__dev060Relaunch.slice()), [], 'correct last question must not relaunch before explicit completion')
  await harness.page.getByText('完成练习', { exact: true }).waitFor({ state: 'visible' })
  await harness.page.screenshot({ path: path.join(evidenceDir, 'correct-last-390x844.png') })
  await harness.page.getByText('完成练习', { exact: true }).click()
  const relaunch = await harness.page.evaluate(() => window.__dev060Relaunch.slice())
  assert.deepEqual(relaunch, ['/pages/home'])
  results.checks.push({ scenario: 'correctLast', getCountBeforeComplete: 1, relaunch })
  assertNoBrowserErrors(harness)
  await harness.context.close()
}

const testWrongRegression = async (browser) => {
  const harness = await createHarness(browser, 'wrongMultiple')
  await harness.page.locator('.question-options__item').nth(1).click()
  await harness.page.locator('.question-options__item').nth(3).click()
  await harness.page.getByText('提交', { exact: true }).click()
  await assertResultDetails(harness, '回答错误')
  assert.equal(await harness.page.locator('.question-options__item--wrong').count(), 2)
  assert.equal(await harness.page.locator('.question-options__item--correct').count(), 2)
  assert.equal(getRequests(harness, 'GET', '/question').length, 1)
  await harness.page.getByText('下一题', { exact: true }).click()
  await harness.page.waitForFunction(() => !document.querySelector('.result-card'))
  assert.equal(getRequests(harness, 'GET', '/question').length, 2)
  results.checks.push({ scenario: 'wrongMultiple', wrongOptions: 2, correctOptions: 2, explicitNext: true })
  assertNoBrowserErrors(harness)
  await harness.context.close()
}

const testDuplicateGuard = async (browser) => {
  const harness = await createHarness(browser, 'duplicateSingle')
  await harness.page.locator('.question-options__item').first().evaluate((element) => {
    element.click()
    element.click()
  })
  await harness.page.waitForTimeout(150)
  await assertResultDetails(harness, '回答正确')
  const posts = getRequests(harness, 'POST', '/answers')
  assert.equal(posts.length, 1, 'rapid repeated submit must POST exactly once')
  results.checks.push({ scenario: 'duplicateSingle', postCount: posts.length })
  assertNoBrowserErrors(harness)
  await harness.context.close()
}

const testResponsiveResult = async (browser, viewport) => {
  const harness = await createHarness(browser, 'correctSingle', viewport)
  await selectCorrect(harness)
  await assertResultDetails(harness, '回答正确')
  const layout = await harness.page.evaluate(() => {
    const rect = (selector) => {
      const value = document.querySelector(selector)?.getBoundingClientRect()
      return value ? { top: value.top, right: value.right, bottom: value.bottom, left: value.left } : null
    }
    return {
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      documentScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      cardStage: rect('.answer-card-stage'),
      actions: rect('.answer-actions'),
      primary: rect('.answer-actions__primary')
    }
  })
  assert(layout.documentScrollWidth <= viewport.width + 1, `document overflow at ${viewport.width}x${viewport.height}`)
  assert(layout.bodyScrollWidth <= viewport.width + 1, `body overflow at ${viewport.width}x${viewport.height}`)
  assert(layout.actions && layout.actions.bottom <= viewport.height + 1, `action footer exceeds viewport at ${viewport.width}x${viewport.height}`)
  assert(layout.primary && layout.primary.left >= 0 && layout.primary.right <= viewport.width + 1, `primary action overflows at ${viewport.width}x${viewport.height}`)
  assert(layout.cardStage && layout.actions && layout.cardStage.bottom <= layout.actions.top + 1, `action footer overlaps card stage at ${viewport.width}x${viewport.height}`)
  await harness.page.screenshot({ path: path.join(evidenceDir, `correct-result-${viewport.width}x${viewport.height}.png`) })
  results.checks.push({ scenario: 'responsiveCorrectResult', viewport, layout })
  assertNoBrowserErrors(harness)
  await harness.context.close()
}

;(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: chromePath })
  try {
    await testCorrectOrdinary(browser, 'correctSingle')
    await testCorrectOrdinary(browser, 'correctMultiple')
    await testCorrectOrdinary(browser, 'correctText')
    await testCorrectLast(browser)
    await testWrongRegression(browser)
    await testDuplicateGuard(browser)
    for (const viewport of [
      { width: 360, height: 800 },
      { width: 390, height: 844 },
      { width: 430, height: 932 }
    ]) {
      await testResponsiveResult(browser, viewport)
    }
    results.status = 'passed'
  } catch (error) {
    results.status = 'failed'
    results.failures.push(error?.stack || String(error))
    throw error
  } finally {
    results.finishedAt = new Date().toISOString()
    writeResults()
    await browser.close()
  }
})()
