const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')

const projectRoot = process.cwd()
const requireFromProject = createRequire(path.join(projectRoot, 'package.json'))
const { chromium } = requireFromProject('playwright')

const outputDir = path.resolve(
  projectRoot,
  '../../../doc/02-版本迭代/03-进行中版本/20260601000000-vphase1-initial-delivery/061-验收标准/03-测试验证/DEV-032',
)
const url = 'http://127.0.0.1:5173/yunjikeji/#/pages/home-reference-preview'
const viewports = [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
]

fs.mkdirSync(outputDir, { recursive: true })

;(async () => {
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const results = []

for (const viewport of viewports) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 })
  const consoleErrors = []
  const failedRequests = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('requestfailed', (request) => {
    failedRequests.push({ url: request.url(), error: request.failure()?.errorText || 'unknown' })
  })

  const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 })
  await page.locator('.phone-screen').waitFor({ state: 'visible' })
  await page.screenshot({
    path: path.join(outputDir, `home-reference-${viewport.width}x${viewport.height}.png`),
    fullPage: false,
  })

  const audit = await page.evaluate(() => {
    const text = document.body.innerText
    const expectedTexts = [
      '5:30', '打卡', '273', 'Hi 我是Tony!', '你的智能创作AI助手',
      'AI创作', '一键智能生成爆款文案', '小红书创作', '小红书种草图文',
      '抖音创作', '抖音视频脚本', '朋友圈创作', '朋友圈每日问候',
      '回访话术', '知识库', '公众号', '图片生成', '数字分身',
      '智能助理', '一句话完成顾客营销与开单', '开单收银', 'AI智能开单',
      '预约查询', '预约查询录入', '添加顾客', '快速添加顾客',
      '帮我查一下今天的预约', '帮我分析下今天的数据', '有什么想法尽管问我',
      '首页', '学习', 'AI助手', '练口语', '会员',
    ]
    const missingTexts = expectedTexts.filter((item) => !text.includes(item))
    const rect = (selector) => {
      const el = document.querySelector(selector)
      if (!el) return null
      const value = el.getBoundingClientRect()
      return {
        x: Math.round(value.x * 10) / 10,
        y: Math.round(value.y * 10) / 10,
        width: Math.round(value.width * 10) / 10,
        height: Math.round(value.height * 10) / 10,
        bottom: Math.round(value.bottom * 10) / 10,
      }
    }
    const visible = (selector) => {
      const el = document.querySelector(selector)
      if (!el) return false
      const value = el.getBoundingClientRect()
      const style = getComputedStyle(el)
      return value.width > 0 && value.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
    }
    const imageAudit = [...document.querySelectorAll('.preview-page img')].map((img) => ({
      src: img.getAttribute('src'),
      complete: img.complete,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
    }))
    const navRects = [...document.querySelectorAll('.bottom-nav .nav-item')].map((el) => {
      const value = el.getBoundingClientRect()
      return { x: value.x, width: value.width }
    })
    const navWidthSpread = navRects.length
      ? Math.max(...navRects.map((item) => item.width)) - Math.min(...navRects.map((item) => item.width))
      : null
    const allElements = [...document.querySelectorAll('.preview-page *')]
    const screenshotLikeBackgrounds = allElements
      .map((el) => {
        const value = el.getBoundingClientRect()
        return {
          selector: el.className || el.tagName,
          backgroundImage: getComputedStyle(el).backgroundImage,
          width: value.width,
          height: value.height,
        }
      })
      .filter((item) =>
        /url\(/.test(item.backgroundImage) &&
        item.width >= innerWidth * 0.9 &&
        item.height >= innerHeight * 0.9
      )
    const phone = document.querySelector('.phone-screen')
    const owl = document.querySelector('.owl-ring')
    const bottomNav = document.querySelector('.bottom-nav')
    const owlRect = owl?.getBoundingClientRect()
    const navRect = bottomNav?.getBoundingClientRect()
    return {
      viewport: { width: innerWidth, height: innerHeight },
      documentWidths: {
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        bodyScrollWidth: document.body.scrollWidth,
        phoneScrollWidth: phone?.scrollWidth || null,
        phoneClientWidth: phone?.clientWidth || null,
      },
      missingTexts,
      counts: {
        statusBars: document.querySelectorAll('.status-bar').length,
        rewardPills: document.querySelectorAll('.reward-row .pill').length,
        closeButtons: document.querySelectorAll('.reward-row .close').length,
        creationCards: document.querySelectorAll('.creation-card').length,
        quickItems: document.querySelectorAll('.quick-item').length,
        assistantCards: document.querySelectorAll('.assistant-card').length,
        suggestions: document.querySelectorAll('.suggestions > uni-view, .suggestions > view').length,
        navItems: document.querySelectorAll('.bottom-nav .nav-item').length,
        images: imageAudit.length,
      },
      visible: {
        hero: visible('.top-area'),
        tony: visible('.tony'),
        createPanel: visible('.create-panel'),
        assistantPanel: visible('.assistant-panel'),
        suggestions: visible('.suggestions'),
        askBox: visible('.ask-box'),
        bottomNav: visible('.bottom-nav'),
        owl: visible('.owl-ring'),
      },
      rects: {
        phone: rect('.phone-screen'),
        hero: rect('.top-area'),
        tony: rect('.tony'),
        createPanel: rect('.create-panel'),
        xhsCard: rect('.xhs-card'),
        douyinCard: rect('.douyin-card'),
        momentsCard: rect('.moments-card'),
        assistantPanel: rect('.assistant-panel'),
        suggestions: rect('.suggestions'),
        askBox: rect('.ask-box'),
        bottomNav: rect('.bottom-nav'),
        owl: rect('.owl-ring'),
      },
      navRects,
      navWidthSpread,
      owlUpwardOffset: owlRect && navRect ? Math.round((navRect.top - owlRect.top) * 10) / 10 : null,
      images: imageAudit,
      screenshotLikeBackgrounds,
      bodyTextLength: text.length,
    }
  })

  const expectedCounts = {
    statusBars: 1,
    rewardPills: 2,
    closeButtons: 1,
    creationCards: 3,
    quickItems: 5,
    assistantCards: 3,
    suggestions: 2,
    navItems: 5,
    images: 5,
  }
  const checks = {
    httpOk: response?.ok() ?? false,
    textsComplete: audit.missingTexts.length === 0,
    countsComplete: Object.entries(expectedCounts).every(([key, value]) => audit.counts[key] === value),
    keySectionsVisible: Object.values(audit.visible).every(Boolean),
    imagesLoaded: audit.images.every((image) => image.complete && image.naturalWidth > 0 && image.naturalHeight > 0),
    noHorizontalOverflow:
      audit.documentWidths.scrollWidth <= audit.documentWidths.clientWidth &&
      audit.documentWidths.bodyScrollWidth <= viewport.width &&
      audit.documentWidths.phoneScrollWidth <= audit.documentWidths.phoneClientWidth,
    fiveEqualNavAreas: audit.navRects.length === 5 && audit.navWidthSpread <= 1,
    owlFloatsUpward: audit.owlUpwardOffset >= 15,
    noScreenshotBackground: audit.screenshotLikeBackgrounds.length === 0,
    noConsoleErrors: consoleErrors.length === 0,
    noFailedRequests: failedRequests.length === 0,
  }

  results.push({
    viewport,
    url,
    status: response?.status() || null,
    passed: Object.values(checks).every(Boolean),
    checks,
    consoleErrors,
    failedRequests,
    audit,
  })
  await page.close()
}

await browser.close()

const output = {
  generatedAt: new Date().toISOString(),
  command: 'pnpm exec node <DEV-032>/dev032-reference-home.spec.cjs',
  allPassed: results.every((result) => result.passed),
  results,
}
fs.writeFileSync(path.join(outputDir, 'test-results.json'), `${JSON.stringify(output, null, 2)}\n`)
console.log(JSON.stringify(output, null, 2))
process.exitCode = output.allPassed ? 0 : 1
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
