import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))

function findRepoRoot(start) {
  let current = path.resolve(start)
  while (path.dirname(current) !== current) {
    if (fs.existsSync(path.join(current, '.git'))) return current
    current = path.dirname(current)
  }
  throw new Error('repository root not found')
}

const repoRoot = findRepoRoot(scriptDir)
const frontRoot = path.join(repoRoot, 'code', 'develop', 'yunjikeji')
const home = fs.readFileSync(path.join(frontRoot, 'src', 'pages', 'home.vue'), 'utf8')
const assessment = fs.readFileSync(path.join(frontRoot, 'src', 'services', 'assessment.ts'), 'utf8')
const career = fs.readFileSync(path.join(frontRoot, 'src', 'services', 'careerAssessment.ts'), 'utf8')
const savingMessage = '上次评测正在初始化分析，请稍后'

function extractFunction(source, name) {
  const candidates = [`async function ${name}`, `function ${name}`]
  const start = candidates.map((candidate) => source.indexOf(candidate)).find((index) => index >= 0)
  assert.ok(start >= 0, `function missing: ${name}`)
  const bodyStart = source.indexOf('{', start)
  assert.ok(bodyStart >= 0, `function body missing: ${name}`)
  let depth = 0
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1
    if (source[index] === '}') {
      depth -= 1
      if (depth === 0) return source.slice(bodyStart, index + 1)
    }
  }
  throw new Error(`unterminated function: ${name}`)
}

function requireSavingShortCircuit(functionName, latestCall, completedCall) {
  const body = extractFunction(home, functionName)
  const latestIndex = body.indexOf(latestCall)
  const completedIndex = body.indexOf(completedCall)
  assert.ok(latestIndex >= 0, `${functionName} must query its category latest save status first`)
  assert.ok(completedIndex > latestIndex, `${functionName} must run completed/restart logic only after latest save status`)
  const statusMatch = body.match(/batchSaveStatus[^\n]{0,100}===\s*1/)
  assert.ok(statusMatch, `${functionName} must short-circuit only batchSaveStatus 1`)
  const statusIndex = body.indexOf(statusMatch[0])
  const returnIndex = body.indexOf('return', statusIndex)
  assert.ok(returnIndex > statusIndex, `${functionName} status 1 branch must return`)
  const savingBranch = body.slice(statusIndex, returnIndex + 'return'.length)
  assert.ok(savingBranch.includes('openAssessmentSavingDialog')
      || savingBranch.includes('assessmentSavingDialogVisible.value = true'),
  `${functionName} status 1 branch must open the shared independent saving notice`)
  for (const forbidden of ['confirmAssessmentRestart', 'resetCompletedAssessment', 'openPage(', 'navigateTo(', 'startAppPractice']) {
    assert.ok(!savingBranch.includes(forbidden), `${functionName} status 1 branch must not call ${forbidden}`)
  }
  assert.ok(!/batchSaveStatus[^\n]{0,100}(?:===\s*[02]|!==|!=|>\s*0)/.test(body),
    `${functionName} must let status 0/2 follow the original completed/restart flow`)
}

function testServiceContracts() {
  assert.match(assessment, /type\s+AssessmentResultStatus\s*=\s*\{[\s\S]*?batchSaveStatus\??:\s*number/,
    'self latest-status type must expose batchSaveStatus')
  assert.match(assessment, /fetchLatestAssessmentResultStatus[\s\S]*?assessment-result\/latest-status/,
    'self latest-status request must retain its original endpoint')
  assert.match(career, /type\s+CareerAssessmentResultStatus\s*=\s*\{[\s\S]*?batchSaveStatus\??:\s*number/,
    'career latest-status type must expose batchSaveStatus')
  assert.match(career, /fetchLatestCareerAssessmentStatus[\s\S]*?assessment-result\/career\/latest-status/,
    'career save gate must use a latest-status endpoint separate from report-entry')
}

function testSavingDialogIsolation() {
  assert.ok(home.includes(savingMessage), 'saving notice must use the exact approved message')
  assert.match(home, /const\s+assessmentSavingDialogVisible\s*=\s*ref\(false\)/,
    'saving notice must own independent visibility state')
  assert.ok(home.includes('const restartDialogVisible = ref(false)'), 'restart dialog state must remain intact')
  const dialogs = home.match(/<SelfTestRestartDialog\b[\s\S]*?\/>/g) || []
  assert.ok(dialogs.length >= 2, 'saving notice must reuse the restart dialog component style as a separate instance')
  const savingDialog = dialogs.find((dialog) => dialog.includes('assessmentSavingDialogVisible'))
  assert.ok(savingDialog, 'independent saving dialog instance is missing')
  assert.ok(!savingDialog.includes('resolveAssessmentRestart'), 'saving dialog must not reuse restart resolver handlers')
  assert.match(savingDialog, /:close-on-mask="true"/,
    'saving notice must enable mask-close only for the independent saving dialog instance')
  assert.match(savingDialog, /@confirm="closeAssessmentSavingDialog"/,
    'saving notice confirm must only close the saving dialog')
  assert.match(savingDialog, /@cancel="closeAssessmentSavingDialog"/,
    'saving notice cancel/mask close must only close the saving dialog')

  const restartDialog = dialogs.find((dialog) => dialog.includes('restartDialogVisible'))
  assert.ok(restartDialog, 'restart dialog instance is missing')
  assert.ok(!restartDialog.includes(':close-on-mask="true"'),
    'DEV-078 must not require the original restart dialog to enable mask-close')

  const dialogComponent = fs.readFileSync(path.join(frontRoot, 'src', 'components', 'practice', 'SelfTestRestartDialog.vue'), 'utf8')
  assert.match(dialogComponent, /class="self-test-restart-dialog__mask"[^>]*@tap="handleMaskTap"/,
    'shared dialog component must route mask taps through an explicit handler')
  const maskHandler = extractFunction(dialogComponent, 'handleMaskTap')
  assert.match(maskHandler, /props\.closeOnMask/, 'mask handler must gate close behavior behind closeOnMask')
  assert.match(maskHandler, /cancel\(\)/, 'mask handler must only reuse cancel close behavior when enabled')

  const closeBody = extractFunction(home, 'closeAssessmentSavingDialog')
  assert.match(closeBody, /assessmentSavingDialogVisible\.value\s*=\s*false/)
  for (const forbidden of ['restartDialogResolver', 'resolveAssessmentRestart', 'reset', 'start', 'openPage', 'navigateTo']) {
    assert.ok(!closeBody.includes(forbidden), `saving notice close handler must not call ${forbidden}`)
  }
}

function testHomeGates() {
  requireSavingShortCircuit('startSelfTest', 'fetchLatestAssessmentResultStatus', 'hasCompletedAssessment')
  requireSavingShortCircuit('startCareerAssessment', 'fetchLatestCareerAssessmentStatus', 'hasCompletedCareerAssessment')

  const self = extractFunction(home, 'startSelfTest')
  assert.ok(self.includes('confirmAssessmentRestart'), 'status 0/2 must retain self restart confirmation')
  assert.ok(self.includes('resetCompletedAssessment'), 'status 0/2 must retain self reset flow')
  assert.ok(self.includes("openPage('/pages/practice/self-test-answer')"), 'status 0/2 must retain self navigation')

  const careerBody = extractFunction(home, 'startCareerAssessment')
  assert.ok(careerBody.includes('confirmAssessmentRestart'), 'status 0/2 must retain career restart confirmation')
  assert.ok(careerBody.includes("openPage('/pages/practice/career-assessment-answer')"),
    'status 0/2 must retain career navigation')
}

const cases = [
  ['service latest-status contracts', testServiceContracts],
  ['saving dialog state and resolver isolation', testSavingDialogIsolation],
  ['self/career status 1 short-circuit and status 0/2 regression protection', testHomeGates]
]

const failures = []
for (const [name, run] of cases) {
  try {
    run()
    console.log(`PASS ${name}`)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    failures.push({ name, message })
    console.error(`FAIL ${name}: ${message}`)
  }
}

console.log(`SUMMARY passed=${cases.length - failures.length} failed=${failures.length}`)
if (failures.length) process.exitCode = 1
