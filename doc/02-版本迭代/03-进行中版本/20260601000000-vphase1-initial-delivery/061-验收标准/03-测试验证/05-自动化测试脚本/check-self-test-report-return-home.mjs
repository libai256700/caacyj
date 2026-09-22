import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const reportPagePath = resolve(
  process.cwd(),
  'code/develop/yunjikeji/src/pages/center/self-test-report.vue'
)
const source = readFileSync(reportPagePath, 'utf8')

const reportActions = source.match(/<button\s+class="report-action"[\s\S]*?<\/button>/g) || []
assert.equal(reportActions.length, 1, '报告页应只保留一个主操作按钮')
assert.match(
  reportActions[0],
  /@tap="goHome">\s*返回首页\s*<\/button>/,
  '主操作按钮应显示“返回首页”并调用 goHome'
)
assert.doesNotMatch(source, /返回中心继续对话/, '报告页不得残留旧文案“返回中心继续对话”')
assert.doesNotMatch(source, /\bgoCenter\b/, '报告页不得残留旧的 goCenter 处理函数')

assert.match(
  source,
  /const goBack = \(\) => \{[\s\S]*?uni\.navigateBack\(\{[\s\S]*?fail:\s*goHome[\s\S]*?\}\)[\s\S]*?\}/,
  '顶部返回失败时应复用 goHome 返回首页'
)
assert.match(
  source,
  /const goHome = \(\) => \{[\s\S]*?uni\.reLaunch\(\{\s*url:\s*['"]\/pages\/home['"]\s*\}\)[\s\S]*?\}/,
  'goHome 应使用 uni.reLaunch 进入 /pages/home'
)

console.log('self-test report return-home contract passed')
