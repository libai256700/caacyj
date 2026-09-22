const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd()] }))

const baseUrl = process.env.DEV085_BASE_URL || 'http://127.0.0.1:3000/yj/assessment/question'
const outputDir = __dirname
const resultPath = path.join(outputDir, 'playwright-results.json')
const screenshotPath = path.join(outputDir, 'assessment-required.png')

const rows = [
  {
    id: 85001,
    title: 'DEV-085 optional question',
    question_type: '1',
    question_content: 'Optional question content',
    step_name: 'Basic profile',
    is_required: false,
    status: true,
    sort_no: 1,
    update_time: '2026-09-02 18:00:00'
  },
  {
    id: 85002,
    title: 'DEV-085 required question',
    question_type: '2',
    question_content: 'Required question content',
    step_name: 'Basic profile',
    is_required: true,
    status: true,
    sort_no: 2,
    update_time: '2026-09-02 18:00:00'
  }
]

const menu = [
  {
    id: 850,
    parentId: 0,
    name: 'Self assessment',
    path: '/yj/assessment',
    component: '',
    visible: true,
    keepAlive: true,
    alwaysShow: true,
    children: [
      {
        id: 851,
        parentId: 850,
        name: 'Question bank',
        path: 'question',
        component: 'yj/resource/index?resource=assessment-question',
        componentName: 'YjAssessmentQuestion',
        visible: true,
        keepAlive: false,
        alwaysShow: false
      }
    ]
  }
]

const requests = []
const pageErrors = []

const response = (route, data) => route.fulfill({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({ code: 0, data, msg: '' })
})

const selectedText = async (select) => (await select.innerText()).trim()

const chooseOption = async (page, select, label) => {
  await select.click()
  const options = page.locator('.el-select-dropdown__item:visible')
  await options.first().waitFor({ state: 'visible' })
  const labels = (await options.allInnerTexts()).map((item) => item.trim()).filter(Boolean)
  assert.deepEqual(labels, ['Yes', 'No'].map((item) => item === 'Yes' ? '\u662f' : '\u5426'))
  await options.filter({ hasText: label }).click()
}

const openEdit = async (page) => {
  const row = page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: 'DEV-085 optional question' })
  await row.getByRole('button', { name: '\u7f16\u8f91', exact: true }).click()
  const dialog = page.locator('.el-dialog:visible')
  await dialog.waitFor({ state: 'visible' })
  return dialog
}

const run = async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.DEV085_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  })
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
  await context.addInitScript(() => {
    const now = Date.now()
    localStorage.setItem('ACCESS_TOKEN', JSON.stringify({ c: now, e: now + 3600000, v: JSON.stringify('dev085-mocked-token') }))
  })
  const page = await context.newPage()
  page.on('pageerror', (error) => pageErrors.push(error.message))

  await page.route('**/admin-api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname

    if (pathname.endsWith('/system/auth/get-permission-info')) {
      return response(route, {
        user: { id: 850, nickname: 'DEV-085', avatar: '', deptId: 1 },
        roles: ['super_admin'],
        permissions: ['*:*:*'],
        menus: menu
      })
    }
    if (pathname.endsWith('/system/dict-data/simple-list')) {
      return response(route, [
        { dictType: 'yj_practice_question_type', value: '1', label: '\u5355\u9009\u9898', colorType: 'primary' },
        { dictType: 'yj_practice_question_type', value: '2', label: '\u591a\u9009\u9898', colorType: 'success' }
      ])
    }
    if (pathname.endsWith('/yj/assessment-question/page')) {
      requests.push({ method: request.method(), path: pathname, query: Object.fromEntries(url.searchParams) })
      return response(route, { list: rows, total: rows.length })
    }
    if (pathname.endsWith('/yj/assessment-question/get')) {
      const id = Number(url.searchParams.get('id'))
      const row = rows.find((item) => item.id === id)
      requests.push({ method: request.method(), path: pathname, id, responseIsRequired: row?.is_required })
      return response(route, row)
    }
    if (pathname.endsWith('/yj/assessment-question/update')) {
      const body = request.postDataJSON()
      requests.push({ method: request.method(), path: pathname, body })
      const row = rows.find((item) => item.id === Number(body.id))
      Object.assign(row, body)
      return response(route, true)
    }
    return response(route, [])
  })

  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' })
    await page.getByText('\u81ea\u6d4b\u9898\u5e93\u7ba1\u7406', { exact: true }).waitFor({ state: 'visible' })
    await page.locator('.el-table__body-wrapper tbody tr').first().waitFor({ state: 'visible' })

    const headers = (await page.locator('.el-table__header-wrapper th').allInnerTexts()).map((item) => item.trim())
    assert(headers.includes('\u662f\u5426\u5fc5\u586b'), 'required column is missing')

    const tableRows = page.locator('.el-table__body-wrapper tbody tr')
    const optionalRow = tableRows.filter({ hasText: 'DEV-085 optional question' })
    const requiredRow = tableRows.filter({ hasText: 'DEV-085 required question' })
    assert.match(await optionalRow.innerText(), /\u5426/)
    assert.match(await requiredRow.innerText(), /\u662f/)
    for (const label of ['\u8be6\u60c5', '\u7f16\u8f91', '\u81ea\u6d4b\u7b54\u6848', '\u5220\u9664']) {
      assert.equal(await optionalRow.getByRole('button', { name: label, exact: true }).count(), 1, `${label} action missing`)
    }
    assert.equal(await optionalRow.locator('.el-switch').count(), 1, 'status switch missing')
    assert.match(await optionalRow.innerText(), /\u5355\u9009\u9898/)

    let dialog = await openEdit(page)
    let requiredItem = dialog.locator('.el-form-item').filter({ hasText: '\u662f\u5426\u5fc5\u586b' })
    let requiredSelect = requiredItem.locator('.el-select')
    assert.match(await selectedText(requiredSelect), /\u5426/, 'edit did not reflect false')
    await chooseOption(page, requiredSelect, '\u662f')
    await Promise.all([
      page.waitForResponse((item) => item.url().includes('/yj/assessment-question/update')),
      dialog.getByRole('button', { name: '\u4fdd\u5b58', exact: true }).click()
    ])
    await dialog.waitFor({ state: 'hidden' })
    assert.match(await optionalRow.innerText(), /\u662f/, 'list did not refresh to true')

    dialog = await openEdit(page)
    requiredItem = dialog.locator('.el-form-item').filter({ hasText: '\u662f\u5426\u5fc5\u586b' })
    requiredSelect = requiredItem.locator('.el-select')
    assert.match(await selectedText(requiredSelect), /\u662f/, 'reopen did not retain true')
    await chooseOption(page, requiredSelect, '\u5426')
    await Promise.all([
      page.waitForResponse((item) => item.url().includes('/yj/assessment-question/update')),
      dialog.getByRole('button', { name: '\u4fdd\u5b58', exact: true }).click()
    ])
    await dialog.waitFor({ state: 'hidden' })
    assert.match(await optionalRow.innerText(), /\u5426/, 'list did not refresh to false')

    await page.getByRole('button', { name: '\u65b0\u589e', exact: true }).click()
    dialog = page.locator('.el-dialog:visible')
    await dialog.waitFor({ state: 'visible' })
    requiredItem = dialog.locator('.el-form-item').filter({ hasText: '\u662f\u5426\u5fc5\u586b' })
    requiredSelect = requiredItem.locator('.el-select')
    assert.match(await selectedText(requiredSelect), /\u662f/, 'create default is not true')
    await chooseOption(page, requiredSelect, '\u5426')
    await dialog.getByRole('button', { name: '\u53d6\u6d88', exact: true }).click()

    const updateBodies = requests.filter((item) => item.path.endsWith('/update')).map((item) => item.body)
    assert.equal(updateBodies.length, 2)
    assert.equal(updateBodies[0].is_required, true)
    assert.equal(updateBodies[1].is_required, false)
    assert.equal(Object.hasOwn(updateBodies[1], 'is_required'), true, 'false field was dropped')

    await page.screenshot({ path: screenshotPath, fullPage: true })
    const result = {
      status: 'passed-with-controlled-api-stub',
      baseUrl,
      assertions: {
        requiredColumn: true,
        rowLabelsYesNo: true,
        editReflectsFalse: true,
        optionsYesNo: true,
        saveRefreshReopenTrue: true,
        falsePayloadPreserved: true,
        createDefaultsTrue: true,
        existingActionsRendered: true
      },
      requests,
      pageErrors,
      limitation: 'Controlled API stubs validate the real frontend only; no real backend or database write occurred.'
    }
    fs.writeFileSync(resultPath, `${JSON.stringify(result, null, 2)}\n`, 'utf8')
    assert.deepEqual(pageErrors, [])
  } finally {
    await context.close()
    await browser.close()
  }
}

run().catch((error) => {
  fs.writeFileSync(resultPath, `${JSON.stringify({ status: 'failed', error: error.stack || String(error), requests, pageErrors }, null, 2)}\n`, 'utf8')
  console.error(error)
  process.exitCode = 1
})
