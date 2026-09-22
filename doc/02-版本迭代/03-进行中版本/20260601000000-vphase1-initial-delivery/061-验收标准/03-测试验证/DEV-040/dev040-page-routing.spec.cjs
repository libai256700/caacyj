const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd()] }))

const repoRoot = path.resolve(__dirname, '../../../../../../..')
const appRoot = path.join(repoRoot, 'code/develop/yunjikeji/src')
const baseUrl = process.env.DEV040_BASE_URL || 'http://127.0.0.1:5173/yunjikeji/'
const results = { startedAt: new Date().toISOString(), baseUrl, source: {}, runtime: [], errors: [] }
const read = (relative) => fs.readFileSync(path.join(appRoot, relative), 'utf8')

const auditSource = () => {
  const login = read('pages/auth/login.vue')
  const home = read('pages/home.vue')
  const index = read('pages/index.vue')
  const answer = read('pages/practice/answer.vue')
  const redirect = login.slice(login.indexOf('async function redirectAfterLogin()'))
  assert.equal((redirect.match(/redirectUrl \|\| '\/pages\/service\/customer-service'/g) || []).length, 2, 'enterprise eligible defaults must route to the enterprise customer-service page')
  assert.equal((redirect.match(/url: redirectUrl \|\| '\/pages\/service\/customer-service'/g) || []).length, 2, 'enterprise eligible routes must preserve redirectUrl priority')
  assert.match(redirect, /loginRole\.value === 'enterprise'[\s\S]*?'\/pages\/service\/customer-service'[\s\S]*?'\/pages\/home'/, 'H5 preview must choose its default by login identity')
  assert.match(redirect, /auditStatus === 1 \|\| appState\.enterpriseRegistration\?\.status === 'reviewing'[\s\S]*?url: '\/pages\/enterprise\/review\?status=reviewing'/, 'enterprise reviewing route must remain unchanged')
  assert.match(redirect, /url: '\/pages\/enterprise\/register'/, 'enterprise registration route must remain unchanged')
  assert.match(redirect, /uni\.reLaunch\(\{\s*url: '\/pages\/home'\s*}\)/, 'student normal default must route to /pages/home')
  assert.match(home, /import \{ onLoad, onShow } from '@dcloudio\/uni-app'/)
  assert.match(home, /import \{ computed, ref } from 'vue'/)
  assert.match(home, /import \{ appState, requireLogin } from '@\/stores\/appState'/)
  assert.match(home, /<view v-if="homeReady" class="preview-page">/)
  assert.match(home, /const homeReady = ref\(false\)/)
  const guard = home.slice(home.indexOf('async function guardHome()'))
  assert.match(guard, /if \(!requireLogin\(\)\) \{[\s\S]*?homeReady\.value = false[\s\S]*?return[\s\S]*?}/)
  assert.match(guard, /if \(appState\.loginIdentity === 'enterprise'\) \{[\s\S]*?homeReady\.value = false[\s\S]*?url: '\/pages\/service\/customer-service'/)
  assert(guard.indexOf("appState.loginIdentity === 'enterprise'") < guard.indexOf("import('@/services/practice')"), 'enterprise home guard must run before student data imports')
  assert(guard.indexOf("appState.loginIdentity === 'enterprise'") < guard.indexOf('homeReady.value = true'), 'enterprise home guard must run before student content is enabled')
  assert.match(home, /onLoad\(guardHome\)/)
  assert.match(home, /onShow\(guardHome\)/)
  assert.doesNotMatch(home, /AppDynamicTabBar/)
  assert.match(index, /url: '\/pages\/home'/)
  assert.doesNotMatch(index, /loginIdentity === 'enterprise'/)
  assert.match(answer, /fail: \(\) => \{[\s\S]*?url: '\/pages\/practice\/exam-assessment'/)
  assert.match(answer, /answerResult\.value\.completed[\s\S]*?url: '\/pages\/home'/)
  results.source = { status: 'passed' }
}

const sessionValue = JSON.stringify({ type: 'object', data: { userId: 999, phone: '13800000000', name: 'DEV-040', token: 'dev040-token', refreshToken: '', expiresTime: '2099-01-01T00:00:00Z', auditStatus: 2, loggedInAt: new Date().toISOString() } })

const createPage = async (browser, withSession = true, identity = 'student') => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  if (withSession) {
    await context.addInitScript(({ value, identity }) => {
      localStorage.setItem('yunjikeji-user-session', value)
      localStorage.setItem('yunjikeji-login-identity', JSON.stringify({ type: 'string', data: identity }))
    }, { value: sessionValue, identity })
  }
  const page = await context.newPage()
  const requestedPaths = []
  await page.route('**/app-api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    requestedPaths.push(url.pathname)
    if (url.pathname.endsWith('/current')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, data: [{ id: 'topic-a', fieldType: 'FT-A', index: '01', title: '判断题', categoryName: '判断题', categoryStatus: true, questionCount: 1, totalScore: 5, wrongQuestionCount: 0 }] }) })
    if (url.pathname.endsWith('/question')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, data: { practiceId: 'p-040', sessionId: 's-040', mode: 'standard', currentIndex: 0, totalQuestions: 1, answeredCount: 0, correctCount: 0, progressPercent: 100, question: { id: 'q-040', type: '单选题', title: 'DEV-040 路由验证题', stem: '请选择', score: 5, options: [{ id: 'A', label: 'A', content: '选项 A' }] } } }) })
    if (url.pathname.endsWith('/answers')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, data: { questionId: 'q-040', selectedOptionId: 'A', selectedOptionIds: ['A'], correctOptionId: 'A', correctOptionIds: ['A'], correct: true, explanation: '完成', currentIndex: 0, nextQuestionIndex: 0, totalQuestions: 1, answeredCount: 1, correctCount: 1, progressPercent: 100, completed: true } }) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, data: null }) })
  })
  return { context, page, requestedPaths }
}

const routeName = (page) => page.evaluate(() => location.hash)

const runRuntime = async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.DEV040_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' })
  try {
    const guest = await createPage(browser, false)
    await guest.page.goto(`${baseUrl}?dev040=guest#/pages/home`, { waitUntil: 'domcontentloaded' })
    await guest.page.waitForFunction(() => location.hash.includes('/pages/auth/login'))
    const homeTextCount = await guest.page.getByText('考题测评', { exact: true }).count()
    assert.equal(homeTextCount, 0)
    results.runtime.push({ scenario: 'guest-home-to-login', route: await routeName(guest.page), homeTextCount })
    await guest.context.close()

    const enterprise = await createPage(browser, true, 'enterprise')
    await enterprise.page.goto(`${baseUrl}?dev040=enterprise#/pages/home`, { waitUntil: 'domcontentloaded' })
    await enterprise.page.waitForFunction(() => location.hash.includes('/pages/service/customer-service'))
    assert.equal(await enterprise.page.getByText('自我测评', { exact: true }).count(), 0)
    assert.equal(enterprise.requestedPaths.some((url) => url.includes('/practice/')), false)
    results.runtime.push({ scenario: 'enterprise-home-to-customer-service', route: await routeName(enterprise.page), studentPracticeRequests: 0 })
    await enterprise.context.close()

    const member = await createPage(browser, true)
    await member.page.goto(`${baseUrl}?dev040=member#/pages/home`, { waitUntil: 'domcontentloaded' })
    await member.page.getByText('首页', { exact: true }).waitFor({ state: 'visible' })
    assert.equal(await member.page.getByText('AI助手', { exact: true }).count(), 1)
    assert.equal(await member.page.getByText('我的', { exact: true }).count(), 1)
    assert.equal(await member.page.locator('app-dynamic-tab-bar').count(), 0)
    await member.page.evaluate(() => {
      window.__dev040HomeRelaunch = []
      window.uni.reLaunch = (options) => { window.__dev040HomeRelaunch.push(options.url); options.success?.({}) }
    })
    await member.page.getByText('AI助手', { exact: true }).click()
    await member.page.getByText('我的', { exact: true }).click()
    assert.deepEqual(await member.page.evaluate(() => window.__dev040HomeRelaunch.slice()), ['/pages/center', '/pages/profile'])
    await member.page.evaluate(() => { window.uni.reLaunch = window.__failingDev040Relaunch || window.uni.reLaunch })
    await member.page.locator('.assessment-action').click()
    await member.page.waitForFunction(() => location.hash.includes('/pages/practice/exam-topics'))
    results.runtime.push({ scenario: 'student-home-to-training', route: await routeName(member.page) })
    await member.context.close()

    const answer = await createPage(browser, true)
    await answer.page.goto(`${baseUrl}?dev040=answer#/pages/practice/answer?id=p-040&sessionId=s-040&mode=standard`, { waitUntil: 'domcontentloaded' })
    await answer.page.locator('.question-card').waitFor({ state: 'visible' })
    await answer.page.evaluate(() => {
      window.__dev040Relaunch = []
      window.uni.navigateBack = (options) => options.fail?.({})
      window.uni.reLaunch = (options) => { window.__dev040Relaunch.push(options.url); options.success?.({}) }
    })
    await answer.page.locator('.answer-nav__back').click()
    assert.deepEqual(await answer.page.evaluate(() => window.__dev040Relaunch.slice()), ['/pages/practice/exam-assessment'])
    await answer.page.locator('.question-options__item').first().click()
    await answer.page.getByText('完成练习', { exact: true }).waitFor({ state: 'visible' })
    await answer.page.getByText('完成练习', { exact: true }).click()
    const answerRelaunch = await answer.page.evaluate(() => window.__dev040Relaunch.slice())
    assert.equal(answerRelaunch[0], '/pages/practice/exam-assessment')
    assert(answerRelaunch.slice(1).length >= 1 && answerRelaunch.slice(1).every((url) => url === '/pages/home'))
    results.runtime.push({ scenario: 'answer-fallback-and-complete', relaunch: answerRelaunch })
    await answer.context.close()

    const stacked = await createPage(browser, true)
    await stacked.page.goto(`${baseUrl}?dev040=stacked#/pages/practice/answer?id=p-040&sessionId=s-040&mode=standard`, { waitUntil: 'domcontentloaded' })
    await stacked.page.locator('.question-card').waitFor({ state: 'visible' })
    await stacked.page.evaluate(() => {
      window.__dev040BackCalls = 0
      window.uni.navigateBack = (options) => { window.__dev040BackCalls += 1; options.success?.({}) }
    })
    await stacked.page.locator('.answer-nav__back').click()
    assert.equal(await stacked.page.evaluate(() => window.__dev040BackCalls), 1)
    results.runtime.push({ scenario: 'answer-stack-navigate-back', calls: 1 })
    await stacked.context.close()

    const logout = await createPage(browser, true)
    await logout.page.goto(`${baseUrl}?dev040=logout#/pages/profile/settings`, { waitUntil: 'domcontentloaded' })
    await logout.page.getByText('退出登录', { exact: true }).waitFor({ state: 'visible' })
    await logout.page.evaluate(() => {
      window.__dev040LogoutRelaunch = []
      window.uni.showModal = (options) => options.success?.({ confirm: true, cancel: false })
      window.uni.reLaunch = (options) => { window.__dev040LogoutRelaunch.push(options.url); options.success?.({}) }
    })
    await logout.page.getByText('退出登录', { exact: true }).click()
    await logout.page.waitForFunction(() => window.__dev040LogoutRelaunch.length > 0)
    assert.equal((await logout.page.evaluate(() => window.__dev040LogoutRelaunch.slice())).at(-1), '/pages/auth/login')
    results.runtime.push({ scenario: 'logout-to-login', route: '/pages/auth/login' })
    await logout.context.close()
  } finally {
    await browser.close()
  }
}

;(async () => {
  try {
    auditSource()
    await runRuntime()
    results.status = 'passed'
  } catch (error) {
    results.status = 'failed'
    results.errors.push(error?.stack || String(error))
    throw error
  } finally {
    results.finishedAt = new Date().toISOString()
    fs.writeFileSync(path.join(__dirname, 'playwright-results.json'), `${JSON.stringify(results, null, 2)}\n`, 'utf8')
  }
})()
