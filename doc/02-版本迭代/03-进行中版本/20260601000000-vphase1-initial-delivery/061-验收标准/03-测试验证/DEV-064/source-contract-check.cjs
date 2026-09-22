const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '../../../../../../../')
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8')
const assertIncludes = (content, token, label) => {
  if (!content.includes(token)) {
    throw new Error(`${label}: missing ${token}`)
  }
}

const batchService = read('code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/practice/service/FrontPracticeBatchService.java')
const controller = read('code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/practice/controller/FrontPracticeController.java')
const config = read('code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/resources/application.yaml')
const practiceService = read('code/develop/yunjikeji/src/services/practice.ts')
const examModes = read('code/develop/yunjikeji/src/pages/practice/exam-modes.vue')
const answer = read('code/develop/yunjikeji/src/pages/practice/answer.vue')

assertIncludes(config, 'HUIYITECH_PRACTICE_EXAM_THEORY_MINUTES', 'config')
assertIncludes(config, 'HUIYITECH_PRACTICE_EXAM_COMPREHENSIVE_MINUTES', 'config')
assertIncludes(config, 'HUIYITECH_PRACTICE_EXAM_INSTRUCTOR_MINUTES', 'config')
for (const token of ['THEORY_EXAM_MODE', 'COMPREHENSIVE_EXAM_MODE', 'INSTRUCTOR_EXAM_MODE', 'completeExpiredExamBatches', 'closeIncompleteExamBatches', 'timeLimitMinutes']) {
  assertIncludes(batchService, token, 'batch service')
}
assertIncludes(controller, '/app-api/yj/practices/exam-batches/close-incomplete', 'controller')
assertIncludes(practiceService, '/app-api/yj/practices/exam-batches/close-incomplete', 'frontend service')
assertIncludes(examModes, 'closeIncompleteExamBatches()', 'exam modes page')
assertIncludes(answer, 'formattedRemainingTime', 'answer timer')
console.log('DEV-064 source contract: PASS')
