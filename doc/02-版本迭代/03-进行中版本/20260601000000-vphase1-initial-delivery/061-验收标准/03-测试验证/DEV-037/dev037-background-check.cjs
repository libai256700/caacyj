const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd()] }))

const repoRoot = path.resolve(__dirname, '../../../../../../..')
const appRoot = path.join(repoRoot, 'code/develop/yunjikeji')
const sourceRelative = 'code/develop/yunjikeji/src/pages/practice/exam-assessment.vue'
const sourcePath = path.join(repoRoot, sourceRelative)
const dev036ResultsPath = path.join(__dirname, '../DEV-036/playwright-results.json')
const baseUrl = 'http://127.0.0.1:5173/yunjikeji/'

const currentSource = fs.readFileSync(sourcePath, 'utf8')
const headSource = execFileSync('git', ['show', `HEAD:${sourceRelative}`], { cwd: repoRoot, encoding: 'utf8' })
const expectedSource = headSource
  .replace('#edf7ff', '#F5F0EA')
  .replace('rgba(226,244,255,.94)', 'rgba(247,161,106,.94)')
  .replace('rgba(244,250,255,.92)', 'rgba(248,220,200,.92)')
  .replace('#f3f8fc', '#F5F0EA')

const count = (text, needle) => text.split(needle).length - 1
const staticCheck = {
  COLOR_MAP_ONLY: currentSource === expectedSource ? 1 : 0,
  STRUCTURE_PRESERVED: currentSource === expectedSource ? 1 : 0,
  expectedNewCounts: {
    '#F5F0EA': count(currentSource, '#F5F0EA'),
    'rgba(247,161,106,.94)': count(currentSource, 'rgba(247,161,106,.94)'),
    'rgba(248,220,200,.92)': count(currentSource, 'rgba(248,220,200,.92)')
  },
  remainingOldCounts: {
    '#edf7ff': count(currentSource, '#edf7ff'),
    'rgba(226,244,255,.94)': count(currentSource, 'rgba(226,244,255,.94)'),
    'rgba(244,250,255,.92)': count(currentSource, 'rgba(244,250,255,.92)'),
    '#f3f8fc': count(currentSource, '#f3f8fc')
  },
  structureTokens: {
    linearGradient: currentSource.includes('linear-gradient(180deg,'),
    stops: currentSource.includes('.94) 0%,') && currentSource.includes('.92) 58%,') && currentSource.includes('100%)'),
    backgroundAsset: currentSource.includes("url('@/static/backgrounds/focus-atmosphere.png') right top / 100% auto no-repeat")
  }
}

assert.equal(staticCheck.COLOR_MAP_ONLY, 1)
assert.equal(staticCheck.STRUCTURE_PRESERVED, 1)
assert.deepEqual(staticCheck.expectedNewCounts, {
  '#F5F0EA': 2,
  'rgba(247,161,106,.94)': 1,
  'rgba(248,220,200,.92)': 1
})
assert(Object.values(staticCheck.remainingOldCounts).every((value) => value === 0))
assert(Object.values(staticCheck.structureTokens).every(Boolean))

const topics = [
  { id: 'topic-a', fieldType: 'FT-A', index: '01', title: '判断题', categoryName: '判断题', categoryStatus: true, questionCount: 10, totalScore: 20, wrongQuestionCount: 0 },
  { id: 'topic-b', fieldType: 'FT-B', index: '02', title: '单选题', categoryName: '单选题', categoryStatus: true, questionCount: 20, totalScore: 40, wrongQuestionCount: 2 },
  { id: 'topic-c', index: '03', title: '多选题', categoryName: '多选题', categoryStatus: true, questionCount: 30, totalScore: 60, wrongQuestionCount: 3 },
  { id: 'topic-d', fieldType: 'FT-D', index: '04', title: '填空题', categoryName: '填空题', categoryStatus: true, questionCount: 15, totalScore: 30, wrongQuestionCount: 1 },
  { id: 'topic-e', fieldType: 'FT-E', index: '05', title: '简答题', categoryName: '简答题', categoryStatus: true, questionCount: 5, totalScore: 50, wrongQuestionCount: 1 }
]

;(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.DEV037_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  })
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1 })
  await context.addInitScript(() => {
    localStorage.setItem('yunjikeji-user-session', JSON.stringify({
      type: 'object',
      data: { userId: 999, phone: '13800000000', token: 'dev037-token' }
    }))
  })
  const page = await context.newPage()
  const consoleErrors = []
  const pageErrors = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('pageerror', (error) => pageErrors.push(error.message))
  await page.route('**/app-api/yj/practices/current**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, data: topics })
  }))

  await page.goto(`${baseUrl}?dev037=${Date.now()}#/pages/practice/exam-assessment`, { waitUntil: 'domcontentloaded' })
  await page.locator('.practice-start-card').waitFor({ state: 'visible', timeout: 10000 })
  const runtime = await page.evaluate(() => {
    const tabs = [...document.querySelectorAll('.topic-tab')]
    const buttons = [...document.querySelectorAll('.practice-start-actions__primary,.practice-start-actions__secondary')]
    const pageElement = document.querySelector('.assessment-page')
    const backdrop = document.querySelector('.assessment-backdrop')
    return {
      title: document.title,
      bodyText: document.body.innerText,
      innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      pageBackgroundColor: getComputedStyle(pageElement).backgroundColor,
      backdropBackgroundImage: getComputedStyle(backdrop).backgroundImage,
      tabCount: tabs.length,
      tabY: tabs.map((element) => Math.round(element.getBoundingClientRect().y)),
      buttons: buttons.map((element) => {
        const rect = element.getBoundingClientRect()
        return { left: rect.left, right: rect.right, width: rect.width, height: rect.height }
      }),
      introDomCount: document.querySelectorAll('.practice-start__intro').length
    }
  })

  assert.equal(runtime.pageBackgroundColor, 'rgb(245, 240, 234)')
  assert(runtime.backdropBackgroundImage.includes('rgba(247, 161, 106, 0.94)'))
  assert(runtime.backdropBackgroundImage.includes('rgba(248, 220, 200, 0.92)'))
  assert(runtime.backdropBackgroundImage.includes('rgb(245, 240, 234)'))
  assert(runtime.backdropBackgroundImage.includes('focus-atmosphere.png'))
  assert(runtime.scrollWidth <= runtime.innerWidth + 1)
  assert(runtime.bodyScrollWidth <= runtime.innerWidth + 1)
  assert.equal(runtime.tabCount, 5)
  assert.equal(runtime.introDomCount, 0)
  for (const text of ['考题测评', '判断题', '题目分类', '题目编号', '题量', '总分', '答题时间', '阅卷方式', '开始练习', '错题复练']) {
    assert(runtime.bodyText.includes(text), `missing runtime content: ${text}`)
  }
  assert(runtime.buttons.every((button) => button.left >= 0 && button.right <= runtime.innerWidth + 1 && button.width > 0 && button.height > 0))

  const baseline = JSON.parse(fs.readFileSync(dev036ResultsPath, 'utf8')).viewports
    .find((item) => item.viewport.width === 390 && item.viewport.height === 844).layout
  const geometry = {
    tabYMatchesBaseline: JSON.stringify(runtime.tabY) === JSON.stringify(baseline.tabY),
    buttonsMatchBaseline: runtime.buttons.every((button, index) => {
      const prior = baseline.buttons[index]
      return ['left', 'right', 'width', 'height'].every((field) => Math.abs(button[field] - prior[field]) < 0.02)
    }),
    scrollWidthMatchesBaseline: runtime.scrollWidth === baseline.scrollWidth,
    bodyScrollWidthMatchesBaseline: runtime.bodyScrollWidth === baseline.bodyScrollWidth
  }
  assert(Object.values(geometry).every(Boolean))
  assert.equal(consoleErrors.length, 0)
  assert.equal(pageErrors.length, 0)

  await page.screenshot({ path: path.join(__dirname, 'assessment-warm-390x844.png') })
  await page.screenshot({ path: path.join(__dirname, 'assessment-warm-390x844-full.png'), fullPage: true })
  const result = {
    status: 'passed',
    url: page.url(),
    viewport: { width: 390, height: 844 },
    staticCheck,
    runtime,
    geometry,
    consoleErrors,
    pageErrors
  }
  fs.writeFileSync(path.join(__dirname, 'playwright-results.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
  await browser.close()
})()
