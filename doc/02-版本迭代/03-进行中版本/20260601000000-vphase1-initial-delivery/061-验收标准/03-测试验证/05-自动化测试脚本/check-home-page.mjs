import { createRequire } from 'node:module'
import fs from 'node:fs/promises'
import path from 'node:path'

const timeoutMs = 10_000
const workspaceRoot = path.resolve(import.meta.dirname, '../../../../../../..')
const appRoot = path.join(workspaceRoot, 'code', 'develop', 'yunjikeji')
const resultsDir = path.join(import.meta.dirname, '..', 'DEV-031')
const require = createRequire(path.join(appRoot, 'package.json'))
const { chromium } = require('playwright')
const configuredUrl = process.env.HOME_TEST_BASE_URL
if (!configuredUrl) throw new Error('HOME_TEST_BASE_URL must point to an already running H5 server.')
const configuredBase = new URL(configuredUrl)
const baseUrl = configuredBase.pathname.replace(/\/$/, '').endsWith('/yunjikeji')
  ? configuredUrl.replace(/\/$/, '')
  : `${configuredUrl.replace(/\/$/, '')}/yunjikeji`
const homeUrl = `${baseUrl}/#/pages/home`
const viewports = [
  { name: '360x800', width: 360, height: 800 },
  { name: '390x844', width: 390, height: 844 },
  { name: '430x932', width: 430, height: 932 }
]

const rect = (element) => {
  const value = element.getBoundingClientRect()
  return { x: value.x, y: value.y, width: value.width, height: value.height, top: value.top, bottom: value.bottom }
}

async function waitForHome(page) {
  await page.goto(homeUrl, { waitUntil: 'networkidle', timeout: timeoutMs })
  await page.locator('.home-page').waitFor({ state: 'visible', timeout: timeoutMs })
  await page.locator('.feature-card--self').waitFor({ state: 'visible', timeout: timeoutMs })
}

async function captureNavigation(page, selector, expectedMethod, expectedUrl) {
  await waitForHome(page)
  await page.evaluate(() => {
    const calls = []
    for (const method of ['navigateTo', 'reLaunch']) {
      window.uni[method] = (options = {}) => {
        calls.push({ method, url: options.url || '' })
        options.success?.({ errMsg: `${method}:ok` })
        options.complete?.({ errMsg: `${method}:ok` })
        return Promise.resolve({ errMsg: `${method}:ok` })
      }
    }
    window.__dev031NavigationCalls = calls
  })
  await page.locator(selector).click({ timeout: timeoutMs })
  const actual = await page.evaluate(() => window.__dev031NavigationCalls.at(-1) || null)
  return { expectedMethod, expectedUrl, actual, passed: actual?.method === expectedMethod && actual?.url === expectedUrl }
}

async function inspectViewport(browser, viewport, enterpriseBranchPresent) {
  const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } })
  const consoleErrors = []
  const pageErrors = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('pageerror', (error) => pageErrors.push(error.message))
  try {
    await waitForHome(page)
    const geometry = await page.evaluate(() => {
      const rect = (element) => {
        const value = element.getBoundingClientRect()
        return { x: value.x, y: value.y, width: value.width, height: value.height, top: value.top, bottom: value.bottom }
      }
      const primary = document.querySelector('.feature-card--self')
      const exam = document.querySelector('.feature-card--exam')
      const wrong = document.querySelector('.feature-card--redo')
      const grid = document.querySelector('.assessment-grid')
      const tab = document.querySelector('.home-tab-bar')
      const owl = document.querySelector('.home-tab-bar__mascot-wrap')
      const owlImage = document.querySelector('.home-tab-bar__mascot')
      const activeIcon = document.querySelector('.home-tab-bar__item--active .uv-icon')
      const labelElements = [...document.querySelectorAll('.home-tab-bar__item > uni-text')]
      const labels = labelElements.map((item) => ({
        text: item.textContent.trim(),
        fontSize: getComputedStyle(item).fontSize,
        rect: rect(item)
      }))
      const cards = [...document.querySelectorAll('.feature-card')]
      const illustrationAreas = cards.map((card) => {
        const visual = card.querySelector('.card-visual')
        const c = card.getBoundingClientRect()
        const v = visual?.getBoundingClientRect()
        const visibleWidth = v ? Math.max(0, Math.min(c.right, v.right) - Math.max(c.left, v.left)) : 0
        const visibleHeight = v ? Math.max(0, Math.min(c.bottom, v.bottom) - Math.max(c.top, v.top)) : 0
        return { cardArea: c.width * c.height, visualArea: visibleWidth * visibleHeight }
      })
      const gridStyle = grid ? getComputedStyle(grid) : null
      const textOverflow = [...document.querySelectorAll('.home-hero__copy, .section-heading__copy, .feature-card__copy, .home-tab-bar__item > uni-text')]
        .filter((element) => element.scrollWidth > element.clientWidth + 1)
        .map((element) => element.className)
      const owlStyle = owl ? getComputedStyle(owl) : null
      const centerLabel = labels.find((label) => label.text === 'AI工作台')
      return {
        scrollWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        primary: primary && rect(primary), exam: exam && rect(exam), wrong: wrong && rect(wrong),
        gridGap: gridStyle ? Number.parseFloat(gridStyle.columnGap) : null,
        tab: tab && rect(tab), owl: owl && rect(owl), owlImage: owlImage && rect(owlImage),
        owlStyle: owlStyle && { borderWidth: owlStyle.borderWidth, borderColor: owlStyle.borderColor, borderRadius: owlStyle.borderRadius, overflow: owlStyle.overflow },
        centerLabelOverlap: owl && centerLabel ? Math.max(0, rect(owl).bottom - centerLabel.rect.top) : null,
        activeIcon: activeIcon && rect(activeIcon), labels, illustrationAreas, textOverflow
      }
    })
    await page.screenshot({ path: path.join(resultsDir, `home-${viewport.name}.png`), fullPage: true })
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await page.waitForTimeout(120)
    const bottom = await page.evaluate(() => {
      const rect = (element) => {
        const value = element.getBoundingClientRect()
        return { top: value.top, bottom: value.bottom, height: value.height }
      }
      return { tab: rect(document.querySelector('.home-tab-bar')), finalCard: rect(document.querySelector('.feature-card--service')) }
    })
    const navigation = {
      selfAssessment: await captureNavigation(page, '.feature-card--self', 'reLaunch', '/pages/center'),
      practiceAssessment: await captureNavigation(page, '.feature-card--exam', 'navigateTo', '/pages/practice'),
      wrongRedo: await captureNavigation(page, '.feature-card--redo', 'navigateTo', '/pages/practice'),
      jobs: await captureNavigation(page, '.feature-card--jobs', 'navigateTo', '/pages/jobs'),
      customerService: await captureNavigation(page, '.feature-card--service', 'navigateTo', '/pages/service/customer-service-chat?conversationId=default'),
      aiWorkspace: await captureNavigation(page, '.home-tab-bar__item--center', 'reLaunch', '/pages/center'),
      profile: await captureNavigation(page, '.home-tab-bar__item:last-child', 'reLaunch', '/pages/profile'),
      enterpriseCustomerServiceSourceBranch: { expectedUrl: '/pages/service/customer-service', passed: enterpriseBranchPresent }
    }
    const ratio = geometry.primary && geometry.exam ? geometry.primary.width / (geometry.primary.width + geometry.exam.width + (geometry.gridGap || 0)) : 0
    const gapOk = geometry.gridGap >= 8 && geometry.gridGap <= 14
    const heightOk = Boolean(geometry.primary && geometry.exam && geometry.wrong
      && Math.abs(geometry.primary.height - geometry.exam.height - geometry.wrong.height - (geometry.gridGap || 0)) <= 4)
    const illustrationsOk = geometry.illustrationAreas.length === 5
      && geometry.illustrationAreas.every((area) => area.visualArea >= area.cardArea * 0.25)
    const tabMetricsOk = Boolean(geometry.activeIcon && geometry.owl && geometry.tab
      && geometry.activeIcon.width >= 20 && geometry.activeIcon.width <= 26
      && geometry.owl.width >= 56 && geometry.owl.width <= 68
      && geometry.tab.top - geometry.owl.top >= 14 && geometry.tab.top - geometry.owl.top <= 24
      && geometry.labels.map((label) => label.text).join('|') === '首页|AI工作台|我的'
      && geometry.labels.every((label) => Number.parseFloat(label.fontSize) >= 11 && Number.parseFloat(label.fontSize) <= 14
        && label.rect.top >= 0 && label.rect.bottom <= geometry.viewportHeight)
      && geometry.centerLabelOverlap <= 0.5)
    const passed = geometry.scrollWidth <= geometry.viewportWidth
      && geometry.textOverflow.length === 0 && ratio >= 0.42 && ratio <= 0.48 && gapOk && heightOk
      && illustrationsOk && tabMetricsOk && bottom.finalCard.bottom <= bottom.tab.top - 1
      && Object.values(navigation).every((entry) => entry.passed) && consoleErrors.length === 0 && pageErrors.length === 0
    return { viewport, screenshot: path.join(resultsDir, `home-${viewport.name}.png`), geometry, bottom,
      checks: { gridRatio: ratio, gridRatioOk: ratio >= 0.42 && ratio <= 0.48, gapOk, heightOk, illustrationsOk, tabMetricsOk,
        noHorizontalOverflow: geometry.scrollWidth <= geometry.viewportWidth, noTextClipping: geometry.textOverflow.length === 0,
        centerLabelClearOfOwl: geometry.centerLabelOverlap <= 0.5,
        finalCardClearOfTabBar: bottom.finalCard.bottom <= bottom.tab.top - 1, noConsoleErrors: consoleErrors.length === 0, noPageErrors: pageErrors.length === 0 },
      navigation, consoleErrors, pageErrors, passed }
  } finally { await page.close() }
}

await fs.mkdir(resultsDir, { recursive: true })
let browser
let evidence
try {
  const response = await fetch(configuredUrl, { signal: AbortSignal.timeout(timeoutMs) })
  if (!response.ok) throw new Error(`H5 server unavailable: HTTP ${response.status}`)
  const homeSource = await fs.readFile(path.join(appRoot, 'src/pages/home.vue'), 'utf8')
  const enterpriseBranchPresent = homeSource.includes("appState.loginIdentity === 'enterprise'")
    && homeSource.includes("uni.reLaunch({ url: '/pages/service/customer-service' })")
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined, timeout: timeoutMs })
  const viewports = []
  for (const viewport of [{ name: '360x800', width: 360, height: 800 }, { name: '390x844', width: 390, height: 844 }, { name: '430x932', width: 430, height: 932 }]) viewports.push(await inspectViewport(browser, viewport, enterpriseBranchPresent))
  evidence = { generatedAt: new Date().toISOString(), homeUrl, viewports, passed: viewports.every((result) => result.passed) }
  if (!evidence.passed) process.exitCode = 1
} catch (error) {
  evidence = { generatedAt: new Date().toISOString(), homeUrl, viewports: [], passed: false, error: error instanceof Error ? error.message : String(error) }
  process.exitCode = 1
} finally {
  await browser?.close()
  await fs.writeFile(path.join(resultsDir, 'navigation-results.json'), `${JSON.stringify(evidence, null, 2)}\n`)
}
console.log(JSON.stringify(evidence, null, 2))
