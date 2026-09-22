import { getYjAppApiBaseUrl } from './apiBase'
import { buildAuthHeader, handleUnauthorizedResponse } from './request'

type ApiResponse<T> = {
  code: number | string
  msg?: string
  message?: string
  data: T
  timestamp?: string
}

export type KnowledgeReference = {
  source: string
  content: string
}

export type KnowledgeQueryResult = {
  answer: string
  references: KnowledgeReference[]
  raw: unknown
}

const isSuccessCode = (code: number | string | undefined) => code === 0 || code === '0' || code === '00000'

const readErrorMessage = (body: ApiResponse<unknown> | undefined, fallback: string) => {
  const message = body?.msg || body?.message || ''
  return message.trim() || fallback
}

const buildKnowledgeUrl = (query: string) =>
  `${getYjAppApiBaseUrl()}/app-api/yj/knowledge/query?q=${encodeURIComponent(query)}`

const compactText = (value: unknown): string => {
  if (typeof value === 'string') {
    return value.trim()
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return ''
}

const pickFirstText = (source: Record<string, unknown>, keys: string[]) => {
  for (const key of keys) {
    const value = compactText(source[key])
    if (value) {
      return value
    }
  }
  return ''
}

const normalizeReference = (item: unknown, index: number): KnowledgeReference | null => {
  if (typeof item === 'string') {
    const content = item.trim()
    return content ? { source: `知识库片段 ${index + 1}`, content } : null
  }
  if (!item || typeof item !== 'object') {
    return null
  }

  const source = item as Record<string, unknown>
  const content = pickFirstText(source, ['content', 'answer', 'text', 'segment', 'chunk', 'description', 'summary'])
  if (!content) {
    return null
  }

  return {
    source: pickFirstText(source, ['source', 'title', 'name', 'documentName', 'docName', 'fileName']) || `知识库片段 ${index + 1}`,
    content
  }
}

const normalizeReferences = (value: unknown): KnowledgeReference[] => {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .map((item, index) => normalizeReference(item, index))
    .filter((item): item is KnowledgeReference => Boolean(item))
}

const summarizeReferences = (references: KnowledgeReference[]) =>
  references
    .map((item, index) => `${index + 1}. ${item.content}`)
    .join('\n')

const normalizeKnowledgeResult = (data: unknown): KnowledgeQueryResult => {
  if (typeof data === 'string') {
    return {
      answer: data.trim(),
      references: [],
      raw: data
    }
  }

  if (Array.isArray(data)) {
    const references = normalizeReferences(data)
    return {
      answer: summarizeReferences(references),
      references,
      raw: data
    }
  }

  if (!data || typeof data !== 'object') {
    return {
      answer: '',
      references: [],
      raw: data
    }
  }

  const source = data as Record<string, unknown>
  const answer = pickFirstText(source, ['answer', 'content', 'text', 'result', 'message', 'summary'])
  const references = [
    normalizeReferences(source.references),
    normalizeReferences(source.segments),
    normalizeReferences(source.list),
    normalizeReferences(source.records),
    normalizeReferences(source.resultList)
  ].find((items) => items.length > 0) || []

  return {
    answer: answer || summarizeReferences(references),
    references,
    raw: data
  }
}

export const queryKnowledge = (query: string) => {
  return new Promise<KnowledgeQueryResult>((resolve, reject) => {
    uni.request({
      url: buildKnowledgeUrl(query),
      method: 'GET',
      header: {
        ...buildAuthHeader()
      },
      success: (response) => {
        const body = response.data as ApiResponse<unknown>
        if (handleUnauthorizedResponse(body)) {
          reject(new Error(readErrorMessage(body, '登录状态已过期，请重新登录')))
          return
        }
        if (response.statusCode >= 200 && response.statusCode < 300 && isSuccessCode(body?.code)) {
          resolve(normalizeKnowledgeResult(body.data))
          return
        }
        reject(new Error(readErrorMessage(body, '知识库查询失败')))
      },
      fail: () => {
        reject(new Error('知识库服务暂不可用，请稍后再试'))
      }
    })
  })
}
