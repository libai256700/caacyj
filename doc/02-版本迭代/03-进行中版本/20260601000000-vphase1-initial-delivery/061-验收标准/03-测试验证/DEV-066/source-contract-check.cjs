const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '../../../../../../../')
const answerPage = fs.readFileSync(path.join(root, 'code/develop/yunjikeji/src/pages/practice/self-test-answer.vue'), 'utf8')
const assessment = fs.readFileSync(path.join(root, 'code/develop/yunjikeji/src/services/assessment.ts'), 'utf8')

for (const [label, source, pattern] of [
  ['optional-label', answerPage, /isOptionalQuestion/],
  ['optional-submit-gate', answerPage, /isOptionalQuestion\.value \|\|/],
  ['required-normalization', assessment, /isRequired: normalizeRequired/]
]) {
  if (!pattern.test(source)) throw new Error(`missing ${label}`)
}
console.log('DEV-066 source contract passed')
