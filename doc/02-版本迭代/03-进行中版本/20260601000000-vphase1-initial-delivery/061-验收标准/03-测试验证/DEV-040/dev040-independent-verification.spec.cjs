const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd()] }))

const repoRoot = path.resolve(__dirname, '../../../../../../..')
const appRoot = path.join(repoRoot, 'code/develop/yunjikeji/src')
const baseUrl = process.env.DEV040_BASE_URL || 'http://127.0.0.1:5173/yunjikeji/'
const baselineRef = 'HEAD'
const remoteRef = 'origin/feature/20260601000000-vphase1-initial-delivery'
const resultPath = path.join(__dirname, 'independent-playwright-results.json')
const auditPath = path.join(__dirname, 'independent-source-audit.json')
const results = { startedAt: new Date().toISOString(), baseUrl, runtime: [], errors: [] }

const normalize = (value) => value.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n')
const read = (relative) => normalize(fs.readFileSync(path.join(appRoot, relative), 'utf8'))
const git = (args) => normalize(execFileSync('git', args, { cwd: repoRoot, encoding: 'utf8' }))
const show = (ref, relative) => git(['show', `${ref}:code/develop/yunjikeji/src/${relative}`])
const block = (source, tag) => source.match(new RegExp(`<${tag}[^>]*>[\\s\\S]*?<\\/${tag}>`))?.[0] || ''
const conditions = (source) => Array.from(source.matchAll(/(?:v-(?:if|else-if|show)|:(?:disabled|loading))="([^"]+)"/g), (match) => match[0])
const storage = (data) => JSON.stringify({ type: Array.isArray(data) ? 'array' : typeof data, data })

const auditSource = () => {
  const files = ['pages/auth/login.vue', 'pages/home.vue', 'pages/index.vue', 'pages/practice/answer.vue']
  const current = Object.fromEntries(files.map((file) => [file, read(file)]))
  const baseline = Object.fromEntries(files.map((file) => [file, show(baselineRef, file)]))

  for (const file of files) {
    const currentTemplate = file === 'pages/home.vue'
      ? block(current[file], 'template').replace(' v-if="homeReady"', '')
      : block(current[file], 'template')
    assert.equal(currentTemplate, block(baseline[file], 'template'), `${file} template changed beyond the home render gate`)
    assert.equal(block(current[file], 'style'), block(baseline[file], 'style'), `${file} style changed`)
  }

  const normalizedLogin = current['pages/auth/login.vue']
    .replace(/redirectUrl \|\| '\/pages\/home'/g, "redirectUrl || '/pages/service/customer-service'")
    .replace(/url: '\/pages\/home'\n  \}\)\n\}/, "url: '/pages/practice'\n  })\n}")
  assert.equal(block(normalizedLogin, 'script'), block(baseline['pages/auth/login.vue'], 'script'), 'login branch order changed beyond three defaults')

  const normalizedAnswer = current['pages/practice/answer.vue']
    .replace("url: '/pages/practice/exam-assessment'", "url: '/pages/practice'")
    .replace("url: '/pages/home'", "url: '/pages/practice'")
  assert.equal(block(normalizedAnswer, 'script'), block(baseline['pages/practice/answer.vue'], 'script'), 'answer changed beyond two navigation literals')

  const examCurrent = read('pages/practice/exam-assessment.vue')
  const examBaseline = show(baselineRef, 'pages/practice/exam-assessment.vue')
  assert.equal(examCurrent, examBaseline, 'exam assessment differs from DEV-039 baseline')
  assert.deepEqual(conditions(current['pages/practice/answer.vue']), conditions(baseline['pages/practice/answer.vue']), 'answer conditions changed')
  assert.deepEqual(conditions(examCurrent), conditions(examBaseline), 'assessment conditions changed')

  const pages = JSON.parse(read('pages.json'))
  assert.equal(pages.pages[0].path, 'pages/home', 'pages.json first page is not home')
  assert.doesNotMatch(current['pages/home.vue'], /AppDynamicTabBar/)
  assert.match(current['pages/home.vue'], /<view v-if="homeReady" class="preview-page">/)
  assert.match(current['pages/home.vue'], /const homeReady = ref\(false\)/)
  assert.match(current['pages/home.vue'], /function guardHome\(\) \{\s*homeReady\.value = requireLogin\(\)\s*}/)
  assert.match(current['pages/home.vue'], /onLoad\(guardHome\)/)
  assert.match(current['pages/home.vue'], /onShow\(guardHome\)/)

  const remoteLogin = show(remoteRef, 'pages/auth/login.vue')
  const remoteSms = {
    sendLoginSmsCode: (remoteLogin.match(/sendLoginSmsCode/g) || []).length,
    countdown60: (remoteLogin.match(/codeCountdown\.value = 60/g) || []).length,
    mutualExclusion: (remoteLogin.match(/codeCountdown\.value > 0 \|\| loginLoading\.value/g) || []).length,
    disabledBinding: (remoteLogin.match(/codeCountdown > 0 \|\| loginLoading/g) || []).length,
    tapBinding: (remoteLogin.match(/@tap="requestVerifyCode"/g) || []).length
  }
  assert(remoteSms.sendLoginSmsCode >= 2, 'remote sendLoginSmsCode missing')
  assert.equal(remoteSms.countdown60, 1, 'remote 60 second countdown missing')
  assert.equal(remoteSms.mutualExclusion, 1, 'remote countdown/loginLoading guard missing')
  assert(remoteSms.disabledBinding >= 1, 'remote disabled binding missing')
  assert.equal(remoteSms.tapBinding, 1, 'remote requestVerifyCode binding missing')

  const currentSmsIntegrated = /sendLoginSmsCode/.test(current['pages/auth/login.vue']) && /codeCountdown\.value = 60/.test(current['pages/auth/login.vue'])
  const namedWorkingTreeChanges = git(['diff', '--name-only', baselineRef]).trim().split('\n').filter(Boolean)
  const forbiddenTargets = [
    'pages.json',
    'pages/practice/exam-assessment.vue',
    'components/AppDynamicTabBar.vue',
    'stores/appState.ts'
  ]
  const forbiddenTargetDiffs = forbiddenTargets.filter((file) => read(file) !== show(baselineRef, file))

  const audit = {
    status: currentSmsIntegrated ? 'passed' : 'passed-with-final-integration-gate',
    baselineRef: git(['rev-parse', baselineRef]).trim(),
    remoteRef: git(['rev-parse', remoteRef]).trim(),
    applicationWhitelist: files.map((file) => `code/develop/yunjikeji/src/${file}`),
    pagesFirst: pages.pages[0].path,
    templatesUnchanged: true,
    assessmentAndAnswerConditionsUnchanged: true,
    answerOnlyTwoNavigationLiterals: true,
    loginOnlyThreeDefaultRoutes: true,
    forbiddenTargetDiffs,
    concurrentWorkingTreeChanges: namedWorkingTreeChanges.filter((file) => !files.map((item) => `code/develop/yunjikeji/src/${item}`).includes(file)),
    remoteSms,
    currentSmsIntegrated,
    finalIntegrationReady: currentSmsIntegrated
  }
  fs.writeFileSync(auditPath, `${JSON.stringify(audit, null, 2)}\n`, 'utf8')
  return audit
}

const sessionData = {
  userId: 999,
  phone: '13800000000',
  name: 'DEV-040',
  role: '无人机培训学员',
  token: 'dev040-token',
  refreshToken: 'dev040-refresh',
  expiresTime: '2099-01-01T00:00:00Z',
  loggedInAt: new Date().toISOString()
}

const customerResponse = {
  customerId: 701,
  tenantId: 1,
  mobile: '13800000000',
  nickname: '验收学员',
  auditStatus: 2,
  accessToken: 'student-token',
  refreshToken: 'student-refresh',
  expiresTime: '2099-01-01T00:00:00Z'
}

const companyResponse = (auditStatus = 0) => ({
  companyAccountFrontId: 801,
  tenantId: 2,
  username: '13800000000',
  status: true,
  auditStatus,
  accessToken: 'enterprise-token',
  refreshToken: 'enterprise-refresh',
  expiresTime: '2099-01-01T00:00:00Z'
})

const createPage = async (browser, fixture = {}) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  await context.addInitScript(({ session, identity, redirect, registration, watchGuestFlash }) => {
    if (session) localStorage.setItem('yunjikeji-user-session', session)
    if (identity) localStorage.setItem('yunjikeji-login-identity', identity)
    if (redirect) localStorage.setItem('yunjikeji-login-redirect', redirect)
    if (registration) localStorage.setItem('yunjikeji-enterprise-registration', registration)
    if (watchGuestFlash) {
      window.__dev040GuestSawHomeContent = false
      const inspect = () => {
        const text = document.body?.innerText || ''
        if (text.includes('AI助手') || text.includes('考题测评')) window.__dev040GuestSawHomeContent = true
      }
      const observe = () => {
        inspect()
        new MutationObserver(inspect).observe(document.documentElement, { childList: true, subtree: true, characterData: true })
      }
      if (document.documentElement) observe()
      else document.addEventListener('DOMContentLoaded', observe, { once: true })
    }
  }, {
    session: fixture.withSession ? storage(sessionData) : '',
    identity: fixture.identity ? storage(fixture.identity) : '',
    redirect: fixture.redirect ? storage(fixture.redirect) : '',
    registration: fixture.registration ? storage(fixture.registration) : '',
    watchGuestFlash: Boolean(fixture.watchGuestFlash)
  })

  await context.route('**/app-api/**', async (route) => {
    const url = new URL(route.request().url())
    const pathname = url.pathname
    let data = null
    if (pathname.endsWith('/customer-auth/login-or-register') || pathname.endsWith('/customer-auth/refresh-token')) data = customerResponse
    else if (pathname.endsWith('/customer-auth/me')) data = { customerId: 701, tenantId: 1, mobile: '13800000000', nickname: '验收学员' }
    else if (pathname.endsWith('/student-audit/my')) data = fixture.studentAudit === undefined ? { auditStatus: 2 } : fixture.studentAudit
    else if (pathname.endsWith('/company-auth/login-or-register') || pathname.endsWith('/company-auth/refresh-token')) data = companyResponse(fixture.enterpriseAuditStatus ?? 0)
    else if (pathname.endsWith('/company-auth/post-codes')) data = { hasWtPost: Boolean(fixture.hasWtPost), tenantId: fixture.hasWtPost ? 2 : undefined }
    else if (pathname.endsWith('/current')) data = [{ id: 'topic-a', fieldType: 'FT-A', index: '01', title: '判断题', categoryName: '判断题', categoryStatus: true, questionCount: 1, totalScore: 5, wrongQuestionCount: 0 }]
    else if (/\/practices\/[^/]+\/start$/.test(pathname)) data = { practiceId: 'practice-040', sessionId: 'session-040', nextPage: '/pages/practice/answer' }
    else if (pathname.endsWith('/question')) data = { practiceId: 'p-040', sessionId: 's-040', mode: 'standard', currentIndex: 0, totalQuestions: 1, answeredCount: 0, correctCount: 0, progressPercent: 100, question: { id: 'q-040', type: '单选题', title: 'DEV-040 路由验证题', stem: '请选择', score: 5, options: [{ id: 'A', label: 'A', content: '选项 A' }] } }
    else if (pathname.endsWith('/answers')) data = { questionId: 'q-040', selectedOptionId: 'A', selectedOptionIds: ['A'], correctOptionId: 'A', correctOptionIds: ['A'], correct: true, explanation: '完成', currentIndex: 0, nextQuestionIndex: 0, totalQuestions: 1, answeredCount: 1, correctCount: 1, progressPercent: 100, completed: true }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, data }) })
  })
  return { context, page: await context.newPage() }
}

const captureNavigation = (page) => page.evaluate(() => {
  window.__dev040Navigation = []
  for (const method of ['reLaunch', 'redirectTo', 'navigateTo']) {
    window.uni[method] = (options) => {
      window.__dev040Navigation.push({ method, url: options.url })
      options.success?.({})
    }
  }
})

const runLoginScenario = async (browser, scenario) => {
  const target = await createPage(browser, scenario)
  try {
    await target.page.goto(`${baseUrl}?case=${scenario.name}#/pages/auth/login?identity=${scenario.identity}`, { waitUntil: 'domcontentloaded' })
    await target.page.locator('.login-submit').waitFor({ state: 'visible' })
    await captureNavigation(target.page)
    const fields = target.page.locator('.login-field__input')
    await fields.nth(0).fill('13800000000')
    await fields.nth(1).fill('123456')
    await target.page.locator('.login-agreement').click()
    await target.page.locator('.login-submit').click()
    await target.page.waitForFunction(() => window.__dev040Navigation.length > 0)
    const actual = await target.page.evaluate(() => window.__dev040Navigation.at(-1))
    assert.deepEqual(actual, scenario.expected)
    results.runtime.push({ scenario: scenario.name, actual })
  } finally {
    await target.context.close()
  }
}

const runRuntime = async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.DEV040_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' })
  try {
    const guest = await createPage(browser, { watchGuestFlash: true })
    await guest.page.goto(`${baseUrl}?case=guest-home#/pages/home`, { waitUntil: 'domcontentloaded' })
    await guest.page.waitForFunction(() => location.hash.includes('/pages/auth/login'))
    assert.equal(await guest.page.evaluate(() => window.__dev040GuestSawHomeContent), false, 'guest observed home content before login redirect')
    const homeTextCount = await guest.page.getByText('考题测评', { exact: true }).count()
    assert.equal(homeTextCount, 0, 'guest home content remained in DOM after login redirect')
    results.runtime.push({ scenario: 'guest-home-no-content-flash', route: await guest.page.evaluate(() => location.hash), homeTextCount })
    await guest.context.close()

    for (const [name, hash, expected] of [
      ['guest-index-to-login', '/pages/index', '/pages/auth/login'],
      ['member-index-to-home', '/pages/index', '/pages/home']
    ]) {
      const target = await createPage(browser, { withSession: name.startsWith('member') })
      await target.page.goto(`${baseUrl}?case=${name}#${hash}`, { waitUntil: 'domcontentloaded' })
      await target.page.waitForFunction((route) => location.hash.includes(route), expected)
      results.runtime.push({ scenario: name, route: await target.page.evaluate(() => location.hash) })
      await target.context.close()
    }

    const member = await createPage(browser, { withSession: true })
    await member.page.goto(`${baseUrl}?case=member-home#/pages/home`, { waitUntil: 'domcontentloaded' })
    await member.page.getByText('首页', { exact: true }).waitFor({ state: 'visible' })
    await member.page.waitForTimeout(800)
    assert.match(await member.page.evaluate(() => location.hash), /\/pages\/home/)
    assert.equal(await member.page.locator('app-dynamic-tab-bar').count(), 0)
    await captureNavigation(member.page)
    await member.page.getByText('首页', { exact: true }).click()
    await member.page.getByText('AI助手', { exact: true }).click()
    await member.page.getByText('我的', { exact: true }).click()
    assert.deepEqual(await member.page.evaluate(() => window.__dev040Navigation), [
      { method: 'reLaunch', url: '/pages/home' },
      { method: 'reLaunch', url: '/pages/center' },
      { method: 'reLaunch', url: '/pages/profile' }
    ])
    results.runtime.push({ scenario: 'member-home-three-entry-and-no-loop', route: '#/pages/home' })
    await member.context.close()

    const homeAssessment = await createPage(browser, { withSession: true })
    await homeAssessment.page.goto(`${baseUrl}?case=home-assessment#/pages/home`, { waitUntil: 'domcontentloaded' })
    await homeAssessment.page.getByText('考题测评', { exact: true }).click()
    await homeAssessment.page.waitForFunction(() => location.hash.includes('/pages/practice/exam-assessment'))
    results.runtime.push({ scenario: 'home-to-assessment', route: await homeAssessment.page.evaluate(() => location.hash) })
    await homeAssessment.context.close()

    const assessment = await createPage(browser, { withSession: true })
    await assessment.page.goto(`${baseUrl}?case=assessment#/pages/practice/exam-assessment`, { waitUntil: 'domcontentloaded' })
    await assessment.page.getByText('开始练习', { exact: true }).waitFor({ state: 'visible' })
    await captureNavigation(assessment.page)
    await assessment.page.getByText('开始练习', { exact: true }).click()
    await assessment.page.waitForFunction(() => window.__dev040Navigation.length > 0)
    const answerUrl = await assessment.page.evaluate(() => window.__dev040Navigation[0].url)
    assert.equal(answerUrl, '/pages/practice/answer?id=practice-040&sessionId=session-040&mode=standard&topicId=FT-A&topicTitle=%E5%88%A4%E6%96%AD%E9%A2%98')
    await assessment.page.evaluate(() => {
      window.uni.navigateBack = (options) => options.fail?.({})
      window.__dev040Navigation = []
    })
    await assessment.page.locator('.assessment-nav__action').first().click()
    assert.deepEqual(await assessment.page.evaluate(() => window.__dev040Navigation), [{ method: 'reLaunch', url: '/pages/home' }])
    results.runtime.push({ scenario: 'assessment-answer-params-and-back', answerUrl, fallback: '/pages/home' })
    await assessment.context.close()

    const answer = await createPage(browser, { withSession: true })
    await answer.page.goto(`${baseUrl}?case=answer#/pages/practice/answer?id=p-040&sessionId=s-040&mode=standard`, { waitUntil: 'domcontentloaded' })
    await answer.page.locator('.question-card').waitFor({ state: 'visible' })
    await answer.page.evaluate(() => {
      window.__dev040Navigation = []
      window.uni.navigateBack = (options) => options.fail?.({})
      window.uni.reLaunch = (options) => { window.__dev040Navigation.push(options.url); options.success?.({}) }
    })
    await answer.page.locator('.answer-nav__back').click()
    assert.deepEqual(await answer.page.evaluate(() => window.__dev040Navigation), ['/pages/practice/exam-assessment'])
    await answer.page.locator('.question-options__item').first().click()
    await answer.page.getByText('完成练习', { exact: true }).waitFor({ state: 'visible' })
    await answer.page.getByText('完成练习', { exact: true }).click()
    assert((await answer.page.evaluate(() => window.__dev040Navigation)).slice(1).every((url) => url === '/pages/home'))
    results.runtime.push({ scenario: 'answer-fallback-and-complete', navigation: await answer.page.evaluate(() => window.__dev040Navigation) })
    await answer.context.close()

    const stacked = await createPage(browser, { withSession: true })
    await stacked.page.goto(`${baseUrl}?case=answer-stacked#/pages/practice/answer?id=p-040&sessionId=s-040&mode=standard`, { waitUntil: 'domcontentloaded' })
    await stacked.page.locator('.question-card').waitFor({ state: 'visible' })
    await stacked.page.evaluate(() => {
      window.__dev040BackCalls = 0
      window.uni.navigateBack = (options) => { window.__dev040BackCalls += 1; options.success?.({}) }
    })
    await stacked.page.locator('.answer-nav__back').click()
    assert.equal(await stacked.page.evaluate(() => window.__dev040BackCalls), 1)
    results.runtime.push({ scenario: 'answer-stack-navigate-back', calls: 1 })
    await stacked.context.close()

    const loginScenarios = [
      { name: 'student-approved-default', identity: 'student', studentAudit: { auditStatus: 2 }, expected: { method: 'reLaunch', url: '/pages/home' } },
      { name: 'student-approved-redirect', identity: 'student', redirect: '/pages/profile/settings', studentAudit: { auditStatus: 2 }, expected: { method: 'reLaunch', url: '/pages/profile/settings' } },
      { name: 'student-unbound-before-redirect', identity: 'student', redirect: '/pages/profile/settings', studentAudit: null, expected: { method: 'redirectTo', url: '/pages/enterprise/organization-bind?entry=login' } },
      { name: 'student-reviewing-baseline', identity: 'student', studentAudit: { auditStatus: 1 }, expected: { method: 'reLaunch', url: '/pages/home' } },
      { name: 'enterprise-post-default', identity: 'enterprise', hasWtPost: true, expected: { method: 'reLaunch', url: '/pages/home' } },
      { name: 'enterprise-audit-approved-default', identity: 'enterprise', enterpriseAuditStatus: 2, expected: { method: 'reLaunch', url: '/pages/home' } },
      { name: 'enterprise-post-redirect', identity: 'enterprise', hasWtPost: true, redirect: '/pages/profile/settings', expected: { method: 'reLaunch', url: '/pages/profile/settings' } },
      { name: 'enterprise-review-before-redirect', identity: 'enterprise', enterpriseAuditStatus: 1, redirect: '/pages/profile/settings', expected: { method: 'redirectTo', url: '/pages/enterprise/review?status=reviewing' } },
      { name: 'enterprise-registration-reviewing', identity: 'enterprise', registration: { status: 'reviewing', submittedAt: '2026-07-18', updatedAt: '2026-07-18' }, expected: { method: 'redirectTo', url: '/pages/enterprise/review?status=reviewing' } },
      { name: 'enterprise-register-default', identity: 'enterprise', expected: { method: 'redirectTo', url: '/pages/enterprise/register' } }
    ]
    for (const scenario of loginScenarios) await runLoginScenario(browser, scenario)

    const logout = await createPage(browser, { withSession: true })
    await logout.page.goto(`${baseUrl}?case=logout#/pages/profile/settings`, { waitUntil: 'domcontentloaded' })
    await logout.page.getByText('退出登录', { exact: true }).waitFor({ state: 'visible' })
    await logout.page.evaluate(() => {
      window.__dev040Logout = []
      window.uni.showModal = (options) => options.success?.({ confirm: true, cancel: false })
      window.uni.reLaunch = (options) => { window.__dev040Logout.push(options.url); options.success?.({}) }
    })
    await logout.page.getByText('退出登录', { exact: true }).click()
    await logout.page.waitForFunction(() => window.__dev040Logout.length > 0)
    assert.equal((await logout.page.evaluate(() => window.__dev040Logout)).at(-1), '/pages/auth/login')
    results.runtime.push({ scenario: 'logout-to-login', route: '/pages/auth/login' })
    await logout.context.close()
  } finally {
    await browser.close()
  }
}

;(async () => {
  try {
    const audit = auditSource()
    await runRuntime()
    results.status = audit.finalIntegrationReady ? 'passed' : 'passed-with-final-integration-gate'
  } catch (error) {
    results.status = 'failed'
    results.errors.push(error?.stack || String(error))
    throw error
  } finally {
    results.finishedAt = new Date().toISOString()
    fs.writeFileSync(resultPath, `${JSON.stringify(results, null, 2)}\n`, 'utf8')
  }
})()
