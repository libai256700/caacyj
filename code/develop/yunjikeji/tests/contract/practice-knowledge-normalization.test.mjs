import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('../../src/services/practice.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020
  }
}).outputText

const loadPracticeService = (responseData) => {
  const module = { exports: {} }
  const context = vm.createContext({
    module,
    exports: module.exports,
    require: (specifier) => {
      if (specifier === './apiBase') {
        return {
          getApiBaseUrl: () => 'https://example.test',
          getYjAppApiBaseUrl: () => 'https://example.test'
        }
      }
      if (specifier === './request') {
        return {
          buildAuthHeader: () => ({}),
          handleUnauthorizedResponse: () => false
        }
      }
      throw new Error(`Unexpected module request: ${specifier}`)
    },
    uni: {
      request: ({ success }) => success({
        statusCode: 200,
        data: responseData
      })
    },
    URLSearchParams,
    console,
    setTimeout,
    clearTimeout
  })

  new vm.Script(compiled, { filename: 'practice.ts' }).runInContext(context)
  return module.exports
}

const queryWithData = async (data) => {
  const service = loadPracticeService({ code: 0, data })
  return service.queryKnowledge('旋翼无人机')
}

test('does not turn an answer-only root response into a reference', async () => {
  const raw = { answer: '旋翼无人机依靠旋翼产生升力。' }
  const result = await queryWithData(raw)

  assert.equal(result.answer, raw.answer)
  assert.deepEqual(JSON.parse(JSON.stringify(result.references)), [])
  assert.strictEqual(result.raw, raw)
})

test('extracts references only from explicit reference containers', async () => {
  const containerNames = [
    'references',
    'citations',
    'segments',
    'records',
    'list',
    'result',
    'results',
    'items'
  ]

  for (const containerName of containerNames) {
    const result = await queryWithData({
      answer: '归一化答案',
      [containerName]: [{ source: containerName, content: `${containerName} 内容` }]
    })

    assert.deepEqual(
      JSON.parse(JSON.stringify(result.references)),
      [{ source: containerName, content: `${containerName} 内容` }]
    )
  }
})

test('deduplicates real references while preserving answer and raw data', async () => {
  const reference = { source: '民用航空法', content: '飞行活动应当遵守空域管理规定。' }
  const raw = {
    answer: '应遵守空域管理规定。',
    references: [reference],
    citations: [{ ...reference }]
  }
  const result = await queryWithData(raw)

  assert.equal(result.answer, raw.answer)
  assert.deepEqual(JSON.parse(JSON.stringify(result.references)), [reference])
  assert.strictEqual(result.raw, raw)
})
