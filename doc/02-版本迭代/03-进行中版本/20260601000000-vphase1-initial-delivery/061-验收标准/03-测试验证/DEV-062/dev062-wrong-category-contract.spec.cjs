const fs = require('fs')
const path = require('path')

const outputDir = __dirname
const appDir = path.resolve(__dirname, '../../../../../../../code/develop/yunjikeji')

const readFile = (filePath) => fs.readFileSync(filePath, 'utf8')
const homeSource = readFile(path.join(appDir, 'src/pages/home.vue'))
const topicsSource = readFile(path.join(appDir, 'src/pages/practice/exam-topics.vue'))

const checks = []
const assertMatch = (name, source, pattern, description) => {
  const passed = pattern.test(source)
  checks.push({ name, passed, description })
  return passed
}

const failures = []

const expectedChecks = [
  [
    'home-wrong-review-route',
    homeSource,
    /\/pages\/practice\/exam-topics\?mode=wrongReview/,
    '首页错题入口应先进入分类页'
  ],
  [
    'topics-mode-typing',
    topicsSource,
    /type TopicEntryMode = 'practice' \| 'chapter-test' \| 'wrongReview'/,
    '分类页应支持 wrongReview 模式'
  ],
  [
    'topics-title',
    topicsSource,
    /mode\.value === 'wrongReview'\)\s*return '错题练习'/s,
    '分类页标题应显示错题练习'
  ],
  [
    'topics-loading',
    topicsSource,
    /正在加载\$\{pageTitle\.value\}分类/,
    '分类页加载态应按当前标题展示'
  ],
  [
    'topics-wrong-review-start',
    topicsSource,
    /startPractice\(DEFAULT_PRACTICE_ID,\s*'wrongReview',\s*selectedTopicId\)/s,
    '错题分类应调用真实 wrongReview 启动接口'
  ],
  [
    'topics-next-page',
    topicsSource,
    /result\.nextPage/,
    '应按后端 nextPage 进入答题页'
  ],
  [
    'topics-record-batch',
    topicsSource,
    /recordId|catalogBatchId/,
    '应承接 recordId 与 catalogBatchId'
  ],
  [
    'topics-empty-toast',
    topicsSource,
    /当前暂无错题可练习/,
    '空错题分类应给出真实反馈'
  ],
  [
    'topics-normal-branch',
    topicsSource,
    /startChapterTestBatch|startPracticeModeBatch/,
    '普通 practice/chapter 分支应保留'
  ]
]

for (const [name, source, pattern, description] of expectedChecks) {
  const passed = assertMatch(name, source, pattern, description)
  if (!passed) {
    failures.push(name)
  }
}

const result = {
  command: 'node dev062-wrong-category-contract.spec.cjs',
  status: failures.length ? 'failed' : 'passed',
  failures,
  checks
}

fs.writeFileSync(path.join(outputDir, 'playwright-results.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')

if (failures.length) {
  console.error(`DEV-062 contract failed: ${failures.join(', ')}`)
  process.exit(1)
}

console.log('DEV-062 contract passed')
