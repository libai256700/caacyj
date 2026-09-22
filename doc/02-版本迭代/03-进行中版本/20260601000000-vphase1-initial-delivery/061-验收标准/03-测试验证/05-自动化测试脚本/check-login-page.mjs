import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { createRequire } from 'node:module'
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { promisify } from 'node:util'

const requireFromApp = createRequire(path.resolve(process.cwd(), 'package.json'))
const { chromium } = requireFromApp('playwright')
const execFileAsync = promisify(execFile)

const url = process.env.LOGIN_URL || 'http://127.0.0.1:5190/yunjikeji/#/pages/auth/login'
const chromePath = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const evidenceDir = path.resolve(process.argv[2] || '.')
const sourcePath = path.resolve(process.cwd(), 'src/pages/auth/login.vue')
const viewports = [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 }
]

const requiredText = [
  '云技科技',
  'APP 端客户端项目',
  '学员登录',
  '企业登录',
  '账号',
  '验证码',
  '获取验证码',
  '登录',
  '第三方登录',
  '我已阅读并同意',
  '《用户协议》',
  '《隐私协议》',
  'ICP/SP 备案信息'
]

const keySelectors = [
  '.login-role-tabs',
  '.login-field:not(.login-field--code)',
  '.login-field--code',
  '.login-submit',
  '.login-agreement',
  '.login-third-party',
  '.login-icp'
]

const inRange = (value, min, max) => value >= min && value <= max
const normalizeLineEndings = value => value.replace(/\r\n/g, '\n')
const extractScriptSetup = source => source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)?.[1] || ''

const intersectionArea = (a, b) => {
  const width = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x))
  const height = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y))
  return width * height
}

await mkdir(evidenceDir, { recursive: true })
const results = {
  url,
  executedAt: new Date().toISOString(),
  chromePath,
  sourceChecks: {},
  viewports: [],
  status: 'FAILED'
}
const tabStateResults = {
  status: 'FAILED',
  executedAt: results.executedAt,
  requiredText: ['学员登录', '企业登录'],
  strictHalfTolerancePx: 1,
  commonAssertions: {},
  results: [],
  logicAssertions: {},
  evidenceSource: 'check-login-page.mjs'
}

let browser
try {
  const source = await readFile(sourcePath, 'utf8')
  const { stdout: headSource } = await execFileAsync(
    'git',
    ['show', 'HEAD:code/develop/yunjikeji/src/pages/auth/login.vue'],
    { cwd: process.cwd(), encoding: 'utf8' }
  )
  const sourceChecks = {
    scriptSetupUnchanged: normalizeLineEndings(extractScriptSetup(source)) === normalizeLineEndings(extractScriptSetup(headSource)),
    studentLogin: /loginStudent\(phone\.value,\s*verifyCode\.value\)/.test(source),
    enterpriseLogin: /loginEnterprise\(phone\.value,\s*verifyCode\.value\)/.test(source),
    roleBranch: /loginRole\.value === 'enterprise'/.test(source),
    loadingState: /loginLoading\.value = true/.test(source) && /loginLoading\.value = false/.test(source),
    loadingText: /loginLoading \? '登录中\.\.\.' : '登录'/.test(source),
    wechatHandler: /@tap="handleWechatLogin"/.test(source),
    agreementToggle: /@tap="toggleAgreement"/.test(source),
    userAgreement: /openAgreement\('user'\)/.test(source),
    privacyAgreement: /openAgreement\('privacy'\)/.test(source),
    internalPasswordInputUnchanged: /v-model="verifyCode"[\s\S]{0,120}type="text"[\s\S]{0,120}password[\s\S]{0,120}maxlength="32"/.test(source),
    verificationCodeDisplay: source.includes('<text class="login-field__label">验证码</text>')
      && source.includes('placeholder="请输入验证码"'),
    getCodeIsDisplayView: /<view class="login-field__get-code">获取验证码<\/view>/.test(source),
    getCodeHasNoInteraction: !/<(?:view|button)[^>]*class="login-field__get-code"[^>]*(?:@tap|@click)/.test(source),
    noSmsFlow: !/(?:request|send|get)VerifyCode|countdown|countDown|短信请求/.test(extractScriptSetup(source)),
    noFieldIcons: !/<view class="login-field__icon/.test(source),
    iosIsView: /<view class="ios-login"[^>]*>/.test(source),
    iosHasNoInteraction: !/<(?:view|button)[^>]*class="ios-login"[^>]*(?:@tap|@click)/.test(source),
    noIosHandler: !/(?:const|function)\s+handleIosLogin/.test(source),
    appleAsset: /<image class="ios-login__icon" src="\/static\/login\/apple-logo\.svg"/.test(source),
    noIosText: !/<text[^>]*>\s*iOS\s*<\/text>/.test(source)
  }
  assert.ok(Object.values(sourceChecks).every(Boolean), `Source behavior check failed: ${JSON.stringify(sourceChecks)}`)
  results.sourceChecks = sourceChecks

  browser = await chromium.launch({ executablePath: chromePath, headless: true })
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 })
    const page = await context.newPage()
    const pageErrors = []
    page.on('pageerror', error => pageErrors.push(error.message))

    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 })
    await page.locator('.login-page').waitFor({ state: 'visible' })

    for (const text of requiredText) {
      const locator = page.getByText(text, { exact: true }).first()
      await locator.waitFor({ state: 'visible' })
    }
    assert.equal(await page.getByText('密码', { exact: true }).count(), 0)
    assert.equal(await page.getByText('请输入密码', { exact: true }).count(), 0)
    assert.equal(await page.getByText('iOS', { exact: true }).count(), 0)

    const phoneInput = page.locator('.login-field:not(.login-field--code) .login-field__input input')
    const codeInput = page.locator('.login-field--code .login-field__input input')
    await phoneInput.fill('13800138000')
    await codeInput.fill('abcdef')
    assert.equal(await phoneInput.inputValue(), '13800138000')
    assert.equal(await codeInput.inputValue(), 'abcdef')
    await phoneInput.fill('')
    await codeInput.fill('')

    const readRoleSurface = () => page.evaluate(() => {
      const panel = document.querySelector('.login-content')
      const items = [...document.querySelectorAll('.login-role-tabs__item')]
      const activeItem = items.find(item => item.classList.contains('login-role-tabs__item--active'))
      const activeStyle = getComputedStyle(activeItem)
      const inactiveItem = items.find(item => item !== activeItem)
      const inactiveStyle = getComputedStyle(inactiveItem)
      const frostedSurface = getComputedStyle(panel, '::before')
      const activeSurface = getComputedStyle(panel, '::after')
      const panelWidth = panel.getBoundingClientRect().width
      return {
        panelClass: panel.className,
        panelWidth,
        itemWidths: items.map(item => item.getBoundingClientRect().width),
        itemCenterOffsets: items.map(item => {
          const panelRect = panel.getBoundingClientRect()
          const itemRect = item.getBoundingClientRect()
          return itemRect.left + itemRect.width / 2 - panelRect.left
        }),
        activeText: activeItem?.textContent?.trim() || '',
        activeItemBackground: activeStyle.backgroundColor,
        activeItemBackdropFilter: activeStyle.backdropFilter || activeStyle.webkitBackdropFilter,
        activeItemFilter: activeStyle.filter,
        inactiveItemBackground: inactiveStyle.backgroundColor,
        inactiveItemBackdropFilter: inactiveStyle.backdropFilter || inactiveStyle.webkitBackdropFilter,
        inactiveItemFilter: inactiveStyle.filter,
        activeSurfaceBackground: activeSurface.backgroundColor,
        activeSurfaceBackdropFilter: activeSurface.backdropFilter || activeSurface.webkitBackdropFilter,
        activeSurfaceFilter: activeSurface.filter,
        activeSurfaceLeft: activeSurface.left,
        activeSurfaceRight: activeSurface.right,
        activeSurfaceWidth: parseFloat(activeSurface.width),
        activeSurfaceTopLeftRadius: activeSurface.borderTopLeftRadius,
        activeSurfaceTopRightRadius: activeSurface.borderTopRightRadius,
        activeSurfaceBottomLeftRadius: activeSurface.borderBottomLeftRadius,
        activeSurfaceBottomRightRadius: activeSurface.borderBottomRightRadius,
        frostedSurfaceLeft: frostedSurface.left,
        frostedSurfaceRight: frostedSurface.right,
        frostedSurfaceWidth: parseFloat(frostedSurface.width),
        frostedSurfaceBackground: frostedSurface.backgroundColor,
        frostedSurfaceBackdropFilter: frostedSurface.backdropFilter || frostedSurface.webkitBackdropFilter,
        frostedSurfaceFilter: frostedSurface.filter,
        frostedSurfaceTopLeftRadius: frostedSurface.borderTopLeftRadius,
        frostedSurfaceTopRightRadius: frostedSurface.borderTopRightRadius,
        frostedSurfaceBottomLeftRadius: frostedSurface.borderBottomLeftRadius,
        frostedSurfaceBottomRightRadius: frostedSurface.borderBottomRightRadius
      }
    })

    const toTabGeometry = surface => {
      const parseOffset = (left, right, width) => {
        if (left !== 'auto') return parseFloat(left)
        return surface.panelWidth - parseFloat(right) - width
      }
      const activeStart = parseOffset(surface.activeSurfaceLeft, surface.activeSurfaceRight, surface.activeSurfaceWidth)
      const inactiveStart = parseOffset(surface.frostedSurfaceLeft, surface.frostedSurfaceRight, surface.frostedSurfaceWidth)
      const activeRect = { start: activeStart, end: activeStart + surface.activeSurfaceWidth, width: surface.activeSurfaceWidth }
      const inactiveRect = { start: inactiveStart, end: inactiveStart + surface.frostedSurfaceWidth, width: surface.frostedSurfaceWidth }
      const [leftSurface, rightSurface] = [
        { type: 'active', ...activeRect },
        { type: 'inactive', ...inactiveRect }
      ].sort((a, b) => a.start - b.start)
      const midpoint = surface.panelWidth / 2
      const overlap = Math.max(0, Math.min(activeRect.end, inactiveRect.end) - Math.max(activeRect.start, inactiveRect.start))
      const gap = Math.max(0, rightSurface.start - leftSurface.end)
      const activeIsLeft = activeRect.start < midpoint
      const inactiveVisibleRect = activeIsLeft
        ? { start: midpoint, end: surface.panelWidth, width: surface.panelWidth - midpoint }
        : { start: 0, end: midpoint, width: midpoint }
      const labelExpectedCenters = [surface.panelWidth * 0.25, surface.panelWidth * 0.75]
      return {
        containerWidth: surface.panelWidth,
        midpoint,
        leftSurface,
        rightSurface,
        activeRatio: activeRect.width / surface.panelWidth,
        inactiveVisibleRatio: inactiveVisibleRect.width / surface.panelWidth,
        inactiveUnderlayRatio: inactiveRect.width / surface.panelWidth,
        overlap,
        gap,
        underlap: overlap,
        outerEdgeDeviation: {
          left: Math.abs(Math.min(activeRect.start, inactiveRect.start)),
          right: Math.abs(Math.max(activeRect.end, inactiveRect.end) - surface.panelWidth)
        },
        labelCenters: {
          actual: surface.itemCenterOffsets,
          expected: labelExpectedCenters,
          ratios: surface.itemCenterOffsets.map(offset => offset / surface.panelWidth),
          deviations: surface.itemCenterOffsets.map((offset, index) => Math.abs(offset - labelExpectedCenters[index]))
        },
        tabItemWidths: surface.itemWidths,
        activeStyles: {
          surfaceBackground: surface.activeSurfaceBackground,
          surfaceBackdropFilter: surface.activeSurfaceBackdropFilter,
          surfaceFilter: surface.activeSurfaceFilter,
          itemBackground: surface.activeItemBackground,
          itemBackdropFilter: surface.activeItemBackdropFilter,
          itemFilter: surface.activeItemFilter,
          borderRadii: {
            topLeft: surface.activeSurfaceTopLeftRadius,
            topRight: surface.activeSurfaceTopRightRadius,
            bottomLeft: surface.activeSurfaceBottomLeftRadius,
            bottomRight: surface.activeSurfaceBottomRightRadius
          }
        },
        inactiveStyles: {
          surfaceBackground: surface.frostedSurfaceBackground,
          surfaceBackdropFilter: surface.frostedSurfaceBackdropFilter,
          surfaceFilter: surface.frostedSurfaceFilter,
          itemBackground: surface.inactiveItemBackground,
          itemBackdropFilter: surface.inactiveItemBackdropFilter,
          itemFilter: surface.inactiveItemFilter,
          borderRadii: {
            topLeft: surface.frostedSurfaceTopLeftRadius,
            topRight: surface.frostedSurfaceTopRightRadius,
            bottomLeft: surface.frostedSurfaceBottomLeftRadius,
            bottomRight: surface.frostedSurfaceBottomRightRadius
          }
        }
      }
    }

    const assertEqualRoleHalves = surface => {
      const halfWidth = surface.panelWidth / 2
      const expectedUnderlap = 58
      const geometry = toTabGeometry(surface)
      assert.ok(Math.abs(surface.activeSurfaceWidth - halfWidth) <= 1, `Active surface must occupy 50%: ${JSON.stringify(surface)}`)
      assert.ok(Math.abs(surface.frostedSurfaceWidth - (halfWidth + expectedUnderlap)) <= 1, `Frosted underlay must cross the midpoint by ${expectedUnderlap}px: ${JSON.stringify(surface)}`)
      assert.ok(surface.itemWidths.every(width => Math.abs(width - halfWidth) <= 1), `Role tabs must occupy equal halves: ${JSON.stringify(surface)}`)
      assert.ok(Math.abs(surface.itemCenterOffsets[0] - surface.panelWidth * 0.25) <= 1, `Student label must be centered in the left half: ${JSON.stringify(surface)}`)
      assert.ok(Math.abs(surface.itemCenterOffsets[1] - surface.panelWidth * 0.75) <= 1, `Enterprise label must be centered in the right half: ${JSON.stringify(surface)}`)
      assert.ok(Math.abs(geometry.activeRatio - 0.5) <= 0.005, `Active visible surface must remain 50%: ${JSON.stringify(geometry)}`)
      assert.ok(Math.abs(geometry.inactiveVisibleRatio - 0.5) <= 0.005, `Inactive visible surface must remain 50%: ${JSON.stringify(geometry)}`)
      assert.ok(Math.abs(geometry.underlap - expectedUnderlap) <= 1, `Frosted surface must underlap the active curve by ${expectedUnderlap}px: ${JSON.stringify(geometry)}`)
      assert.equal(geometry.gap, 0, `Role surfaces must have no transparent gap: ${JSON.stringify(geometry)}`)
      assert.ok(geometry.outerEdgeDeviation.left <= 1 && geometry.outerEdgeDeviation.right <= 1, `Role surfaces must cover both outer edges: ${JSON.stringify(geometry)}`)
      assert.ok(geometry.labelCenters.deviations.every(value => value <= 1), `Role labels must be centered at 25%/75%: ${JSON.stringify(geometry)}`)
      return geometry
    }

    const readAgreementState = () => page.evaluate(() => {
      const check = document.querySelector('.login-agreement__check')
      const tick = document.querySelector('.login-agreement__tick')
      const checkStyle = getComputedStyle(check)
      const tickStyle = tick ? getComputedStyle(tick) : null
      return {
        checkClass: check?.className || '',
        active: check?.classList.contains('login-agreement__check--active') || false,
        checkBackgroundColor: checkStyle.backgroundColor,
        tickPresent: Boolean(tick),
        tickText: tick?.textContent?.trim() || '',
        tickColor: tickStyle?.color || null,
        tickVisibility: tickStyle?.visibility || null,
        tickDisplay: tickStyle?.display || null
      }
    })

    const assertAgreementToggle = async role => {
      const check = page.locator('.login-agreement__check')
      const before = await readAgreementState()
      assert.equal(before.active, false, `${role}: agreement must start unchecked`)
      assert.equal(before.checkBackgroundColor, 'rgb(255, 255, 255)', `${role}: unchecked agreement background must be white`)
      assert.equal(before.tickPresent, false, `${role}: unchecked agreement must not render a tick`)

      await check.click()
      await page.locator('.login-agreement__check--active').waitFor({ state: 'visible' })
      const checked = await readAgreementState()
      const tickChannels = checked.tickColor?.match(/\d+(?:\.\d+)?/g)?.slice(0, 3).map(Number) || []
      assert.equal(checked.active, true, `${role}: agreement active class must follow the checked state`)
      assert.equal(checked.checkBackgroundColor, 'rgb(255, 255, 255)', `${role}: checked agreement background must remain white`)
      assert.equal(checked.tickPresent, true, `${role}: checked agreement must render a tick`)
      assert.equal(checked.tickText, '✓', `${role}: checked agreement must render the expected tick mark`)
      assert.equal(checked.tickVisibility, 'visible', `${role}: checked agreement tick must be visible`)
      assert.notEqual(checked.tickDisplay, 'none', `${role}: checked agreement tick must be displayed`)
      assert.equal(tickChannels.length, 3, `${role}: agreement tick color must be an RGB color: ${checked.tickColor}`)
      assert.ok(tickChannels.every(channel => channel <= 32), `${role}: agreement tick must be black or near-black: ${checked.tickColor}`)

      await check.click()
      await page.locator('.login-agreement__check--active').waitFor({ state: 'detached' })
      const afterCancel = await readAgreementState()
      assert.equal(afterCancel.active, false, `${role}: second click must clear the agreement state`)
      assert.equal(afterCancel.checkBackgroundColor, 'rgb(255, 255, 255)', `${role}: cleared agreement background must be white`)
      assert.equal(afterCancel.tickPresent, false, `${role}: cleared agreement must remove the tick`)
      return { before, checked, afterCancel, tickRgb: tickChannels }
    }

    await page.getByText('企业登录', { exact: true }).click()
    const enterpriseSurface = await readRoleSurface()
    assert.match(enterpriseSurface.panelClass, /login-content--enterprise/)
    assert.equal(enterpriseSurface.activeText, '企业登录')
    assert.equal(enterpriseSurface.activeSurfaceBackground, 'rgb(255, 255, 255)')
    assert.equal(enterpriseSurface.activeSurfaceBackdropFilter, 'none')
    assert.equal(enterpriseSurface.activeSurfaceFilter, 'none')
    assert.equal(enterpriseSurface.activeSurfaceRight, '0px')
    const enterpriseTabGeometry = assertEqualRoleHalves(enterpriseSurface)
    assert.ok(parseFloat(enterpriseSurface.activeSurfaceTopLeftRadius) >= 50, 'Enterprise active curve must mirror toward the lower left')
    assert.equal(enterpriseSurface.frostedSurfaceLeft, '0px')
    assert.match(enterpriseSurface.frostedSurfaceBackdropFilter, /blur\(/)
    const enterpriseAgreement = await assertAgreementToggle('enterprise')

    const enterpriseScreenshotPath = path.join(evidenceDir, `login-enterprise-${viewport.width}x${viewport.height}.png`)
    await page.screenshot({ path: enterpriseScreenshotPath, fullPage: true })
    const enterpriseScreenshotStat = await stat(enterpriseScreenshotPath)
    assert.ok(enterpriseScreenshotStat.size > 10000, `Enterprise screenshot appears blank or incomplete: ${enterpriseScreenshotStat.size} bytes`)

    await page.getByText('学员登录', { exact: true }).click()
    const studentSurface = await readRoleSurface()
    assert.match(studentSurface.panelClass, /login-content--student/)
    assert.equal(studentSurface.activeText, '学员登录')
    assert.equal(studentSurface.activeItemBackground, 'rgba(0, 0, 0, 0)')
    assert.equal(studentSurface.activeItemBackdropFilter, 'none')
    assert.equal(studentSurface.activeItemFilter, 'none')
    assert.equal(studentSurface.activeSurfaceBackground, 'rgb(255, 255, 255)')
    assert.equal(studentSurface.activeSurfaceBackdropFilter, 'none')
    assert.equal(studentSurface.activeSurfaceFilter, 'none')
    assert.equal(studentSurface.activeSurfaceLeft, '0px')
    const studentTabGeometry = assertEqualRoleHalves(studentSurface)
    assert.ok(parseFloat(studentSurface.activeSurfaceTopRightRadius) >= 50, 'Student active curve must expand toward the lower right')
    assert.equal(studentSurface.frostedSurfaceRight, '0px')
    assert.match(studentSurface.frostedSurfaceBackdropFilter, /blur\(/)
    const studentAgreement = await assertAgreementToggle('student')
    const studentScreenshotPath = path.join(evidenceDir, `login-${viewport.width}x${viewport.height}.png`)
    await page.screenshot({ path: studentScreenshotPath, fullPage: true })
    const studentScreenshotStat = await stat(studentScreenshotPath)
    assert.ok(studentScreenshotStat.size > 10000, `Student screenshot appears blank or incomplete: ${studentScreenshotStat.size} bytes`)

    const tabStateResult = {
      viewport,
      student: { panelClass: studentSurface.panelClass, activeText: studentSurface.activeText, geometry: studentTabGeometry, agreement: studentAgreement },
      enterprise: { panelClass: enterpriseSurface.panelClass, activeText: enterpriseSurface.activeText, geometry: enterpriseTabGeometry, agreement: enterpriseAgreement },
      studentScreenshot: { path: studentScreenshotPath, bytes: studentScreenshotStat.size },
      enterpriseScreenshot: { path: enterpriseScreenshotPath, bytes: enterpriseScreenshotStat.size },
      pass: true
    }
    tabStateResults.results.push(tabStateResult)

    const agreement = page.locator('.login-agreement')
    await agreement.click({ position: { x: 8, y: 8 } })
    await page.locator('.login-agreement__check--active').waitFor({ state: 'visible' })

    const metrics = await page.evaluate(selectors => {
      const pageEl = document.querySelector('.login-page')
      const panel = document.querySelector('.login-content')
      const input = document.querySelector('.login-field')
      const button = document.querySelector('.login-submit')
      const mascot = document.querySelector('.login-hero__mascot img')
      const wechat = document.querySelector('.wechat-login__icon img')
      const apple = document.querySelector('.ios-login__icon img')
      const ios = document.querySelector('.ios-login')
      const tabs = document.querySelector('.login-role-tabs')
      const overlay = getComputedStyle(panel, '::before')
      const whiteCap = getComputedStyle(panel, '::after')
      const hero = document.querySelector('.login-hero')
      const getCode = document.querySelector('.login-field__get-code')
      const labels = [...document.querySelectorAll('.login-field__label')]
      const panelRect = panel.getBoundingClientRect()
      const mascotRect = document.querySelector('.login-hero__mascot-wrap').getBoundingClientRect()
      const textClipping = [...document.querySelectorAll('.login-page uni-text, .login-page span')]
        .filter(el => el.textContent?.trim())
        .filter(el => !el.classList.contains('login-agreement__tick'))
        .filter(el => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)
        .map(el => el.textContent?.trim())
      return {
        backgroundColor: getComputedStyle(pageEl).backgroundColor,
        panelBackgroundColor: getComputedStyle(panel).backgroundColor,
        panelBackgroundImage: getComputedStyle(panel).backgroundImage,
        panelBorderRadius: getComputedStyle(panel).borderRadius,
        panelBottomLeftRadius: getComputedStyle(panel).borderBottomLeftRadius,
        panelBottomRightRadius: getComputedStyle(panel).borderBottomRightRadius,
        panelBottomGap: window.innerHeight - panelRect.bottom,
        inputBorderRadius: getComputedStyle(input).borderRadius,
        heroBackgroundImage: getComputedStyle(document.querySelector('.login-hero')).backgroundImage,
        tabsBackgroundColor: getComputedStyle(tabs).backgroundColor,
        overlayBackgroundColor: overlay.backgroundColor,
        overlayBackgroundImage: overlay.backgroundImage,
        overlayBackdropFilter: overlay.backdropFilter || overlay.webkitBackdropFilter,
        overlayBottomLeftRadius: overlay.borderBottomLeftRadius,
        overlayBottomRightRadius: overlay.borderBottomRightRadius,
        whiteCapTopRightRadius: whiteCap.borderTopRightRadius,
        whiteCapBottomRightRadius: whiteCap.borderBottomRightRadius,
        mascotPanelOverlap: mascotRect.bottom - panelRect.top,
        panelAboveHero: Number.parseInt(getComputedStyle(panel).zIndex, 10) > Number.parseInt(getComputedStyle(hero).zIndex, 10),
        buttonBackgroundImage: getComputedStyle(button).backgroundImage,
        buttonBoxShadow: getComputedStyle(button).boxShadow,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        documentScrollWidth: document.documentElement.scrollWidth,
        bodyScrollWidth: document.body.scrollWidth,
        pageScrollWidth: pageEl.scrollWidth,
        pageClientWidth: pageEl.clientWidth,
        mascotLoaded: mascot instanceof HTMLImageElement && mascot.complete && mascot.naturalWidth > 0,
        wechatIconLoaded: wechat instanceof HTMLImageElement && wechat.complete && wechat.naturalWidth > 0,
        appleIconLoaded: apple instanceof HTMLImageElement && apple.complete && apple.naturalWidth > 0,
        fieldIconCount: document.querySelectorAll('.login-field__icon').length,
        iosTagName: ios?.tagName,
        iosHasClickAttribute: [...(ios?.attributes || [])].some(attribute => /tap|click/i.test(attribute.name)),
        iosTextContent: ios?.textContent?.trim() || '',
        getCodeTagName: getCode?.tagName,
        getCodeHasClickAttribute: [...(getCode?.attributes || [])].some(attribute => /tap|click/i.test(attribute.name)),
        getCodeTextContent: getCode?.textContent?.trim() || '',
        labelStyles: labels.map(label => {
          const style = getComputedStyle(label)
          return { color: style.color, fontSize: style.fontSize, fontWeight: style.fontWeight }
        }),
        textClipping,
        geometry: Object.fromEntries([
          ['brand', '.login-hero__brand'],
          ['subtitle', '.login-hero__title'],
          ['panel', '.login-content'],
          ['mascot', '.login-hero__mascot-wrap'],
          ['phone', '.login-field--phone'],
          ['code', '.login-field--code'],
          ['submit', '.login-submit'],
          ['agreement', '.login-agreement'],
          ['thirdPartyTitle', '.login-third-party__title'],
          ['wechat', '.wechat-login'],
          ['ios', '.ios-login']
        ].map(([name, selector]) => {
          const rect = document.querySelector(selector).getBoundingClientRect()
          return [name, { x: rect.x, y: rect.y + window.scrollY, width: rect.width, height: rect.height }]
        })),
        boxes: selectors.map(selector => {
          const el = document.querySelector(selector)
          const rect = el.getBoundingClientRect()
          return { selector, x: rect.x, y: rect.y + window.scrollY, width: rect.width, height: rect.height }
        })
      }
    }, keySelectors)

    assert.equal(metrics.backgroundColor, 'rgb(245, 240, 234)')
    assert.equal(metrics.viewportWidth, viewport.width, 'Browser width does not match target viewport')
    assert.equal(metrics.viewportHeight, viewport.height, 'Browser height does not match target viewport')
    assert.equal(metrics.panelBackgroundColor, 'rgba(0, 0, 0, 0)')
    assert.match(metrics.panelBackgroundImage, /rgb\(255, 255, 255\)/)
    assert.notEqual(metrics.buttonBoxShadow, 'none')
    assert.match(metrics.buttonBackgroundImage, /rgb\((230, 111, 45|243, 163, 95)\)/)
    assert.ok(!/128,\s*0,\s*128|purple|violet/i.test(metrics.buttonBackgroundImage))
    assert.match(metrics.heroBackgroundImage, /linear-gradient/)
    assert.match(metrics.overlayBackgroundImage, /linear-gradient/)
    assert.match(metrics.overlayBackgroundColor, /rgba\([^)]*,\s*0\.[1-9]/)
    assert.match(metrics.overlayBackdropFilter, /blur\(/)
    assert.equal(parseFloat(metrics.overlayBottomLeftRadius), 0, 'Frosted overlay bottom edge must stay straight')
    assert.equal(parseFloat(metrics.overlayBottomRightRadius), 0, 'Frosted overlay bottom edge must stay straight')
    assert.ok(parseFloat(metrics.whiteCapTopRightRadius) >= 50, 'White cap must expand toward the lower right')
    assert.equal(parseFloat(metrics.whiteCapBottomRightRadius), 0, 'White cap curve direction must not narrow toward the lower left')
    assert.ok(inRange(metrics.mascotPanelOverlap, 12, 28), `Mascot/overlay overlap mismatch: ${metrics.mascotPanelOverlap}`)
    assert.equal(metrics.panelAboveHero, true, 'Frosted panel must render in front of the mascot lower edge')
    assert.ok(inRange(parseFloat(metrics.panelBottomLeftRadius), 28, 40), 'Panel bottom-left radius must remain visible')
    assert.ok(inRange(parseFloat(metrics.panelBottomRightRadius), 28, 40), 'Panel bottom-right radius must remain visible')
    assert.ok(inRange(metrics.panelBottomGap, 12, 20), `Warm bottom gap mismatch: ${metrics.panelBottomGap}`)
    assert.equal(metrics.tabsBackgroundColor, 'rgba(0, 0, 0, 0)')
    assert.ok(parseFloat(metrics.inputBorderRadius) >= 24)
    assert.ok(metrics.mascotLoaded, 'Mascot image did not load')
    assert.ok(metrics.wechatIconLoaded, 'Wechat image did not load')
    assert.ok(metrics.appleIconLoaded, 'Apple image did not load')
    assert.equal(metrics.fieldIconCount, 0, 'Field prefix icons must not exist')
    assert.equal(metrics.iosTagName, 'UNI-VIEW', 'iOS visual must not be a button')
    assert.equal(metrics.iosHasClickAttribute, false, 'iOS visual must not expose click/tap attributes')
    assert.equal(metrics.iosTextContent, '', 'iOS visual must use the Apple mark without text')
    assert.equal(metrics.getCodeTagName, 'UNI-VIEW', 'Get-code text must be a display-only view')
    assert.equal(metrics.getCodeHasClickAttribute, false, 'Get-code text must not expose click/tap attributes')
    assert.equal(metrics.getCodeTextContent, '获取验证码')
    assert.equal(metrics.labelStyles.length, 2)
    for (const labelStyle of metrics.labelStyles) {
      assert.ok(inRange(parseFloat(labelStyle.fontSize), 15, 17), `Label font-size mismatch: ${JSON.stringify(labelStyle)}`)
    }
    assert.equal(metrics.labelStyles[0].color, metrics.labelStyles[1].color, 'Field label colors must match')
    assert.equal(metrics.labelStyles[0].fontWeight, metrics.labelStyles[1].fontWeight, 'Field label weights must match')
    assert.ok(metrics.documentScrollWidth <= metrics.viewportWidth + 1, 'Document has horizontal overflow')
    assert.ok(metrics.bodyScrollWidth <= metrics.viewportWidth + 1, 'Body has horizontal overflow')
    assert.ok(metrics.pageScrollWidth <= metrics.pageClientWidth + 1, 'Login page has horizontal overflow')
    assert.deepEqual(metrics.textClipping, [], `Clipped text: ${metrics.textClipping.join(', ')}`)

    if (viewport.width === 390) {
      const { brand, subtitle, panel, mascot, phone, code, submit, agreement, thirdPartyTitle, wechat, ios } = metrics.geometry
      assert.ok(inRange(brand.y, 104, 116), `Brand y mismatch: ${JSON.stringify(brand)}`)
      assert.ok(inRange(subtitle.y, 150, 166), `Subtitle y mismatch: ${JSON.stringify(subtitle)}`)
      assert.ok(inRange(panel.x, 10, 14) && inRange(panel.y, 196, 204), `Panel geometry mismatch: ${JSON.stringify(panel)}`)
      assert.ok(inRange(mascot.x, 244, 252) && inRange(mascot.y, 80, 86), `Mascot position mismatch: ${JSON.stringify(mascot)}`)
      assert.ok(inRange(mascot.width, 108, 116) && inRange(mascot.height, 132, 140), `Mascot size mismatch: ${JSON.stringify(mascot)}`)
      for (const field of [phone, code]) {
        assert.ok(inRange(field.x, 35, 43), `Field x mismatch: ${JSON.stringify(field)}`)
        assert.ok(inRange(field.width, 308, 316), `Field width mismatch: ${JSON.stringify(field)}`)
        assert.ok(inRange(field.height, 47, 53), `Field height mismatch: ${JSON.stringify(field)}`)
      }
      assert.ok(inRange(phone.y, 299, 307), `Phone y mismatch: ${JSON.stringify(phone)}`)
      assert.ok(inRange(code.y, 407, 415), `Code y mismatch: ${JSON.stringify(code)}`)
      assert.ok(inRange(submit.y, 496, 504) && inRange(submit.height, 50, 54), `Submit geometry mismatch: ${JSON.stringify(submit)}`)
      assert.ok(inRange(agreement.y, 574, 590), `Agreement y mismatch: ${JSON.stringify(agreement)}`)
      assert.ok(inRange(thirdPartyTitle.y, 710, 728), `Third-party title y mismatch: ${JSON.stringify(thirdPartyTitle)}`)
      for (const icon of [wechat, ios]) {
        assert.ok(inRange(icon.y, 740, 784), `Third-party icon y mismatch: ${JSON.stringify(icon)}`)
      }
    }

    const overlaps = []
    for (let i = 0; i < metrics.boxes.length; i += 1) {
      for (let j = i + 1; j < metrics.boxes.length; j += 1) {
        if (intersectionArea(metrics.boxes[i], metrics.boxes[j]) > 1) {
          overlaps.push([metrics.boxes[i].selector, metrics.boxes[j].selector])
        }
      }
    }
    assert.deepEqual(overlaps, [], `Unexpected overlaps: ${JSON.stringify(overlaps)}`)
    assert.deepEqual(pageErrors, [], `Browser page errors: ${pageErrors.join('; ')}`)

    let agreementLinksOpened = null
    if (viewport.width === 390) {
      await page.locator('.login-agreement__link').nth(0).click()
      await page.waitForURL(/agreement\?type=user/, { timeout: 10000 })
      await page.goto(url, { waitUntil: 'networkidle' })
      await page.locator('.login-agreement__link').nth(1).click()
      await page.waitForURL(/agreement\?type=privacy/, { timeout: 10000 })
      agreementLinksOpened = true
    }

    results.viewports.push({
      ...viewport,
      screenshots: tabStateResult.studentScreenshot && {
        student: tabStateResult.studentScreenshot,
        enterprise: tabStateResult.enterpriseScreenshot
      },
      tabStates: {
        student: tabStateResult.student,
        enterprise: tabStateResult.enterprise
      },
      metrics,
      overlaps,
      pageErrors,
      agreementLinksOpened
    })
    await context.close()
  }

  results.status = 'PASSED'
  tabStateResults.commonAssertions = {
    activeSurfaceBackground: 'rgb(255, 255, 255)',
    activeSurfaceFilter: 'none',
    activeSurfaceBackdropFilter: 'none',
    inactiveSurfaceBackdropFilterIncludesBlur: true,
    activeVisibleRatio: 0.5,
    inactiveVisibleRatio: 0.5,
    frostedUnderlapPx: 58,
    maxGapPx: 0,
    maxOuterEdgeDeviationPx: 1,
    expectedLabelCenterRatios: [0.25, 0.75]
  }
  tabStateResults.logicAssertions = {
    scriptSetupUnchanged: results.sourceChecks.scriptSetupUnchanged,
    studentLoginFlowPresent: results.sourceChecks.studentLogin,
    enterpriseLoginFlowPresent: results.sourceChecks.enterpriseLogin,
    roleBranchUnchanged: results.sourceChecks.roleBranch,
    internalPasswordInputUnchanged: results.sourceChecks.internalPasswordInputUnchanged,
    noSmsFlowAdded: results.sourceChecks.noSmsFlow
  }
  tabStateResults.status = 'PASSED'
} catch (error) {
  results.error = error instanceof Error ? `${error.name}: ${error.message}` : String(error)
  tabStateResults.error = results.error
  process.exitCode = 1
} finally {
  if (browser) await browser.close()
  await writeFile(path.join(evidenceDir, 'playwright-results.json'), `${JSON.stringify(results, null, 2)}\n`, 'utf8')
  await writeFile(path.join(evidenceDir, 'tab-state-results.json'), `${JSON.stringify(tabStateResults, null, 2)}\n`, 'utf8')
}

console.log(JSON.stringify(results, null, 2))
