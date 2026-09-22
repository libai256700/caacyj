#!/usr/bin/env node

import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))

function findRepoRoot(start) {
  let current = path.resolve(start)
  while (current !== path.dirname(current)) {
    if (fs.existsSync(path.join(current, 'code', 'develop', 'yunjikeji', 'package.json'))) return current
    current = path.dirname(current)
  }
  throw new Error('repository root not found')
}

const repoRoot = findRepoRoot(scriptDir)
const frontRoot = path.join(repoRoot, 'code', 'develop', 'yunjikeji')
const requireFromFront = createRequire(path.join(frontRoot, 'package.json'))
const { parse: parseSfc } = requireFromFront('@vue/compiler-sfc')
const { NodeTypes, parse: parseTemplate } = requireFromFront('@vue/compiler-dom')
const ts = requireFromFront('typescript')
const printer = ts.createPrinter({ newLine: ts.NewLineKind.LineFeed, removeComments: true })

const paths = {
  home: path.join(frontRoot, 'src', 'pages', 'home.vue'),
  answer: path.join(frontRoot, 'src', 'pages', 'practice', 'self-test-answer.vue'),
  assessment: path.join(frontRoot, 'src', 'services', 'assessment.ts'),
  practice: path.join(frontRoot, 'src', 'services', 'practice.ts'),
  pythonChecker: path.join(scriptDir, 'dev070_tool_contract.py')
}

function read(file) {
  return fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '')
}

function sfcParts(file) {
  const parsed = parseSfc(read(file), { filename: file })
  assert.equal(parsed.errors.length, 0, `${path.basename(file)} must parse as Vue SFC`)
  assert.ok(parsed.descriptor.scriptSetup, `${path.basename(file)} must retain script setup`)
  return {
    script: parsed.descriptor.scriptSetup.content,
    template: parsed.descriptor.template?.content || ''
  }
}

function sourceFile(source, filename = 'contract.ts') {
  return ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
}

function functionMap(source, filename) {
  const sf = sourceFile(source, filename)
  const map = new Map()
  for (const statement of sf.statements) {
    if (ts.isFunctionDeclaration(statement) && statement.name) {
      map.set(statement.name.text, {
        name: statement.name.text,
        node: statement,
        body: statement.body,
        declaration: statement,
        params: statement.parameters.length,
        text: statement.getText(sf)
      })
    }
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        if (ts.isIdentifier(declaration.name) && declaration.initializer
          && (ts.isArrowFunction(declaration.initializer) || ts.isFunctionExpression(declaration.initializer))) {
          map.set(declaration.name.text, {
            name: declaration.name.text,
            node: declaration.initializer,
            body: declaration.initializer.body,
            declaration,
            params: declaration.initializer.parameters.length,
            text: statement.getText(sf)
          })
        }
      }
    }
  }
  return { sf, map }
}

function print(node, sf) {
  return printer.printNode(ts.EmitHint.Unspecified, node, sf).replace(/\s+/g, ' ').trim()
}

function semanticAst(node) {
  const result = []
  const visit = (current) => {
    result.push(ts.SyntaxKind[current.kind])
    if (ts.isIdentifier(current)) result.push(`id:${current.text}`)
    else if (ts.isStringLiteralLike(current)) result.push(`str:${current.text}`)
    else if ([ts.SyntaxKind.TemplateHead, ts.SyntaxKind.TemplateMiddle, ts.SyntaxKind.TemplateTail]
      .includes(current.kind)) result.push(`template:${current.text}`)
    else if (ts.isNumericLiteral(current)) result.push(`num:${current.text}`)
    else if (current.kind === ts.SyntaxKind.TrueKeyword) result.push('bool:true')
    else if (current.kind === ts.SyntaxKind.FalseKeyword) result.push('bool:false')
    ts.forEachChild(current, visit)
  }
  visit(node)
  return result
}

function assertAstNormalization(functionInfo, behaviorLiteral) {
  const original = semanticAst(functionInfo.node)
  const commentVariant = functionInfo.text.replace('{', '{\n/* formatting-only DEV-070 proof */\n')
  const parsedVariant = functionMap(commentVariant, 'format-variant.ts').map.get(functionInfo.name)
  assert.deepEqual(semanticAst(parsedVariant.node), original,
    `${functionInfo.name} semantic AST must ignore comments and whitespace`)
  const changedText = functionInfo.text.replace(behaviorLiteral, `${behaviorLiteral}-changed`)
  assert.notEqual(changedText, functionInfo.text, `${functionInfo.name} behavior probe literal missing`)
  const changed = functionMap(changedText, 'behavior-variant.ts').map.get(functionInfo.name)
  assert.notDeepEqual(semanticAst(changed.node), original,
    `${functionInfo.name} semantic AST must detect a behavior literal change`)
}

function walk(node, predicate) {
  const matches = []
  const visit = (current) => {
    if (predicate(current)) matches.push(current)
    ts.forEachChild(current, visit)
  }
  if (node) visit(node)
  return matches
}

function calls(node) {
  return walk(node, ts.isCallExpression)
}

function callName(call, sf) {
  return print(call.expression, sf)
}

function callsNamed(node, sf, name) {
  return calls(node).filter((call) => {
    const actual = callName(call, sf)
    return actual === name || actual.endsWith(`.${name}`)
  })
}

function requireCall(info, sf, name, count = 1) {
  const found = callsNamed(info.node, sf, name)
  assert.equal(found.length, count, `${info.name} must call ${name} exactly ${count} time(s)`)
  return found[0]
}

function requireCallOrder(node, sf, names) {
  const ordered = calls(node).map((call) => callName(call, sf))
  let cursor = -1
  for (const name of names) {
    const next = ordered.findIndex((actual, index) => index > cursor && (actual === name || actual.endsWith(`.${name}`)))
    assert.ok(next >= 0, `missing ordered call after ${cursor}: ${name}; actual=${ordered.join(' -> ')}`)
    cursor = next
  }
}

function findIf(node, predicate) {
  return walk(node, ts.isIfStatement).find((statement) => predicate(statement.expression))
}

function property(node, owner, name) {
  return ts.isPropertyAccessExpression(node)
    && ts.isIdentifier(node.expression) && node.expression.text === owner && node.name.text === name
}

function assignment(node, owner, name, valueKind) {
  return walk(node, ts.isBinaryExpression).find((binary) =>
    binary.operatorToken.kind === ts.SyntaxKind.EqualsToken
    && property(binary.left, owner, name)
    && binary.right.kind === valueKind)
}

function isReturnOnly(statement) {
  if (ts.isReturnStatement(statement)) return true
  return ts.isBlock(statement) && statement.statements.length === 1 && ts.isReturnStatement(statement.statements[0])
}

function testHomeProtectedSemantics() {
  const home = sfcParts(paths.home)
  const functions = functionMap(home.script, paths.home)
  const start = functions.map.get('startSelfTest')
  const report = functions.map.get('openLatestSelfTestReport')
  assert.ok(start && report, 'protected home functions must exist')
  assert.equal(start.params, 0, 'startSelfTest signature must stay parameterless')
  assert.equal(report.params, 0, 'openLatestSelfTestReport signature must stay parameterless')

  assertAstNormalization(start, '/pages/practice/self-test-answer')
  assertAstNormalization(report, 'self-test-report')

  const startStatements = start.body.statements
  assert.ok(ts.isIfStatement(startStatements[0]) && property(startStatements[0].expression, 'startingSelfTest', 'value')
    && isReturnOnly(startStatements[0].thenStatement), 'startSelfTest must retain the in-flight guard')
  assert.ok(assignment(startStatements[1], 'startingSelfTest', 'value', ts.SyntaxKind.TrueKeyword),
    'startSelfTest must set loading before work')
  const startTry = startStatements.find(ts.isTryStatement)
  assert.ok(startTry, 'startSelfTest must retain try/catch/finally')
  const completedBranch = findIf(startTry.tryBlock, (expression) =>
    callsNamed(expression, functions.sf, 'hasCompletedAssessment').length === 1)
  assert.ok(completedBranch, 'startSelfTest must branch on awaited completed status')
  requireCallOrder(completedBranch.thenStatement, functions.sf,
    ['confirmAssessmentRestart', 'resetCompletedAssessment'])
  const rejectRestart = findIf(completedBranch.thenStatement, (expression) =>
    print(expression, functions.sf).includes('!confirmed'))
  assert.ok(rejectRestart && isReturnOnly(rejectRestart.thenStatement),
    'startSelfTest must stop when restart is not confirmed')
  const resetFailure = findIf(completedBranch.thenStatement, (expression) =>
    callsNamed(expression, functions.sf, 'resetCompletedAssessment').length === 1)
  assert.ok(resetFailure && walk(resetFailure.thenStatement, ts.isThrowStatement).length === 1,
    'startSelfTest must fail if completed assessment cannot reset')
  const startNavigation = callsNamed(startTry.tryBlock, functions.sf, 'openPage')
    .find((call) => call.arguments.some((argument) => ts.isStringLiteral(argument)
      && argument.text === '/pages/practice/self-test-answer'))
  assert.ok(startNavigation && startNavigation.getStart() > completedBranch.getEnd(),
    'startSelfTest must navigate to the original answer page after restart handling')
  assert.equal(callsNamed(startTry.catchClause, functions.sf, 'uni.showToast').length, 1,
    'startSelfTest must retain failure toast')
  assert.ok(assignment(startTry.finallyBlock, 'startingSelfTest', 'value', ts.SyntaxKind.FalseKeyword),
    'startSelfTest must clear loading in finally')

  const reportStatements = report.body.statements
  assert.ok(ts.isIfStatement(reportStatements[0]) && property(reportStatements[0].expression, 'selfTestReportLoading', 'value')
    && isReturnOnly(reportStatements[0].thenStatement), 'report function must retain the in-flight guard')
  assert.ok(assignment(reportStatements[1], 'selfTestReportLoading', 'value', ts.SyntaxKind.TrueKeyword),
    'report function must set loading before query')
  const reportTry = reportStatements.find(ts.isTryStatement)
  assert.ok(reportTry, 'report function must retain try/catch/finally')
  requireCallOrder(reportTry.tryBlock, functions.sf,
    ['fetchLatestAssessmentResultStatus', 'uni.showModal', 'openPage'])
  const incomplete = findIf(reportTry.tryBlock, (expression) => print(expression, functions.sf)
    .includes('status?.completed !== true') && print(expression, functions.sf).includes('!status.recordId'))
  assert.ok(incomplete && callsNamed(incomplete.thenStatement, functions.sf, 'uni.showModal').length === 1
    && walk(incomplete.thenStatement, ts.isReturnStatement).length === 1,
  'report function must retain incomplete modal and early return')
  const reportNavigation = callsNamed(reportTry.tryBlock, functions.sf, 'openPage')[0]
  assert.ok(reportNavigation && print(reportNavigation.arguments[0], functions.sf)
    .includes('/pages/center/self-test-report?id='), 'report function must retain original report navigation')
  const missingBranch = findIf(reportTry.catchClause, (expression) => callsNamed(expression, functions.sf, 'test').length === 1)
  assert.ok(missingBranch && callsNamed(missingBranch.thenStatement, functions.sf, 'uni.showModal').length === 1,
    'report function must map missing records to the original incomplete modal')
  assert.equal(callsNamed(reportTry.catchClause, functions.sf, 'uni.showToast').length, 1,
    'report function must retain general failure toast')
  assert.ok(assignment(reportTry.finallyBlock, 'selfTestReportLoading', 'value', ts.SyntaxKind.FalseKeyword),
    'report function must clear loading in finally')
}

function requestCall(info, sf, requestName) {
  const call = calls(info.node).find((candidate) => callName(candidate, sf) === requestName)
  assert.ok(call, `${info.name} must call ${requestName}`)
  return call
}

function typeArgument(call, sf) {
  return call.typeArguments?.[0] ? print(call.typeArguments[0], sf) : ''
}

function assertLiteralArgument(call, index, expected, label) {
  const argument = call.arguments[index]
  assert.ok(argument && ts.isStringLiteral(argument) && argument.text === expected,
    `${label} argument ${index} changed`)
}

function testAssessmentProtectedSemantics() {
  const answer = sfcParts(paths.answer)
  const answerFunctions = functionMap(answer.script, paths.answer)
  const goNext = answerFunctions.map.get('goNext')
  const submitCurrent = answerFunctions.map.get('submitCurrent')
  assert.ok(goNext && submitCurrent, 'answer page must retain goNext and submitCurrent')
  assert.equal(callsNamed(goNext.node, answerFunctions.sf, 'submitAssessmentAnswers').length, 0,
    'goNext must have zero answer submission')
  assert.equal(callsNamed(goNext.node, answerFunctions.sf, 'loadQuestion').length, 1,
    'goNext must only load the next question')
  const nonLast = findIf(submitCurrent.node, (expression) => print(expression, answerFunctions.sf) === '!isLast.value')
  assert.ok(nonLast, 'submitCurrent must retain explicit non-last branch')
  assert.equal(callsNamed(nonLast.thenStatement, answerFunctions.sf, 'submitAssessmentAnswers').length, 0,
    'non-last branch must submit zero answers')
  assert.equal(callsNamed(nonLast.thenStatement, answerFunctions.sf, 'goNext').length, 1,
    'non-last branch must only advance once')
  assert.ok(walk(nonLast.thenStatement, ts.isReturnStatement).length === 1,
    'non-last branch must return before final submission')
  const finalSubmit = callsNamed(submitCurrent.node, answerFunctions.sf, 'submitAssessmentAnswers')
  assert.equal(finalSubmit.length, 1, 'last step must make one aggregate submission call')
  assert.ok(finalSubmit[0].getStart() > nonLast.getEnd(), 'aggregate submission must occur after non-last return')

  const assessment = functionMap(read(paths.assessment), paths.assessment)
  const signatures = {
    fetchAssessmentQuestions: 0,
    hasCompletedAssessment: 0,
    fetchLatestAssessmentResultStatus: 0,
    resetCompletedAssessment: 0,
    regenerateAssessmentReport: 1,
    fetchAssessmentQuestion: 1,
    submitAssessmentAnswers: 1,
    fetchAssessmentRecords: 0,
    fetchLatestAssessmentResult: 0,
    fetchAssessmentResult: 1
  }
  for (const [name, params] of Object.entries(signatures)) {
    assert.equal(assessment.map.get(name)?.params, params, `protected assessment signature changed: ${name}`)
  }
  const contracts = [
    ['hasCompletedAssessment', 'boolean', '/app-api/yj/practices/assessment-result/completed', 'GET'],
    ['fetchLatestAssessmentResultStatus', 'AssessmentResultStatus', '/app-api/yj/practices/assessment-result/latest-status', 'GET'],
    ['resetCompletedAssessment', 'boolean', '/app-api/yj/practices/assessment-result/reset', 'POST']
  ]
  for (const [name, response, endpoint, method] of contracts) {
    const call = requestCall(assessment.map.get(name), assessment.sf, 'requestAssessment')
    assert.equal(typeArgument(call, assessment.sf), response, `${name} response type changed`)
    assertLiteralArgument(call, 0, endpoint, name)
    assertLiteralArgument(call, 1, method, name)
  }
  const regenerate = requestCall(assessment.map.get('regenerateAssessmentReport'), assessment.sf, 'requestAssessment')
  assert.equal(typeArgument(regenerate, assessment.sf), 'AssessmentRegenerateResult', 'regenerate response type changed')
  assert.ok(print(regenerate.arguments[0], assessment.sf)
    .includes('/app-api/yj/practices/assessment-result/${encodeURIComponent(recordId)}/regenerate'),
  'regenerate endpoint or record encoding changed')
  assertLiteralArgument(regenerate, 1, 'POST', 'regenerateAssessmentReport')

  const questions = assessment.map.get('fetchAssessmentQuestions')
  requireCallOrder(questions.node, assessment.sf, ['fetchPracticeTopics', 'fetchLatestAssessmentResultStatus'])
  const resumeBranch = findIf(questions.node, (expression) => print(expression, assessment.sf)
    .includes('latestStatus?.completed === false'))
  assert.ok(resumeBranch, 'existing latest-status branch must retain its current behavior')
  requireCallOrder(resumeBranch.thenStatement, assessment.sf,
    ['fetchCatalogBatchDetail', 'buildSavedAssessmentAnswers', 'resolveResumeQuestionIndex', 'fetchAssessmentQuestion'])
  const startCall = requireCall(questions, assessment.sf, 'startAppPractice')
  assert.deepEqual(startCall.arguments.map((argument) => print(argument, assessment.sf)),
    ['ASSESSMENT_PRACTICE_ID', 'ASSESSMENT_MODE'], 'old start call arguments changed')
  const startPosition = startCall.getStart()
  const zeroQuestion = callsNamed(questions.node, assessment.sf, 'fetchAssessmentQuestion')
    .find((call) => call.getStart() > startPosition && print(call.arguments[0], assessment.sf) === '0')
  assert.ok(zeroQuestion, 'new self assessment must still load question index 0 after start')

  const submit = assessment.map.get('submitAssessmentAnswers')
  const loops = walk(submit.node, ts.isForOfStatement)
  assert.equal(loops.length, 1, 'answer submission must retain one ordered for-of loop')
  const submitCalls = callsNamed(submit.node, assessment.sf, 'submitAppPracticeAnswer')
  assert.equal(submitCalls.length, 1, 'answer submission must call backend once per loop iteration')
  assert.ok(submitCalls[0].getStart() >= loops[0].getStart() && submitCalls[0].getEnd() <= loops[0].getEnd(),
    'backend submission must stay inside ordered loop')
  assert.deepEqual(submitCalls[0].arguments.map((argument) => print(argument, assessment.sf)), [
    'assessmentPracticeId', 'assessmentSessionId', 'answer.questionId',
    'normalizeIds(answer.selectedOptionIds)', 'question?.index ?? index'
  ], 'ordered answer request arguments changed')
  requireCallOrder(loops[0], assessment.sf, ['findQuestion', 'submitAppPracticeAnswer', 'resultList.push'])
  const records = assessment.map.get('fetchAssessmentRecords')
  const recordsReturn = walk(records.body, ts.isReturnStatement)[0]
  assert.ok(recordsReturn?.expression && ts.isCallExpression(recordsReturn.expression),
    'record conversion must return a call chain')
  const mapCall = recordsReturn.expression
  assert.ok(ts.isPropertyAccessExpression(mapCall.expression) && mapCall.expression.name.text === 'map'
    && mapCall.arguments.length === 1 && print(mapCall.arguments[0], assessment.sf) === 'toAssessmentRecord',
  'record conversion must end with map(toAssessmentRecord)')
  const filterCall = mapCall.expression.expression
  assert.ok(ts.isCallExpression(filterCall) && ts.isPropertyAccessExpression(filterCall.expression)
    && filterCall.expression.name.text === 'filter' && filterCall.arguments.length === 1
    && print(filterCall.arguments[0], assessment.sf) === 'isAssessmentPracticeRecord',
  'record conversion must filter with isAssessmentPracticeRecord before mapping')
  const filterReceiver = filterCall.expression.expression
  const fetchCalls = callsNamed(filterReceiver, assessment.sf, 'fetchPracticeRecords')
  assert.equal(fetchCalls.length, 1, 'record conversion filter receiver must await fetchPracticeRecords once')
  assert.ok(walk(filterReceiver, ts.isAwaitExpression).length === 1,
    'record conversion must await fetchPracticeRecords before filter/map')
  const latest = assessment.map.get('fetchLatestAssessmentResult')
  requireCallOrder(latest.node, assessment.sf, ['fetchAssessmentRecords', 'fetchAssessmentResult'])
  assert.ok(findIf(latest.node, (expression) => print(expression, assessment.sf) === '!record'),
    'latest report must return null when record is absent')
  const result = assessment.map.get('fetchAssessmentResult')
  assert.ok(findIf(result.node, (expression) => print(expression, assessment.sf) === '!resultId'),
    'report detail must return null when id is absent')
  const resultReturn = walk(result.body, ts.isReturnStatement)
    .find((statement) => statement.expression && ts.isCallExpression(statement.expression))
  assert.ok(resultReturn && callName(resultReturn.expression, assessment.sf) === 'toAssessmentReport'
    && resultReturn.expression.arguments.length === 1,
  'report detail must return toAssessmentReport(...)')
  assert.equal(callsNamed(resultReturn.expression.arguments[0], assessment.sf, 'fetchPracticeRecordDetail').length, 1,
    'report conversion must consume fetchPracticeRecordDetail result')
  assert.equal(walk(resultReturn.expression.arguments[0], ts.isAwaitExpression).length, 1,
    'report conversion must await fetchPracticeRecordDetail')

  const practice = functionMap(read(paths.practice), paths.practice)
  const practiceRecords = requestCall(practice.map.get('fetchPracticeRecords'), practice.sf, 'requestYjAppPractice')
  assert.equal(typeArgument(practiceRecords, practice.sf), 'PracticeRecord[]', 'record list response changed')
  assertLiteralArgument(practiceRecords, 0, '/app-api/yj/practices/records', 'fetchPracticeRecords')
  assertLiteralArgument(practiceRecords, 1, 'GET', 'fetchPracticeRecords')
  const recordDetail = requestCall(practice.map.get('fetchPracticeRecordDetail'), practice.sf, 'requestYjAppPractice')
  assert.equal(typeArgument(recordDetail, practice.sf), 'PracticeRecordDetail', 'record detail response changed')
  assert.ok(print(recordDetail.arguments[0], practice.sf)
    .includes('/app-api/yj/practices/records/${encodeURIComponent(recordId)}'), 'record detail endpoint changed')
  assertLiteralArgument(recordDetail, 1, 'GET', 'fetchPracticeRecordDetail')
  const practiceStart = requestCall(practice.map.get('startAppPractice'), practice.sf, 'requestYjAppPractice')
  assert.equal(typeArgument(practiceStart, practice.sf), 'PracticeStartResultResponse', 'start response type changed')
  assert.ok(print(practiceStart.arguments[0], practice.sf)
    .includes('/app-api/yj/practices/${encodeURIComponent(practiceId)}/start?${params}'), 'start endpoint changed')
  assertLiteralArgument(practiceStart, 1, 'POST', 'startAppPractice')
  const startThen = callsNamed(practice.map.get('startAppPractice').node, practice.sf, 'then')
  assert.equal(startThen.length, 1, 'start response normalization chain changed')
  assert.deepEqual(startThen[0].arguments.map((argument) => print(argument, practice.sf)),
    ['normalizePracticeStartResult'], 'start response normalization changed')
}

function templateElements(template) {
  const ast = parseTemplate(template)
  const entries = []
  const visit = (node, ancestors = []) => {
    if (node.type === NodeTypes.ELEMENT) {
      entries.push({ node, ancestors })
      node.children.forEach((child) => visit(child, [...ancestors, node]))
    } else if (node.children) {
      node.children.forEach((child) => visit(child, ancestors))
    }
  }
  visit(ast)
  return entries
}

function staticText(node) {
  let value = ''
  const visit = (current) => {
    if (current.type === NodeTypes.TEXT) value += current.content
    if (current.type === NodeTypes.ATTRIBUTE && current.value) value += ` ${current.value.content}`
    current.children?.forEach(visit)
    current.props?.forEach(visit)
  }
  visit(node)
  return value.replace(/\s+/g, ' ').trim()
}

function attribute(element, name) {
  return element.props.find((prop) => prop.type === NodeTypes.ATTRIBUTE && prop.name === name)?.value?.content || ''
}

function directives(element, name) {
  return element.props.filter((prop) => prop.type === NodeTypes.DIRECTIVE && (!name || prop.name === name))
}

function eventDirectives(element) {
  return directives(element, 'on')
}

function eventExpression(element, event = 'tap') {
  return eventDirectives(element).find((item) => item.arg?.loc?.source === event)?.exp?.loc?.source || ''
}

function conditionalExpression(element) {
  return directives(element).find((item) => item.name === 'if' || item.name === 'show')?.exp?.loc?.source || ''
}

function handlerRoot(expression, functions) {
  const name = expression.trim().match(/^([A-Za-z_$][\w$]*)(?:\(.*\))?$/s)?.[1]
  if (name && functions.map.has(name)) return { name, info: functions.map.get(name) }
  const synthetic = functionMap(`const __inline = ($event: unknown) => { ${expression} }`, 'inline-handler.ts')
  return { name: '__inline', info: synthetic.map.get('__inline'), sf: synthetic.sf }
}

function handlerGraph(expression, functions, stopNames = new Set()) {
  const root = handlerRoot(expression, functions)
  const visited = new Set()
  const infos = []
  const internalNames = new Set()
  const internalCalls = []
  const externalCalls = []
  const visitInfo = (info, sf) => {
    if (!info || visited.has(info.name)) return
    visited.add(info.name)
    infos.push({ info, sf })
    for (const call of calls(info.node)) {
      const full = callName(call, sf)
      const leaf = full.split('.').at(-1)
      if (functions.map.has(leaf)) {
        internalNames.add(leaf)
        internalCalls.push({ name: leaf, call, owner: info.name, sf })
        if (!stopNames.has(leaf)) visitInfo(functions.map.get(leaf), functions.sf)
      } else if (full !== 'import') {
        externalCalls.push({ full, call, sf })
      }
    }
  }
  visitInfo(root.info, root.sf || functions.sf)
  return { ...root, infos, internalNames, internalCalls, externalCalls }
}

function graphAssignments(graph, expectedKind) {
  const states = new Set()
  for (const { info } of graph.infos) {
    for (const binary of walk(info.node, ts.isBinaryExpression)) {
      if (binary.operatorToken.kind !== ts.SyntaxKind.EqualsToken || binary.right.kind !== expectedKind) continue
      if (ts.isPropertyAccessExpression(binary.left) && binary.left.name.text === 'value'
        && ts.isIdentifier(binary.left.expression)) states.add(binary.left.expression.text)
    }
  }
  return states
}

function isDialogNode(node) {
  const role = attribute(node, 'role')
  const className = attribute(node, 'class')
  return role === 'dialog' || attribute(node, 'aria-modal') === 'true'
    || /(dialog|modal|selection|select-sheet|action-sheet)/i.test(className)
}

function locateDialogFromEntry(entry, elements, functions, expectedLabels) {
  const expression = eventExpression(entry.node)
  assert.ok(expression, 'original entry must have a tap handler')
  const graph = handlerGraph(expression, functions)
  const openedStates = graphAssignments(graph, ts.SyntaxKind.TrueKeyword)
  assert.ok(openedStates.size > 0, 'original entry handler must open a reactive selection state')
  const dialog = elements.find(({ node }) => isDialogNode(node)
    && [...openedStates].some((state) => conditionalExpression(node).includes(state))
    && expectedLabels.every((label) => staticText(node).includes(label)))
  assert.ok(dialog, `entry handler state must structurally own one dialog containing ${expectedLabels.join(' / ')}`)
  return { dialog, graph, openedStates }
}

function dialogTree(elements, dialog) {
  return [dialog, ...elements.filter((entry) => entry.ancestors.includes(dialog.node))]
}

function actionableOption(tree, label, otherLabel) {
  const candidates = tree.filter(({ node }) => {
    const text = staticText(node)
    return text.includes(label) && !text.includes(otherLabel) && eventDirectives(node).length > 0
  })
  assert.ok(candidates.length > 0, `dialog option is missing or has no action: ${label}`)
  const option = candidates.sort((left, right) => left.node.children.length - right.node.children.length)[0]
  const events = eventDirectives(option.node)
  assert.equal(events.length, 1, `${label} option must expose exactly one event`)
  assert.equal(events[0].arg?.loc?.source, 'tap', `${label} option business action must be bound only to tap`)
  return option
}

function assignmentFacts(graph) {
  const facts = []
  for (const { info, sf } of graph.infos) {
    for (const binary of walk(info.node, ts.isBinaryExpression)) {
      if (binary.operatorToken.kind !== ts.SyntaxKind.EqualsToken) continue
      facts.push({ left: print(binary.left, sf), right: print(binary.right, sf), node: binary })
    }
  }
  return facts
}

function assertCloseOnlyGraph(graph, dialogState, label, requireClose = true) {
  assert.equal(graph.externalCalls.length, 0,
    `${label} must execute zero external event/navigation/request calls: ${graph.externalCalls.map((item) => item.full).join(', ')}`)
  const facts = assignmentFacts(graph)
  assert.ok(facts.every((fact) => fact.left === `${dialogState}.value` && fact.right === 'false'),
    `${label} may only assign false to ${dialogState}.value`)
  if (requireClose) assert.ok(facts.some((fact) => fact.left === `${dialogState}.value` && fact.right === 'false'),
    `${label} must close ${dialogState}`)
}

function isCloseOnlyFunction(name, functions, dialogState) {
  const info = functions.map.get(name)
  if (!info) return false
  const graph = handlerGraph(name, functions)
  try {
    assertCloseOnlyGraph(graph, dialogState, name)
    return true
  } catch {
    return false
  }
}

function directCalls(graph, functions) {
  const { info, sf } = graph.infos[0]
  return calls(info.node).map((call) => {
    const full = callName(call, sf)
    const leaf = full.split('.').at(-1)
    return { full, leaf, local: functions.map.has(leaf), call, sf }
  }).filter((item) => item.full !== 'import')
}

function assertSelectionHandler(expression, functions, dialogState, kind, protectedTarget) {
  const root = handlerRoot(expression, functions)
  const rootGraph = { ...root, infos: [{ info: root.info, sf: root.sf || functions.sf }] }
  const direct = directCalls(rootGraph, functions)
  const closeCalls = direct.filter((item) => item.local && isCloseOnlyFunction(item.leaf, functions, dialogState))
  const businessCalls = direct.filter((item) => !closeCalls.includes(item))
  assert.equal(closeCalls.length, 1, `${kind} option must invoke exactly one local dialog-close action`)
  assert.equal(businessCalls.length, 1, `${kind} option must invoke exactly one business action`)
  const business = businessCalls[0]
  const wrapperGraph = handlerGraph(expression, functions, new Set(business.local ? [business.leaf] : []))
  const wrapperExternal = wrapperGraph.externalCalls.filter((item) => business.local || item.call !== business.call)
  assertCloseOnlyGraph({ ...wrapperGraph, externalCalls: wrapperExternal }, dialogState, `${kind} option wrapper`)

  if (kind === 'self') {
    assert.ok(business.local && business.leaf === protectedTarget,
      `self option must invoke only unchanged ${protectedTarget}`)
    assert.equal(wrapperGraph.internalCalls.filter((item) => item.name === protectedTarget).length, 1,
      `self option must invoke ${protectedTarget} exactly once`)
    return
  }

  const businessGraph = business.local
    ? handlerGraph(business.leaf, functions)
    : { infos: [{ info: initial.info, sf: initial.sf || functions.sf }], externalCalls: [business] }
  const semantic = businessGraph.infos.flatMap(({ info }) => semanticAst(info.node))
  assert.ok(semantic.includes('num:14') || semantic.includes('str:14'),
    'career option business action must explicitly carry categoryId=14')
  assert.ok(businessGraph.externalCalls.length > 0,
    'career option business action must reach navigation or service exactly through its single parallel action')
}

function assertDialogEventTree(tree, optionEntries, functions, dialogState) {
  let closeControlCount = 0
  for (const entry of tree) {
    const isOption = optionEntries.some((option) => option.node === entry.node)
    for (const event of eventDirectives(entry.node)) {
      if (isOption) continue
      const expression = event.exp?.loc?.source || ''
      if (!expression) {
        assert.ok(event.modifiers?.every((modifier) => ['stop', 'self', 'prevent'].includes(modifier)),
          'dialog event without handler may only use inert propagation modifiers')
        continue
      }
      const graph = handlerGraph(expression, functions)
      assertCloseOnlyGraph(graph, dialogState, 'dialog root/mask/cancel/close event')
      const text = staticText(entry.node)
      const className = attribute(entry.node, 'class')
      if (/(取消|关闭)/.test(text) || /(mask|overlay|close|cancel)/i.test(className)) {
        assertCloseOnlyGraph(graph, dialogState, 'cancel/mask/close handler')
        closeControlCount += 1
      }
    }
  }
  assert.ok(closeControlCount > 0, 'dialog must expose an audited cancel/mask/close event')
}

function auditHomeDialog(kind, home) {
  const elements = templateElements(home.template)
  const functions = functionMap(home.script, paths.home)
  const start = kind === 'start'
  const entryLabel = start ? '开始测评' : '评测结果'
  const selfLabel = start ? '自我评测' : '自我评测报告'
  const careerLabel = start ? '职业规划评测' : '职业规划评测报告'
  const protectedTarget = start ? 'startSelfTest' : 'openLatestSelfTestReport'
  const entries = elements.filter(({ node }) => attribute(node, 'aria-label') === entryLabel && eventExpression(node))
  assert.equal(entries.length, 1, `home must retain exactly one original ${entryLabel} entry`)
  const located = locateDialogFromEntry(entries[0], elements, functions, [selfLabel, careerLabel])
  assert.ok(!located.graph.internalNames.has(protectedTarget),
    `original ${entryLabel} click must only open the dialog before protected business logic`)
  assert.equal(located.graph.externalCalls.length, 0,
    `original ${entryLabel} click must make zero external request/navigation calls`)
  const dialogState = [...located.openedStates].find((state) => conditionalExpression(located.dialog.node).includes(state))
  const tree = dialogTree(elements, located.dialog)

  const selfOption = actionableOption(tree, selfLabel, careerLabel)
  assertSelectionHandler(eventExpression(selfOption.node), functions, dialogState, 'self', protectedTarget)
  const careerOption = actionableOption(tree, careerLabel, selfLabel)
  assertSelectionHandler(eventExpression(careerOption.node), functions, dialogState, 'career', protectedTarget)
  assertDialogEventTree(tree, [selfOption, careerOption], functions, dialogState)
}

function testHomeDialog(kind) {
  auditHomeDialog(kind, sfcParts(paths.home))
}

function testCareerFrontFeature() {
  const answer = sfcParts(paths.answer)
  const answerFunctions = functionMap(answer.script, paths.answer)
  const assessment = functionMap(read(paths.assessment), paths.assessment)
  assert.ok([...answerFunctions.map.values()].some((info) => semanticAst(info.node).includes('id:categoryId')),
    'answer page must retain explicit categoryId context')
  const loadHooks = calls(answerFunctions.sf).filter((call) => callName(call, answerFunctions.sf) === 'onLoad')
  assert.ok(loadHooks.some((call) => semanticAst(call).includes('id:categoryId')),
    'answer page must read categoryId from navigation')
  const submitCurrent = answerFunctions.map.get('submitCurrent')
  assert.ok(semanticAst(submitCurrent.node).includes('id:categoryId'),
    'last-step submission must carry categoryId')
  const nonLast = findIf(submitCurrent.node, (expression) => print(expression, answerFunctions.sf) === '!isLast.value')
  assert.ok(nonLast && callsNamed(nonLast.thenStatement, answerFunctions.sf, 'submitAssessmentAnswers').length === 0,
    'career non-last branch must retain zero submission')

  for (const endpoint of ['completed', 'latest-status', 'reset', 'regenerate']) {
    const categoryAware = [...assessment.map.values()].find((info) =>
      semanticAst(info.node).includes('id:categoryId') && info.text.includes(endpoint))
    assert.ok(categoryAware, `missing category-aware frontend service for ${endpoint}`)
  }
  const careerStart = [...assessment.map.values()].find((info) => {
    const semantic = semanticAst(info.node)
    return callsNamed(info.node, assessment.sf, 'startAppPractice').length > 0
      && semantic.includes('id:categoryId') && (semantic.includes('num:14') || semantic.includes('str:14'))
  })
  assert.ok(careerStart, 'missing explicit categoryId=14 start flow')
  const careerSubmit = [...assessment.map.values()].find((info) =>
    callsNamed(info.node, assessment.sf, 'submitAppPracticeAnswer').length > 0
    && semanticAst(info.node).includes('id:categoryId'))
  assert.ok(careerSubmit, 'missing category-aware last-step answer submission')
}

function javaTokens(source) {
  const tokens = []
  const identifierStart = /[A-Za-z_$\u0080-\uFFFF]/u
  const identifierPart = /[A-Za-z0-9_$\u0080-\uFFFF]/u
  let index = 0
  while (index < source.length) {
    const char = source[index]
    if (/\s/u.test(char)) {
      index += 1
      continue
    }
    if (char === '/' && source[index + 1] === '/') {
      index += 2
      while (index < source.length && source[index] !== '\n') index += 1
      continue
    }
    if (char === '/' && source[index + 1] === '*') {
      const end = source.indexOf('*/', index + 2)
      index = end < 0 ? source.length : end + 2
      continue
    }
    if (char === '"' || char === "'") {
      const quote = char
      const start = index++
      while (index < source.length) {
        if (source[index] === '\\') {
          index += 2
        } else if (source[index++] === quote) {
          break
        }
      }
      tokens.push({ kind: quote === '"' ? 'string' : 'char', value: source.slice(start, index), start, end: index })
      continue
    }
    if (identifierStart.test(char)) {
      const start = index++
      while (index < source.length && identifierPart.test(source[index])) index += 1
      tokens.push({ kind: 'identifier', value: source.slice(start, index), start, end: index })
      continue
    }
    if (/[0-9]/u.test(char)) {
      const start = index++
      while (index < source.length && /[A-Za-z0-9_.]/u.test(source[index])) index += 1
      tokens.push({ kind: 'number', value: source.slice(start, index), start, end: index })
      continue
    }
    const pair = source.slice(index, index + 2)
    if (['::', '->', '==', '!=', '<=', '>=', '&&', '||', '++', '--'].includes(pair)) {
      tokens.push({ kind: 'symbol', value: pair, start: index, end: index + 2 })
      index += 2
      continue
    }
    tokens.push({ kind: 'symbol', value: char, start: index, end: index + 1 })
    index += 1
  }
  return tokens
}

function tokenPairs(tokens) {
  const pairs = new Map()
  const stacks = Object.assign(Object.create(null), { '(': [], '[': [], '{': [] })
  const closes = Object.assign(Object.create(null), { ')': '(', ']': '[', '}': '{' })
  tokens.forEach((token, index) => {
    if (Object.hasOwn(stacks, token.value)) stacks[token.value].push(index)
    const open = closes[token.value]
    if (open) {
      const start = stacks[open].pop()
      assert.notEqual(start, undefined, `unbalanced Java token: ${token.value}`)
      pairs.set(start, index)
      pairs.set(index, start)
    }
  })
  for (const [open, stack] of Object.entries(stacks)) {
    assert.equal(stack.length, 0, `unbalanced Java token: ${open}`)
  }
  return pairs
}

function normalizedJava(tokens) {
  return tokens.map((token) => token.value).join('')
}

function splitJavaTokens(tokens, start, end) {
  const parts = []
  let partStart = start
  const levels = { '(': 0, '[': 0, '{': 0, '<': 0 }
  const opens = new Set(Object.keys(levels))
  const closes = { ')': '(', ']': '[', '}': '{', '>': '<' }
  for (let index = start; index < end; index += 1) {
    const value = tokens[index].value
    if (value === ',' && Object.values(levels).every((level) => level === 0)) {
      parts.push(tokens.slice(partStart, index))
      partStart = index + 1
      continue
    }
    if (opens.has(value)) levels[value] += 1
    else if (closes[value] && levels[closes[value]] > 0) levels[closes[value]] -= 1
  }
  if (partStart < end) parts.push(tokens.slice(partStart, end))
  return parts.filter((part) => part.length > 0)
}

function javaCalls(tokens, pairs, start, end) {
  const excluded = new Set(['if', 'for', 'while', 'switch', 'catch', 'synchronized', 'new', 'return', 'throw'])
  const result = []
  for (let index = start; index < end - 1; index += 1) {
    if (tokens[index].kind !== 'identifier' || tokens[index + 1].value !== '(' || excluded.has(tokens[index].value)) continue
    const close = pairs.get(index + 1)
    if (close === undefined || close >= end) continue
    let selectorStart = index
    while (selectorStart >= start + 2 && tokens[selectorStart - 1].value === '.'
      && tokens[selectorStart - 2].kind === 'identifier') selectorStart -= 2
    result.push({
      select: normalizedJava(tokens.slice(selectorStart, index + 1)),
      arguments: splitJavaTokens(tokens, index + 2, close).map(normalizedJava),
      index
    })
  }
  return result
}

function parseJavaSourceStructure(source, file) {
  const tokens = javaTokens(source)
  const pairs = tokenPairs(tokens)
  const typeIndex = tokens.findIndex((token) => token.value === 'class' || token.value === 'interface')
  assert.ok(typeIndex >= 0, `Java type declaration missing: ${path.basename(file)}`)
  const classOpen = tokens.findIndex((token, index) => index > typeIndex && token.value === '{')
  assert.ok(classOpen >= 0, `Java type body missing: ${path.basename(file)}`)
  const classClose = pairs.get(classOpen)
  const depth = []
  let braceDepth = 0
  tokens.forEach((token, index) => {
    depth[index] = braceDepth
    if (token.value === '{') braceDepth += 1
    else if (token.value === '}') braceDepth -= 1
  })

  const methods = new Map()
  const modifiers = new Set(['public', 'protected', 'private', 'static', 'final', 'abstract', 'default',
    'synchronized', 'native', 'strictfp'])
  for (let index = classOpen + 1; index < classClose - 1; index += 1) {
    if (depth[index] !== 1 || tokens[index].kind !== 'identifier' || tokens[index + 1]?.value !== '(') continue
    if (tokens[index - 1]?.value === '@' || tokens[index - 1]?.value === '.') continue
    const paramsClose = pairs.get(index + 1)
    if (paramsClose === undefined) continue
    let terminal = paramsClose + 1
    if (tokens[terminal]?.value === 'throws') {
      terminal += 1
      while (terminal < classClose && !['{', ';'].includes(tokens[terminal].value)) terminal += 1
    }
    if (!['{', ';'].includes(tokens[terminal]?.value)) continue
    let headerStart = index - 1
    while (headerStart > classOpen && ![';', '}', '{'].includes(tokens[headerStart - 1].value)) headerStart -= 1
    const signature = []
    for (let cursor = headerStart; cursor < index; cursor += 1) {
      if (tokens[cursor].value === '@') {
        cursor += 1
        while (tokens[cursor + 1]?.value === '.') cursor += 2
        if (tokens[cursor + 1]?.value === '(') cursor = pairs.get(cursor + 1)
      } else if (!modifiers.has(tokens[cursor].value)) {
        signature.push(tokens[cursor])
      }
    }
    if (signature.length === 0) continue
    const bodyStart = tokens[terminal].value === '{' ? terminal + 1 : terminal
    const bodyEnd = tokens[terminal].value === '{' ? pairs.get(terminal) : terminal
    const parameterParts = splitJavaTokens(tokens, index + 2, paramsClose)
    const parameters = parameterParts.map((part) => {
      const identifiers = part.filter((token) => token.kind === 'identifier')
      return identifiers.at(-1)?.value || ''
    })
    const annotations = []
    for (let cursor = headerStart; cursor < index; cursor += 1) {
      if (tokens[cursor].value !== '@' || tokens[cursor + 1]?.kind !== 'identifier') continue
      const nameStart = cursor + 1
      let nameEnd = nameStart
      while (tokens[nameEnd + 1]?.value === '.' && tokens[nameEnd + 2]?.kind === 'identifier') nameEnd += 2
      let args = []
      if (tokens[nameEnd + 1]?.value === '(') {
        const close = pairs.get(nameEnd + 1)
        args = tokens.slice(nameEnd + 2, close)
        cursor = close
      } else {
        cursor = nameEnd
      }
      annotations.push({ name: normalizedJava(tokens.slice(nameStart, nameEnd + 1)), args })
    }
    const method = {
      name: tokens[index].value,
      returnType: normalizedJava(signature),
      parameters,
      parameterDeclarations: parameterParts.map(normalizedJava),
      bodyTokens: tokens.slice(bodyStart, bodyEnd),
      calls: javaCalls(tokens, pairs, bodyStart, bodyEnd),
      annotations
    }
    if (!methods.has(method.name)) methods.set(method.name, [])
    methods.get(method.name).push(method)
    index = terminal
  }

  const fields = new Map()
  for (let index = classOpen + 1; index < classClose; index += 1) {
    if (depth[index] !== 1 || tokens[index].kind !== 'identifier' || tokens[index + 1]?.value !== '=') continue
    let end = index + 2
    while (end < classClose && !(depth[end] === 1 && tokens[end].value === ';')) end += 1
    if (end < classClose) fields.set(tokens[index].value, normalizedJava(tokens.slice(index + 2, end)))
  }
  return { file, methods, fields }
}

function parseJavaStructure(file) {
  return parseJavaSourceStructure(read(file), file)
}

function javaMethod(parsed, name, parameterCount) {
  const method = (parsed.methods.get(name) || []).find((candidate) => candidate.parameters.length === parameterCount)
  assert.ok(method, `method missing: ${path.basename(parsed.file)}#${name}/${parameterCount}`)
  return method
}

function javaCall(method, suffix) {
  const matches = method.calls.filter((call) => call.select === suffix || call.select.endsWith(`.${suffix}`))
  assert.ok(matches.length > 0, `call missing in ${method.name}: ${suffix}`)
  return matches[0]
}

function requireJavaCallOrder(method, suffixes) {
  let cursor = -1
  for (const suffix of suffixes) {
    const found = method.calls.find((call) => call.index > cursor
      && (call.select === suffix || call.select.endsWith(`.${suffix}`)))
    assert.ok(found, `call order missing in ${method.name} after token ${cursor}: ${suffix}; actual=${method.calls.map((call) => call.select).join(' -> ')}`)
    cursor = found.index
  }
}

function javaHasIdentifier(method, identifier) {
  return method.bodyTokens.some((token) => token.kind === 'identifier' && token.value === identifier)
}

function requireJavaControllerMethod(controller, name, parameterCount, mappingType, mappingPath, responseType,
  serviceCall, expectedArguments = [], expectedParameters = []) {
  const method = javaMethod(controller, name, parameterCount)
  const mappings = method.annotations.filter((annotation) => annotation.name.endsWith('Mapping'))
  assert.equal(mappings.length, 1, `${name} must retain exactly one HTTP mapping annotation`)
  const mapping = mappings[0]
  assert.equal(mapping.name, mappingType, `${name} HTTP method annotation changed`)
  assert.equal(normalizedJava(mapping.args), `"${mappingPath}"`, `${name} mapping path or attributes changed`)
  assert.equal(method.returnType, responseType, `${name} response type changed`)
  assert.deepEqual(method.parameterDeclarations, expectedParameters, `${name} HTTP parameters changed`)
  assert.deepEqual(javaCall(method, `frontPracticeService.${serviceCall}`).arguments, expectedArguments,
    `${name} service arguments changed`)
  javaCall(method, 'success')
}

function javaProtectionSuite() {
  const javaRoot = path.join(repoRoot, 'code', 'develop', 'yunjikeji-admin-server', 'yunjikeji-admin-server',
    'src', 'main', 'java', 'com', 'huiyitech', 'app', 'practice')
  const controller = parseJavaStructure(path.join(javaRoot, 'controller', 'FrontPracticeController.java'))
  const service = parseJavaStructure(path.join(javaRoot, 'service', 'FrontPracticeService.java'))
  const impl = parseJavaStructure(path.join(javaRoot, 'service', 'FrontPracticeServiceImpl.java'))
  const batch = parseJavaStructure(path.join(javaRoot, 'service', 'FrontPracticeBatchService.java'))

  const controllers = [
    ['hasCompletedAssessmentResult', 0, 'GetMapping', '/app-api/yj/practices/assessment-result/completed', 'CommonResult<Boolean>', [], []],
    ['getLatestAssessmentResultStatus', 0, 'GetMapping', '/app-api/yj/practices/assessment-result/latest-status', 'CommonResult<AppAssessmentResultStatusRespVO>', [], []],
    ['resetCompletedAssessmentResult', 0, 'PostMapping', '/app-api/yj/practices/assessment-result/reset', 'CommonResult<Boolean>', [], []],
    ['regenerateAssessmentReport', 1, 'PostMapping', '/app-api/yj/practices/assessment-result/{recordId}/regenerate', 'CommonResult<AppPracticeAnswerSubmitRespVO>', ['recordId'], ['@PathVariable("recordId")LongrecordId']],
    ['startPractice', 3, 'PostMapping', '/app-api/yj/practices/{practiceId}/start', 'CommonResult<AppPracticeStartRespVO>', ['practiceId', 'topicId', 'mode'], ['@PathVariable("practiceId")StringpracticeId', '@RequestParam(value="topicId",defaultValue="")StringtopicId', '@RequestParam(value="mode",defaultValue="standard")Stringmode']],
    ['getRecords', 0, 'GetMapping', '/app-api/yj/practices/records', 'CommonResult<List<AppPracticeRecordRespVO>>', [], []],
    ['getRecordDetail', 1, 'GetMapping', '/app-api/yj/practices/records/{recordId}', 'CommonResult<AppPracticeRecordDetailRespVO>', ['recordId'], ['@PathVariable("recordId")StringrecordId']]
  ]
  for (const [name, count, mappingType, mapping, response, args, parameters] of controllers) {
    requireJavaControllerMethod(controller, name, count, mappingType, mapping, response, name, args, parameters)
  }
  const interfaces = [
    ['hasCompletedAssessmentResult', 0, 'Boolean'],
    ['getLatestAssessmentResultStatus', 0, 'AppAssessmentResultStatusRespVO'],
    ['resetCompletedAssessmentResult', 0, 'Boolean'],
    ['regenerateAssessmentReport', 1, 'AppPracticeAnswerSubmitRespVO'],
    ['startPractice', 3, 'AppPracticeStartRespVO'],
    ['getRecords', 0, 'List<AppPracticeRecordRespVO>'],
    ['getRecordDetail', 1, 'AppPracticeRecordDetailRespVO']
  ]
  for (const [name, count, response] of interfaces) {
    assert.equal(javaMethod(service, name, count).returnType, response, `${name} service response changed`)
  }
  assert.equal(impl.fields.get('SELF_ASSESSMENT_CATEGORY_ID'), '13L', 'classification 13 constant changed')
  assert.equal(impl.fields.get('ASSESSMENT_AGENT_INFO_ID'), '2L', 'Agent 2 constant changed')
  assert.equal(batch.fields.get('SELF_ASSESSMENT_CATEGORY_ID'), '13L', 'batch classification 13 constant changed')
  assert.equal(batch.fields.get('ASSESSMENT_CATALOG_TYPE'), '1', 'assessment catalog type changed')

  const start = javaMethod(impl, 'startPractice', 3)
  assert.ok(javaHasIdentifier(start, 'ASSESSMENT_MODE') && start.bodyTokens.some((token) => token.value === 'case'),
    'assessment start switch branch missing')
  assert.deepEqual(javaCall(start, 'frontPracticeBatchService.startAssessment').arguments,
    ['loginUser', 'practiceId', 'topicId'], 'classification 13 start delegation changed')
  const batchStart = javaMethod(batch, 'startAssessment', 3)
  requireJavaCallOrder(batchStart, ['resolveSelectedAssessmentCategory', 'startBatch'])
  assert.ok(javaCall(batchStart, 'startBatch').arguments.some((argument) =>
    argument.includes('listCategoryExerciseIds(category.getId())')),
  'classification 13 startBatch must consume category exercise ids')
  const selectCategory = javaMethod(batch, 'resolveSelectedAssessmentCategory', 0)
  assert.ok(javaHasIdentifier(selectCategory, 'ASSESSMENT_CATALOG_TYPE'), 'classification 13 catalog type selection missing')
  javaCall(selectCategory, 'practiceCategoryMapper.selectList')

  requireJavaCallOrder(javaMethod(impl, 'hasCompletedAssessmentResult', 0),
    ['AppMobileAuthUtils.requireStudentLoginUser', 'listCompletedAssessmentBatches', 'isEmpty'])
  assert.ok(javaHasIdentifier(javaMethod(impl, 'listCompletedAssessmentBatches', 1), 'SELF_ASSESSMENT_CATEGORY_ID'),
    'completed must stay scoped to category 13')
  const latest = javaMethod(impl, 'getLatestAssessmentResultStatus', 0)
  assert.ok(javaHasIdentifier(latest, 'SELF_ASSESSMENT_CATEGORY_ID'), 'latest-status must stay scoped to category 13')
  requireJavaCallOrder(latest, ['AppMobileAuthUtils.requireStudentLoginUser', 'practiceCatalogBatchMapper.selectOne',
    'AppAssessmentResultStatusRespVO.builder'])
  requireJavaCallOrder(javaMethod(impl, 'resetCompletedAssessmentResult', 0),
    ['listCompletedAssessmentBatches', 'selectAssessmentRecordIdsForPhysicalDelete', 'jdbcTemplate.update',
      'physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds',
      'physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds', 'deleteAssessmentBatches'])
  requireJavaCallOrder(javaMethod(impl, 'regenerateAssessmentReport', 1),
    ['requireUserRecord', 'requireCompletedAssessmentBatch', 'findLatestAssessmentResult',
      'buildRegenerateAssessmentResponse', 'buildRecordAnswers', 'claimFailedAssessmentResult',
      'enqueueAssessmentEvaluation'])
  const requireBatch = javaMethod(impl, 'requireCompletedAssessmentBatch', 2)
  requireJavaCallOrder(requireBatch, ['record.getCategoryId', 'practiceCatalogBatchMapper.selectById', 'batch.getCategoryId'])
  assert.ok(javaHasIdentifier(requireBatch, 'SELF_ASSESSMENT_CATEGORY_ID'), 'regenerate category 13 guard missing')
  requireJavaCallOrder(javaMethod(impl, 'submitAnswer', 3),
    ['frontPracticeBatchService.submitAnswer', 'response.getCompleted', 'isAssessmentSession', 'resolveRecordId',
      'buildRecordAnswers', 'claimInitialAssessmentReport', 'enqueueAssessmentEvaluation'])
  requireJavaCallOrder(javaMethod(impl, 'applyAssessmentEvaluation', 5),
    ['callAssessmentEvaluationAi', 'response.setAssessmentReportContent', 'persistSelfReport'])
  const ai = javaMethod(impl, 'callAssessmentEvaluationAi', 3)
  requireJavaCallOrder(ai, ['requireAssessmentAiConfiguration', 'findAssessmentAgentConfig',
    'buildAssessmentStudentProfile', 'ruleEngine.buildContext', 'deepSeekOpenAiClient.complete'])
  assert.ok(javaHasIdentifier(ai, 'SelfAssessmentV3RuleEngine'), 'classification 13 V3 engine route missing')
  assert.ok(javaCall(javaMethod(impl, 'findAssessmentAgentConfig', 1), 'jdbcTemplate.queryForList')
    .arguments.includes('ASSESSMENT_AGENT_INFO_ID'), 'Agent query must use fixed id 2')
  console.log('PASS Java structural AST classification-13 API and Agent2/V3 call chain')
}

function javaFeatureSuite() {
  const javaRoot = path.join(repoRoot, 'code', 'develop', 'yunjikeji-admin-server', 'yunjikeji-admin-server',
    'src', 'main', 'java', 'com', 'huiyitech', 'app', 'practice')
  const controller = parseJavaStructure(path.join(javaRoot, 'controller', 'FrontPracticeController.java'))
  const service = parseJavaStructure(path.join(javaRoot, 'service', 'FrontPracticeService.java'))
  const impl = parseJavaStructure(path.join(javaRoot, 'service', 'FrontPracticeServiceImpl.java'))
  const careerEnginePath = path.join(javaRoot, 'service', 'CareerPlanningRuleEngine.java')
  assert.equal(impl.fields.get('CAREER_ASSESSMENT_CATEGORY_ID'), '14L', 'classification 14 constant missing')
  assert.equal(impl.fields.get('CAREER_ASSESSMENT_AGENT_INFO_ID'), '3L', 'Agent 3 constant missing')
  assert.ok(fs.existsSync(careerEnginePath), 'CareerPlanningRuleEngine.java is missing')
  assert.ok([...parseJavaStructure(careerEnginePath).methods.values()].flat().length > 0,
    'CareerPlanningRuleEngine must expose executable rule methods')
  assert.ok([...controller.methods.values()].flat().some((method) => method.parameters.includes('categoryId'))
    && [...service.methods.values()].flat().some((method) => method.parameters.includes('categoryId')),
  'backend API must expose explicit categoryId parallel methods')
  const implMethods = [...impl.methods.values()].flat()
  assert.ok(implMethods.some((method) => {
    const names = method.calls.map((call) => call.select)
    return ['record.getCategoryId', 'practiceCatalogBatchMapper.selectById', 'batch.getCategoryId']
      .every((name) => names.includes(name))
  }), 'career report must traverse record category -> catalog batch category')
  assert.ok(implMethods.some((method) => javaHasIdentifier(method, 'CAREER_ASSESSMENT_CATEGORY_ID')
    && javaHasIdentifier(method, 'CareerPlanningRuleEngine')), 'category 14 must route to CareerPlanningRuleEngine')
  assert.ok(implMethods.some((method) => javaHasIdentifier(method, 'CAREER_ASSESSMENT_AGENT_INFO_ID')
    && method.bodyTokens.some((token) => token.kind === 'string' && token.value.includes('yj_agent_info'))),
  'category 14 must query fixed Agent id 3')
  console.log('PASS Java structural AST classification-14 backend routing')
}

function assertMutationRejected(action, label) {
  assert.throws(action, { name: 'AssertionError' }, `mutation escaped contract: ${label}`)
}

function staticContractMutationProof() {
  const dialogScript = `
    const startAssessmentDialogVisible = ref(false)
    function openStartAssessmentDialog() { startAssessmentDialogVisible.value = true }
    function closeStartAssessmentDialog() { startAssessmentDialogVisible.value = false }
    function startSelfTest() { openPage('/pages/practice/self-test-answer') }
    function selectSelfAssessment() { closeStartAssessmentDialog(); startSelfTest() }
    function startCareerAssessment() { startAssessmentByCategory(14) }
    function selectCareerAssessment() { closeStartAssessmentDialog(); startCareerAssessment() }
  `
  const dialogTemplate = `
    <button aria-label="开始测评" @tap="openStartAssessmentDialog"><text>开始测评</text></button>
    <view v-if="startAssessmentDialogVisible" class="assessment-dialog-mask" role="dialog"
      aria-modal="true" @tap="closeStartAssessmentDialog">
      <view class="assessment-dialog" @tap.stop>
        <button @tap="selectSelfAssessment"><text>自我评测</text></button>
        <button @tap="selectCareerAssessment"><text>职业规划评测</text></button>
        <button class="cancel" @tap="closeStartAssessmentDialog"><text>取消</text></button>
      </view>
    </view>
  `
  auditHomeDialog('start', { script: dialogScript, template: dialogTemplate })
  assertMutationRejected(() => auditHomeDialog('start', {
    script: `${dialogScript}\nfunction closeAndRequest() { startAssessmentDialogVisible.value = false; requestData() }`,
    template: dialogTemplate.replace('@tap="closeStartAssessmentDialog"', '@tap="closeAndRequest"')
  }), 'dialog root event adds request')
  assertMutationRejected(() => auditHomeDialog('start', {
    script: dialogScript.replace('startAssessmentDialogVisible.value = false',
      'startAssessmentDialogVisible.value = false; requestData()'),
    template: dialogTemplate
  }), 'shared cancel/mask/close handler adds request')
  assertMutationRejected(() => auditHomeDialog('start', {
    script: dialogScript.replace('closeStartAssessmentDialog(); startSelfTest()',
      "closeStartAssessmentDialog(); openPage('/extra'); startSelfTest()"),
    template: dialogTemplate
  }), 'self option adds navigation')
  assertMutationRejected(() => auditHomeDialog('start', {
    script: dialogScript.replace('closeStartAssessmentDialog(); startCareerAssessment()',
      'closeStartAssessmentDialog(); startCareerAssessment(); auditBusinessAction()'),
    template: dialogTemplate
  }), 'career option adds second business action')
  assertMutationRejected(() => auditHomeDialog('start', {
    script: dialogScript,
    template: dialogTemplate.replace('@tap="selectSelfAssessment"',
      '@tap="selectSelfAssessment" @longpress="requestData"')
  }), 'self option adds a second event')

  const javaGood = parseJavaSourceStructure(`
    class ProbeController {
      @GetMapping("/app-api/yj/practices/records/{recordId}")
      public CommonResult<AppPracticeRecordDetailRespVO> getRecordDetail(
          @PathVariable("recordId") String recordId) {
        return success(frontPracticeService.getRecordDetail(recordId));
      }
    }
  `, 'ProbeController.java')
  const javaArgs = [javaGood, 'getRecordDetail', 1, 'GetMapping',
    '/app-api/yj/practices/records/{recordId}', 'CommonResult<AppPracticeRecordDetailRespVO>',
    'getRecordDetail', ['recordId'], ['@PathVariable("recordId")StringrecordId']]
  requireJavaControllerMethod(...javaArgs)
  const swapped = parseJavaSourceStructure(`
    class ProbeController {
      @PostMapping("/app-api/yj/practices/records/{recordId}")
      public CommonResult<AppPracticeRecordDetailRespVO> getRecordDetail(
          @PathVariable("recordId") String recordId) {
        return success(frontPracticeService.getRecordDetail(recordId));
      }
    }
  `, 'ProbeController.java')
  assertMutationRejected(() => requireJavaControllerMethod(swapped, ...javaArgs.slice(1)),
    'GetMapping changed to PostMapping')
  const wrongPath = parseJavaSourceStructure(`
    class ProbeController {
      @GetMapping("/app-api/yj/practices/records/{id}")
      public CommonResult<AppPracticeRecordDetailRespVO> getRecordDetail(
          @PathVariable("recordId") String recordId) {
        return success(frontPracticeService.getRecordDetail(recordId));
      }
    }
  `, 'ProbeController.java')
  assertMutationRejected(() => requireJavaControllerMethod(wrongPath, ...javaArgs.slice(1)),
    'HTTP path changed')
  const wrongParameter = parseJavaSourceStructure(`
    class ProbeController {
      @GetMapping("/app-api/yj/practices/records/{recordId}")
      public CommonResult<AppPracticeRecordDetailRespVO> getRecordDetail(
          @RequestParam("recordId") String recordId) {
        return success(frontPracticeService.getRecordDetail(recordId));
      }
    }
  `, 'ProbeController.java')
  assertMutationRejected(() => requireJavaControllerMethod(wrongParameter, ...javaArgs.slice(1)),
    'HTTP parameter annotation changed')
  const wrongCall = parseJavaSourceStructure(`
    class ProbeController {
      @GetMapping("/app-api/yj/practices/records/{recordId}")
      public CommonResult<AppPracticeRecordDetailRespVO> getRecordDetail(
          @PathVariable("recordId") String recordId) {
        return success(frontPracticeService.getRecords());
      }
    }
  `, 'ProbeController.java')
  assertMutationRejected(() => requireJavaControllerMethod(wrongCall, ...javaArgs.slice(1)),
    'Controller service call changed')
  runPythonSuite('mutation')
  console.log('PASS built-in dialog/HTTP/Python mutation proofs')
}

function runPythonSuite(suite) {
  const execute = spawnSync('python', [paths.pythonChecker, '--suite', suite, '--repo-root', repoRoot], {
    encoding: 'utf8', windowsHide: true
  })
  assert.equal(execute.status, 0, (execute.stderr || execute.stdout || 'Python AST check failed').trim())
  if (execute.stdout.trim()) console.log(execute.stdout.trim())
}

const suites = {
  protection: [
    ['home classification-13 semantic AST', testHomeProtectedSemantics],
    ['answer/service classification-13 control and API semantics', testAssessmentProtectedSemantics],
    ['Java classification-13/API exact HTTP and mutation contracts', () => {
      javaProtectionSuite()
      staticContractMutationProof()
    }]
  ],
  feature: [
    ['home start dialog ownership and handlers', () => testHomeDialog('start')],
    ['home report dialog ownership and handlers', () => testHomeDialog('report')],
    ['classification-14 frontend flow', testCareerFrontFeature],
    ['classification-14 backend structural AST routing', javaFeatureSuite],
    ['manual career question tool AST contract', () => runPythonSuite('question')],
    ['manual career Agent tool AST contract', () => runPythonSuite('agent')],
    ['manual tool whole-repository isolation', () => runPythonSuite('isolation')]
  ]
}

function run(selected) {
  const cases = selected === 'all' ? [...suites.protection, ...suites.feature] : suites[selected]
  if (!cases) throw new Error(`unknown suite: ${selected}`)
  const failures = []
  for (const [name, test] of cases) {
    try {
      test()
      console.log(`PASS ${name}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      failures.push({ name, message })
      console.error(`FAIL ${name}: ${message}`)
    }
  }
  console.log(`SUMMARY suite=${selected} passed=${cases.length - failures.length} failed=${failures.length}`)
  if (failures.length) process.exitCode = 1
}

run((process.argv[2] || '--suite=all').replace(/^--suite=/, ''))
