const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd()] }))

const evidenceDir = __dirname
const baseUrl = 'http://127.0.0.1:5173/yunjikeji/'
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
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  })
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  await context.addInitScript(() => {
    localStorage.setItem('yunjikeji-user-session', JSON.stringify({
      type: 'object',
      data: { userId: 999, phone: '13800000000', token: 'dev036-css-token' }
    }))
  })
  const page = await context.newPage()
  await page.route('**/app-api/yj/practices/current**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, data: topics })
  }))
  await page.goto(`${baseUrl}?dev036-retest=${Date.now()}#/pages/practice/exam-assessment`, { waitUntil: 'domcontentloaded' })
  await page.locator('.practice-start-card').waitFor({ state: 'visible' })

  const computed = await page.evaluate(() => {
    const section = document.querySelector('.topic-section')
    const heading = document.querySelector('.topic-section__heading')
    const swiper = document.querySelector('.topic-swiper')
    const intro = document.querySelector('.practice-start__intro')
    const card = document.querySelector('.practice-start-card')
    const rect = (element) => element ? {
      top: element.getBoundingClientRect().top,
      bottom: element.getBoundingClientRect().bottom,
      width: element.getBoundingClientRect().width,
      height: element.getBoundingClientRect().height
    } : null
    return {
      viewport: { width: innerWidth, height: innerHeight },
      headingExists: Boolean(heading),
      forbiddenHeadingTextPresent: document.body.innerText.includes('题型分类') || document.body.innerText.includes('左右滑动切换分类'),
      section: section ? {
        backgroundColor: getComputedStyle(section).backgroundColor,
        boxShadow: getComputedStyle(section).boxShadow,
        padding: getComputedStyle(section).padding
      } : null,
      intro: intro ? {
        exists: true,
        visible: getComputedStyle(intro).display !== 'none' && intro.getBoundingClientRect().height > 0,
        display: getComputedStyle(intro).display,
        visibility: getComputedStyle(intro).visibility,
        height: getComputedStyle(intro).height,
        padding: getComputedStyle(intro).padding,
        text: intro.textContent.trim()
      } : { exists: false, visible: false },
      rects: { swiper: rect(swiper), intro: rect(intro), card: rect(card) },
      swiperToCardGap: swiper && card ? card.getBoundingClientRect().top - swiper.getBoundingClientRect().bottom : null
    }
  })

  computed.verdict = computed.intro.visible ? 'fail' : 'pass'
  computed.reason = computed.intro.visible
    ? 'The page-scoped selector does not hide the child component intro; the card is not directly below the category swiper.'
    : 'The child intro is hidden and the card follows the category swiper.'
  fs.writeFileSync(path.join(evidenceDir, 'chrome-css-retest-results.json'), `${JSON.stringify(computed, null, 2)}\n`)
  await page.screenshot({ path: path.join(evidenceDir, 'retest-assessment-390x844-full.png'), fullPage: true })
  await browser.close()
})()
