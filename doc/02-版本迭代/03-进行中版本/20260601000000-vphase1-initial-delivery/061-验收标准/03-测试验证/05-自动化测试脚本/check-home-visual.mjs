import { createRequire } from 'node:module'
import fs from 'node:fs/promises'
import path from 'node:path'

const timeoutMs = 10_000
const workspaceRoot = path.resolve(import.meta.dirname, '../../../../../../..')
const appRoot = path.join(workspaceRoot, 'code', 'develop', 'yunjikeji')
const resultsDir = path.join(import.meta.dirname, '..', 'DEV-031')
const require = createRequire(path.join(appRoot, 'package.json'))
const { chromium } = require('playwright')
const serverUrl = process.env.HOME_TEST_BASE_URL?.replace(/\/$/, '')
if (!serverUrl) throw new Error('HOME_TEST_BASE_URL is required; this script does not start a server.')
const homeUrl = `${serverUrl.endsWith('/yunjikeji') ? serverUrl : `${serverUrl}/yunjikeji`}/#/pages/home`
const viewports = [{ name: '360x800', width: 360, height: 800 }, { name: '390x844', width: 390, height: 844 }, { name: '430x932', width: 430, height: 932 }]

async function inspect(browser, viewport) {
  const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } })
  const errors = []
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  try {
    await page.goto(homeUrl, { waitUntil: 'networkidle', timeout: timeoutMs })
    await page.locator('.home-page').waitFor({ state: 'visible', timeout: timeoutMs })
    await page.locator('.feature-card--self').waitFor({ state: 'visible', timeout: timeoutMs })
    const screenshot = path.join(resultsDir, `home-${viewport.name}.png`)
    await page.screenshot({ path: screenshot, fullPage: true, timeout: timeoutMs })
    const stat = await fs.stat(screenshot)
    const summary = await page.evaluate(() => ({
      assessmentCards: document.querySelectorAll('.assessment-grid .feature-card').length,
      utilityCards: document.querySelectorAll('.common-grid .feature-card').length,
      heroOwl: Boolean(document.querySelector('.home-hero__mascot-wrap')),
      illustrations: document.querySelectorAll('.card-visual').length,
      illustrationLayers: [...document.querySelectorAll('.card-visual')].reduce((total, visual) => total + visual.querySelectorAll('*').length, 0),
      tabs: document.querySelectorAll('.home-tab-bar__item').length,
      tabLabels: [...document.querySelectorAll('.home-tab-bar__item > uni-text')].map((item) => item.textContent.trim()),
      owl: Boolean(document.querySelector('.home-tab-bar__mascot-wrap')),
      scrollWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth
    }))
    const passed = stat.size > 1024 && summary.assessmentCards === 3 && summary.utilityCards === 2 && summary.heroOwl
      && summary.illustrations === 5 && summary.illustrationLayers >= 15 && summary.tabs === 3
      && summary.tabLabels.join('|') === '首页|AI工作台|我的'
      && summary.owl && summary.scrollWidth <= summary.viewportWidth && errors.length === 0
    return { viewport, screenshot, screenshotBytes: stat.size, summary, consoleErrors: errors, passed }
  } finally { await page.close() }
}

await fs.mkdir(resultsDir, { recursive: true })
let browser
let evidence
try {
  const response = await fetch(serverUrl, { signal: AbortSignal.timeout(timeoutMs) })
  if (!response.ok) throw new Error(`H5 server unavailable: HTTP ${response.status}`)
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined, timeout: timeoutMs })
  const captures = []
  for (const viewport of viewports) captures.push(await inspect(browser, viewport))
  evidence = { generatedAt: new Date().toISOString(), serverUrl, homeUrl, captures, passed: captures.every((capture) => capture.passed) }
  await fs.writeFile(path.join(resultsDir, 'playwright-results.json'), `${JSON.stringify(evidence, null, 2)}\n`)
  if (!evidence.passed) process.exitCode = 1
} finally { await browser?.close() }
console.log(JSON.stringify(evidence, null, 2))
