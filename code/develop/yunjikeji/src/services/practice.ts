import { getApiBaseUrl, getYjAppApiBaseUrl } from './apiBase'
import { buildAuthHeader, handleUnauthorizedResponse } from './request'

export type PracticeStartMode =
  | 'standard'
  | 'assessment'
  | 'wrongReview'
  | 'practice'
  | 'chapter-test'
  | 'theory-exam'
  | 'comprehensive-exam'
  | 'instructor-exam'

export type PracticeTopic = {
  id: string
  index: string
  title: string
  categoryName: string
  fieldType?: string
  sortNo?: number
  categoryStatus?: boolean
  questionCount: number
  totalScore: number
  wrongQuestionCount: number
}

export type PracticeStartPage = {
  id: string
  subject: string
  category: string
  paperNo: string
  title: string
  questionCount: number
  totalScore: number
  timeLimitMinutes: number
  gradingMode: string
  wrongQuestionCount: number
  topics?: PracticeTopic[]
}

export type PracticeStartResult = {
  practiceId: string
  sessionId: string
  catalogBatchId: string
  mode: PracticeStartMode
  recordId: string
  nextPage: string
  resumeQuestionIndex: number
  pendingSubmit: boolean
}

type PracticeStartResultResponse = {
  practiceId: string | number
  sessionId: string | number
  catalogBatchId?: string | number
  batchId?: string | number
  recordId: string | number
  resumeQuestionIndex?: number | string
  pendingSubmit?: boolean
  mode: string
  nextPage: string
}

export type PracticeCatalogBatchQuestionStat = {
  label: string
  count: number
}

export type PracticeCatalogBatchFirstQuestion = PracticeQuestion & {
  sortNo?: number
}

export type PracticeCatalogBatchDetail = {
  practiceId: string
  catalogBatchId: string
  recordId: string
  sessionId: string
  type: string
  catalogId: string
  categoryId: string
  sourceCategoryId: string
  categoryName: string
  total: number
  nextPage: string
  questionStats: PracticeCatalogBatchQuestionStat[]
  firstQuestion: PracticeCatalogBatchFirstQuestion | null
  totalScore?: number
  timeLimitMinutes?: number
  remainingSeconds?: number
  completed?: boolean
  pendingSubmit?: boolean
  resumeQuestionIndex?: number
  gradingMode?: string
}

type PracticeCatalogBatchDetailResponse = {
  practiceId: string | number
  catalogBatchId?: string | number
  batchId?: string | number
  recordId: string | number
  sessionId: string | number
  type?: string | number
  catalogId?: string | number
  categoryId?: string | number
  sourceCategoryId?: string | number
  categoryName?: string
  total?: number | string
  nextPage?: string
  questionStats?: unknown
  firstQuestion?: unknown
  totalScore?: number | string
  timeLimitMinutes?: number | string
  remainingSeconds?: number | string
  completed?: boolean
  pendingSubmit?: boolean
  resumeQuestionIndex?: number | string
  gradingMode?: string
}

export type PracticeAnswerCard = {
  total: number
  catalogId: string
  detail: Array<{
    exercisesBatchId: string
    isCompleted: boolean
    sortNo: number
  }>
}

export type PracticeStatistics = {
  practiceTotal: number
  answerTotal: number
  accuracy: number
  streakDays: number
  wrongTotal: number
}

export type PracticeRecord = {
  id: string
  title: string
  category: string
  categoryName?: string
  totalScore: number
  score: number
  correctCount: number
  wrongCount: number
  practicedAt: string
  timeRange: 'all' | 'today' | 'week' | 'month'
}

export type PracticeRecordAnswer = {
  no: number
  questionId: string
  type: string
  question: string
  selectedOptionIds: string[]
  answer: string
  correctOptionIds: string[]
  correct: string
  correctFlag: boolean
  explanation: string
  stepName?: string
  stepStatus?: boolean
}

export type PracticeRecordDetail = Omit<PracticeRecord, 'timeRange'> & {
  practicedAt: string
  assessmentTime?: string
  selfReportContent?: string
  assessmentReportStatus?: string
  assessmentReportFailureReason?: string
  stepName?: string
  stepStatus?: boolean
  answers: PracticeRecordAnswer[]
}

export type PracticeQuestionOption = {
  id: string
  label: string
  content: string
}

export type PracticeQuestion = {
  id: string
  exerciseId?: number
  videoAvailable?: boolean
  videoUrl?: string | null
  videoExpiresAt?: number | null
  type: string
  title: string
  stem: string
  score: number
  options: PracticeQuestionOption[]
  isRequired?: boolean
  stepName?: string
  stepStatus?: boolean
}

export type PracticeQuestionPage = {
  practiceId: string
  sessionId: string
  mode: PracticeStartMode
  currentIndex: number
  totalQuestions: number
  answeredCount: number
  correctCount: number
  progressPercent: number
  question: PracticeQuestion
}

export type PracticeQuestionListPage = {
  practiceId: string
  sessionId: string
  mode: PracticeStartMode
  currentIndex: number
  totalQuestions: number
  answeredCount: number
  correctCount: number
  progressPercent: number
  questions: PracticeQuestion[]
}

export type PracticeAnswerResult = {
  questionId: string
  selectedOptionId: string
  selectedOptionIds: string[]
  correctOptionId: string
  correctOptionIds: string[]
  correct: boolean
  explanation: string
  currentIndex: number
  nextQuestionIndex: number
  totalQuestions: number
  answeredCount: number
  correctCount: number
  progressPercent: number
  completed: boolean
  recordId?: string
  assessmentLevel?: string
  assessmentSummary?: string
  assessmentSuggestion?: string
  recommendDirection?: string
  weakPoints?: string[]
  assessmentReportContent?: string
  assessmentReportStatus?: string
  assessmentReportFailureReason?: string
  stepName?: string
  stepStatus?: boolean
}

export type AiAnswerSection = {
  title: string
  content: string
}

export type AiKnowledgeReference = {
  source: string
  content: string
}

export type AiCenterHistoryItem = {
  id: string
  question: string
  answer: string
  createTime: string
}

export type AiAnswer = {
  practiceId: string
  sessionId: string
  mode: PracticeStartMode
  question: PracticeQuestion
  selectedOptionId: string
  correctOptionId: string
  standardExplanation: string
  sections: AiAnswerSection[]
  references: AiKnowledgeReference[]
}

export type AiFollowUp = {
  questionId: string
  prompt: string
  answer: string
  references: AiKnowledgeReference[]
}

export type AiAnswerStreamEvent =
  | {
      type: 'context'
      answer: AiAnswer
    }
  | {
      type: 'references'
      references: AiKnowledgeReference[]
    }
  | {
      type: 'delta'
      content: string
    }
  | {
      type: 'done'
    }
  | {
      type: 'error'
      message: string
    }

export type AiFollowUpStreamEvent =
  | {
      type: 'references'
      references: AiKnowledgeReference[]
    }
  | {
      type: 'delta'
      content: string
    }
  | {
      type: 'done'
    }
  | {
      type: 'error'
      message: string
    }

export type KnowledgeQueryResult = {
  answer: string
  references: AiKnowledgeReference[]
  raw: unknown
}

export type KnowledgeQuerySource = 'ai_assistant' | 'practice_ai_answer'

type ApiResponse<T> = {
  code: number | string
  msg?: string
  message?: string
  data: T
  timestamp?: string
}

const buildPracticeUrl = (url: string) => `${getApiBaseUrl()}${url}`
const buildYjAppPracticeUrl = (url: string) => `${getYjAppApiBaseUrl()}${url}`
const isSuccessCode = (code: number | string | undefined) => code === 0 || code === '0' || code === '00000'
export const DEFAULT_PRACTICE_ID = 'uav-basic-001'
export const normalizeAppServiceErrorMessage = (message: string, fallback: string) => {
  const normalizedMessage = message.trim()
  if (!normalizedMessage) {
    return fallback
  }
  const lowerMessage = normalizedMessage.toLowerCase()
  if (
    lowerMessage.includes('connection refused') ||
    lowerMessage.includes('connectexception') ||
    lowerMessage.includes('i/o error on get request') ||
    normalizedMessage.includes('127.0.0.1:5001')
  ) {
    return '知识库服务暂不可用，请稍后重试'
  }
  if (lowerMessage.includes('student is not bound to a tenant')) {
    return '请先绑定企业，绑定成功后再进入练习中心'
  }
  return normalizedMessage
}
const readPracticeErrorMessage = (body: ApiResponse<unknown> | undefined, fallback: string) => {
  const message = body?.msg || body?.message || ''
  return normalizeAppServiceErrorMessage(message, fallback)
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const normalizeStringValue = (value: unknown) => {
  if (typeof value === 'string') {
    return value.trim()
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }
  return ''
}

const normalizeNumberValue = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return undefined
}

const normalizePracticeMode = (value: unknown): PracticeStartMode => {
  const normalized = normalizeStringValue(value)
  switch (normalized.toUpperCase()) {
    case 'ASSESSMENT':
      return 'assessment'
    case 'PRACTICE':
      return 'practice'
    case 'CHAPTER_TEST':
    case 'RANDOM_EXAM':
      return 'chapter-test'
    case 'THEORY_EXAM':
      return 'theory-exam'
    case 'COMPREHENSIVE_EXAM':
      return 'comprehensive-exam'
    case 'INSTRUCTOR_EXAM':
      return 'instructor-exam'
    default:
      return normalized === 'wrongReview' ? 'wrongReview' : 'standard'
  }
}

const firstStringField = (record: Record<string, unknown>, fields: string[]) => {
  for (const field of fields) {
    const value = record[field]
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
      return String(value)
    }
  }
  return ''
}

const collectTextValues = (value: unknown, depth = 0): string[] => {
  if (depth > 4 || value === null || value === undefined) {
    return []
  }
  if (typeof value === 'string') {
    const text = value.trim()
    return text ? [text] : []
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return [String(value)]
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectTextValues(item, depth + 1))
  }
  if (!isRecord(value)) {
    return []
  }

  const ignoredFields = new Set(['id', 'score', 'similarity', 'distance', 'createTime', 'updateTime'])
  return Object.entries(value)
    .filter(([key]) => !ignoredFields.has(key))
    .flatMap(([, item]) => collectTextValues(item, depth + 1))
}

const extractKnowledgeReferences = (value: unknown): AiKnowledgeReference[] => {
  const containers: unknown[] = []
  const enqueue = (candidate: unknown) => {
    if (Array.isArray(candidate)) {
      containers.push(...candidate)
    } else if (candidate !== undefined && candidate !== null) {
      containers.push(candidate)
    }
  }

  if (isRecord(value)) {
    enqueue(value.references)
    enqueue(value.citations)
    enqueue(value.segments)
    enqueue(value.records)
    enqueue(value.list)
    enqueue(value.result)
    enqueue(value.results)
    enqueue(value.items)
  }

  const unique = new Map<string, AiKnowledgeReference>()
  containers.forEach((item, index) => {
    if (!isRecord(item)) {
      return
    }
    const source = firstStringField(item, [
      'source',
      'documentName',
      'docName',
      'fileName',
      'knowledgeName',
      'title',
      'name'
    ]) || `知识库命中 ${index + 1}`
    const content = firstStringField(item, [
      'content',
      'text',
      'answer',
      'summary',
      'segmentContent',
      'chunkContent',
      'paragraph'
    ])
    if (!content) {
      return
    }
    const key = `${source}\n${content}`
    if (!unique.has(key)) {
      unique.set(key, { source, content })
    }
  })
  return Array.from(unique.values())
}

const normalizeKnowledgeQueryResult = (raw: unknown, query: string): KnowledgeQueryResult => {
  const data = isRecord(raw) && 'data' in raw ? raw.data : raw
  const direct = isRecord(data)
    ? firstStringField(data, ['answer', 'content', 'result', 'text', 'message', 'summary'])
    : ''
  const references = extractKnowledgeReferences(data)
  const fallbackText = collectTextValues(data)
    .filter((text) => text !== direct)
    .slice(0, 8)
    .join('\n\n')
  const answer = (direct || fallbackText).trim()

  return {
    answer: answer || `未检索到与“${query}”相关的知识库内容。`,
    references,
    raw
  }
}

const PRACTICE_ANSWER_PAGE = '/pages/practice/answer'
const DEFAULT_SUBJECT = '无人机驾驶员理论'
const DEFAULT_CATEGORY = '全部题库'
const DEFAULT_PAPER_NO = 'UAV-THEORY-LIVE'
const DEFAULT_TITLE = '无人机题库练习'
const DEFAULT_TIME_LIMIT_MINUTES = 45
const DEFAULT_GRADING_MODE = '系统阅卷'

const normalizePracticeNextPage = (nextPage: string) => {
  const normalized = nextPage.startsWith('/') ? nextPage : `/${nextPage}`
  if (normalized === '/pages/answer/index') {
    return PRACTICE_ANSWER_PAGE
  }
  return normalized || PRACTICE_ANSWER_PAGE
}

const normalizePracticeQuestion = (question: unknown): PracticeCatalogBatchFirstQuestion | null => {
  if (!isRecord(question)) {
    return null
  }
  return {
    id: normalizeStringValue(question.id),
    type: normalizeStringValue(question.type),
    title: normalizeStringValue(question.title),
    stem: normalizeStringValue(question.stem),
    score: normalizeNumberValue(question.score) ?? 0,
    sortNo: normalizeNumberValue(question.sortNo),
    options: Array.isArray(question.options)
      ? question.options
        .filter(isRecord)
        .map((option) => ({
          id: normalizeStringValue(option.id),
          label: normalizeStringValue(option.label),
          content: normalizeStringValue(option.content)
        }))
      : []
  }
}

const normalizeQuestionStats = (questionStats: unknown): PracticeCatalogBatchQuestionStat[] => {
  if (Array.isArray(questionStats)) {
    return questionStats
      .filter(isRecord)
      .map((item) => ({
        label:
          normalizeStringValue(item.label)
          || normalizeStringValue(item.type)
          || normalizeStringValue(item.questionType),
        count: normalizeNumberValue(item.count) ?? normalizeNumberValue(item.total) ?? 0
      }))
      .filter((item) => item.label && item.count >= 0)
  }

  if (!isRecord(questionStats)) {
    return []
  }

  return Object.entries(questionStats)
    .map(([label, count]) => ({
      label,
      count: normalizeNumberValue(count) ?? 0
    }))
    .filter((item) => item.label && item.count >= 0)
}

const normalizePracticeStartResult = (result: PracticeStartResultResponse): PracticeStartResult => ({
  practiceId: normalizeStringValue(result.practiceId),
  sessionId: normalizeStringValue(result.sessionId),
  catalogBatchId: normalizeStringValue(result.catalogBatchId ?? result.batchId),
  recordId: normalizeStringValue(result.recordId),
  resumeQuestionIndex: normalizeNumberValue(result.resumeQuestionIndex) ?? 0,
  pendingSubmit: result.pendingSubmit === true,
  mode: normalizePracticeMode(result.mode),
  nextPage: normalizePracticeNextPage(normalizeStringValue(result.nextPage))
})

const normalizePracticeQuestionPage = (result: PracticeQuestionPage): PracticeQuestionPage => ({
  ...result,
  practiceId: normalizeStringValue(result.practiceId),
  sessionId: normalizeStringValue(result.sessionId),
  mode: normalizePracticeMode(result.mode)
})

const normalizeCatalogBatchDetail = (result: PracticeCatalogBatchDetailResponse): PracticeCatalogBatchDetail => ({
  practiceId: normalizeStringValue(result.practiceId),
  catalogBatchId: normalizeStringValue(result.catalogBatchId ?? result.batchId),
  recordId: normalizeStringValue(result.recordId),
  sessionId: normalizeStringValue(result.sessionId),
  type: normalizeStringValue(result.type),
  catalogId: normalizeStringValue(result.catalogId),
  categoryId: normalizeStringValue(result.categoryId ?? result.sourceCategoryId),
  sourceCategoryId: normalizeStringValue(result.sourceCategoryId),
  categoryName: normalizeStringValue(result.categoryName),
  total: normalizeNumberValue(result.total) ?? 0,
  nextPage: normalizePracticeNextPage(normalizeStringValue(result.nextPage)),
  questionStats: normalizeQuestionStats(result.questionStats),
  firstQuestion: normalizePracticeQuestion(result.firstQuestion),
  totalScore: normalizeNumberValue(result.totalScore),
  timeLimitMinutes: normalizeNumberValue(result.timeLimitMinutes),
  remainingSeconds: normalizeNumberValue(result.remainingSeconds),
  completed: result.completed === true,
  pendingSubmit: result.pendingSubmit === true,
  resumeQuestionIndex: normalizeNumberValue(result.resumeQuestionIndex) ?? undefined,
  gradingMode: normalizeStringValue(result.gradingMode) || undefined
})

const normalizeAnswerCard = (result: PracticeAnswerCard): PracticeAnswerCard => ({
  total: normalizeNumberValue(result.total) ?? 0,
  catalogId: normalizeStringValue(result.catalogId),
  detail: Array.isArray(result.detail)
    ? result.detail.map((item) => ({
      exercisesBatchId: normalizeStringValue(item.exercisesBatchId),
      isCompleted: Boolean(item.isCompleted),
      sortNo: normalizeNumberValue(item.sortNo) ?? 0
    }))
    : []
})

const requestPractice = <T>(url: string, method: 'GET' | 'POST', data?: Record<string, unknown>) => {
  return new Promise<T>((resolve, reject) => {
    uni.request({
      url: buildPracticeUrl(url),
      method,
      header: {
        ...buildAuthHeader()
      },
      data,
      success: (response) => {
        const body = response.data as ApiResponse<T>
        if (handleUnauthorizedResponse(body)) {
          reject(new Error(readPracticeErrorMessage(body, '登录状态已过期，请重新登录')))
          return
        }
        if (response.statusCode >= 200 && response.statusCode < 300 && isSuccessCode(body?.code) && body.data !== undefined) {
          resolve(body.data)
          return
        }
        reject(new Error(readPracticeErrorMessage(body, '练习服务返回异常')))
      },
      fail: () => {
        reject(new Error('练习服务暂不可用，请稍后重试'))
      }
    })
  })
}

const requestYjAppPractice = <T>(url: string, method: 'GET' | 'POST', data?: Record<string, unknown>) => {
  const localQuestionBase = import.meta.env.VITE_LOCAL_QUESTION_API_BASE_URL?.trim().replace(/\/$/, '')
  const isQuestionRead = method === 'GET'
    && /^\/app-api\/yj\/practices\/[^/]+\/sessions\/[^/]+\/question\?/.test(url)
  const requestUrl = localQuestionBase && isQuestionRead
    ? `${localQuestionBase}${url.replace('/yj/practices/', '/yj/local-practice/')}`
    : buildYjAppPracticeUrl(url)
  return new Promise<T>((resolve, reject) => {
    uni.request({
      url: requestUrl,
      method,
      header: {
        ...buildAuthHeader()
      },
      data,
      success: (response) => {
        const body = response.data as ApiResponse<T>
        if (handleUnauthorizedResponse(body)) {
          reject(new Error(readPracticeErrorMessage(body, '登录状态已过期，请重新登录')))
          return
        }
        if (response.statusCode >= 200 && response.statusCode < 300 && isSuccessCode(body?.code) && body.data !== undefined) {
          resolve(body.data)
          return
        }
        reject(new Error(readPracticeErrorMessage(body, '练习服务返回异常')))
      },
      fail: () => {
        reject(new Error('练习服务暂不可用，请稍后重试'))
      }
    })
  })
}

const requestYjAppKnowledge = (url: string) => {
  return new Promise<unknown>((resolve, reject) => {
    uni.request({
      url: buildYjAppPracticeUrl(url),
      method: 'GET',
      header: {
        ...buildAuthHeader()
      },
      success: (response) => {
        const body = response.data as ApiResponse<unknown> | unknown
        if (isRecord(body) && handleUnauthorizedResponse(body)) {
          reject(new Error(readPracticeErrorMessage(body as ApiResponse<unknown>, '登录状态已过期，请重新登录')))
          return
        }
        if (response.statusCode < 200 || response.statusCode >= 300) {
          reject(new Error(isRecord(body) ? readPracticeErrorMessage(body as ApiResponse<unknown>, '知识库服务返回异常') : '知识库服务返回异常'))
          return
        }
        if (isRecord(body) && 'code' in body) {
          const wrapped = body as ApiResponse<unknown>
          if (isSuccessCode(wrapped.code)) {
            resolve(wrapped.data === undefined ? wrapped : wrapped.data)
            return
          }
          reject(new Error(readPracticeErrorMessage(wrapped, '知识库服务返回异常')))
          return
        }
        resolve(body)
      },
      fail: () => {
        reject(new Error('知识库服务暂不可用，请稍后重试'))
      }
    })
  })
}

const parseErrorMessage = async (response: Response) => {
  const text = await response.text()
  if (!text) {
    return response.statusText || '练习服务返回异常'
  }
  try {
    const body = JSON.parse(text) as Partial<ApiResponse<unknown>>
    if (handleUnauthorizedResponse(body)) {
      return body.msg || body.message || '登录状态已过期，请重新登录'
    }
    if (typeof body.message === 'string' && body.message.trim()) {
      return body.message
    }
  } catch (error) {
    void error
  }
  return text
}

const parseSseBlock = <T>(block: string): T | null => {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .join('\n')

  if (!data) {
    return null
  }

  return JSON.parse(data) as T
}

const streamPractice = async <T>(
  url: string,
  method: 'GET' | 'POST',
  onEvent: (event: T) => void,
  options?: {
    data?: Record<string, unknown>
    signal?: AbortSignal
  }
) => {
  if (typeof fetch !== 'function' || typeof TextDecoder === 'undefined') {
    throw new Error('当前环境暂不支持流式AI解答')
  }

  const headers: Record<string, string> = {
    ...buildAuthHeader(),
    Accept: 'text/event-stream'
  }

  let body: string | undefined
  if (method === 'POST') {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options?.data ?? {})
  }

  const response = await fetch(buildPracticeUrl(url), {
    method,
    headers,
    body,
    signal: options?.signal
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  if (!response.body) {
    throw new Error('AI流式响应为空')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const flushBuffer = (force = false) => {
    const splitter = /\r?\n\r?\n/g
    let match = splitter.exec(buffer)
    let lastIndex = 0
    while (match) {
      const block = buffer.slice(lastIndex, match.index)
      lastIndex = match.index + match[0].length
      const event = parseSseBlock<T>(block)
      if (event) {
        onEvent(event)
      }
      match = splitter.exec(buffer)
    }

    if (force && buffer.slice(lastIndex).trim()) {
      const event = parseSseBlock<T>(buffer.slice(lastIndex))
      if (event) {
        onEvent(event)
      }
      buffer = ''
      return
    }

    buffer = buffer.slice(lastIndex)
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      buffer += decoder.decode()
      flushBuffer(true)
      break
    }
    buffer += decoder.decode(value, { stream: true })
    flushBuffer()
  }
}

export const fetchPracticeTopics = (topicId = '', mode: PracticeStartMode = 'standard') => {
  const params = `mode=${mode}${topicId ? `&topicId=${encodeURIComponent(topicId)}` : ''}`
  return requestYjAppPractice<PracticeTopic[]>(`/app-api/yj/practices/current?${params}`, 'GET')
}

export const toPracticeStartPage = (topics: PracticeTopic[], topicId = ''): PracticeStartPage => {
  const selectedTopic = topicId
    ? topics.find((topic) => topic.id === topicId || topic.fieldType === topicId || topic.categoryName === topicId || topic.title === topicId)
    : undefined
  const scopedTopics = selectedTopic ? [selectedTopic] : topics
  const questionCount = scopedTopics.reduce((total, topic) => total + (topic.questionCount || 0), 0)
  const totalScore = scopedTopics.reduce((total, topic) => total + (topic.totalScore || 0), 0)

  return {
    id: DEFAULT_PRACTICE_ID,
    subject: DEFAULT_SUBJECT,
    category: selectedTopic?.categoryName || selectedTopic?.title || DEFAULT_CATEGORY,
    paperNo: DEFAULT_PAPER_NO,
    title: DEFAULT_TITLE,
    questionCount,
    totalScore,
    timeLimitMinutes: DEFAULT_TIME_LIMIT_MINUTES,
    gradingMode: DEFAULT_GRADING_MODE,
    wrongQuestionCount: scopedTopics.reduce((total, topic) => total + (topic.wrongQuestionCount || 0), 0),
    topics
  }
}

export const fetchPracticeStartPage = async (topicId = '', mode: PracticeStartMode = 'standard') => {
  return fetchPracticeTopics(topicId, mode).then((topics) => toPracticeStartPage(topics, topicId))
}

export const fetchPracticeStatistics = () => {
  return requestYjAppPractice<PracticeStatistics>('/app-api/yj/practices/statistics', 'GET')
}

export const fetchPracticeRecords = () => {
  return requestYjAppPractice<PracticeRecord[]>('/app-api/yj/practices/records', 'GET')
}

export const fetchAssessmentResultCompleted = () => {
  return requestYjAppPractice<boolean>('/app-api/yj/practices/assessment-result/completed', 'GET')
}

export const queryKnowledge = async (query: string, source: KnowledgeQuerySource = 'ai_assistant') => {
  const normalizedQuery = query.trim()
  if (!normalizedQuery) {
    throw new Error('请输入需要查询的知识点')
  }
  const queryForRequest = normalizedQuery.length > 1200 ? normalizedQuery.slice(0, 1200) : normalizedQuery
  const params = [
    `q=${encodeURIComponent(queryForRequest)}`,
    `source=${encodeURIComponent(source)}`
  ].join('&')
  const result = await requestYjAppKnowledge(`/app-api/yj/knowledge/query?${params}`)
  return normalizeKnowledgeQueryResult(result, queryForRequest)
}

export const fetchAiCenterHistory = (limit = 20) => {
  return requestYjAppPractice<AiCenterHistoryItem[]>(
    `/app-api/yj/ai-center/history?limit=${encodeURIComponent(String(limit))}`,
    'GET'
  )
}

export const fetchPracticeRecordDetail = (recordId: string) => {
  return requestYjAppPractice<PracticeRecordDetail>(
    `/app-api/yj/practices/records/${encodeURIComponent(recordId)}`,
    'GET'
  )
}

export const startPractice = (practiceId: string, mode: PracticeStartMode, topicId = '') => {
  if (mode === 'practice') {
    return startPracticeModeBatch(practiceId, topicId)
  }
  if (mode === 'chapter-test') {
    return startChapterTestBatch(practiceId, topicId)
  }
  if (mode === 'theory-exam') {
    return startTheoryExamBatch(practiceId)
  }
  if (mode === 'comprehensive-exam') {
    return startComprehensiveExamBatch(practiceId)
  }
  if (mode === 'instructor-exam') {
    return startInstructorExamBatch(practiceId)
  }
  return startAppPractice(practiceId, mode, topicId)
}

export const startAppPractice = (practiceId: string, mode: PracticeStartMode, topicId = '') => {
  const normalizedTopicId = mode === 'assessment' ? '' : topicId
  const params = `mode=${mode}${normalizedTopicId ? `&topicId=${encodeURIComponent(normalizedTopicId)}` : ''}`
  return requestYjAppPractice<PracticeStartResultResponse>(
    `/app-api/yj/practices/${encodeURIComponent(practiceId)}/start?${params}`,
    'POST'
  ).then(normalizePracticeStartResult)
}

export const startPracticeModeBatch = (practiceId: string, topicId: string) => {
  return requestYjAppPractice<PracticeStartResultResponse>(
    `/app-api/yj/practices/${encodeURIComponent(practiceId)}/start/practice?topicId=${encodeURIComponent(topicId)}`,
    'POST'
  ).then(normalizePracticeStartResult)
}

export const startChapterTestBatch = (practiceId: string, topicId: string) => {
  return requestYjAppPractice<PracticeStartResultResponse>(
    `/app-api/yj/practices/${encodeURIComponent(practiceId)}/start/chapter-test?topicId=${encodeURIComponent(topicId)}`,
    'POST'
  ).then(normalizePracticeStartResult)
}

export const startTheoryExamBatch = (practiceId: string) => {
  return requestYjAppPractice<PracticeStartResultResponse>(
    `/app-api/yj/practices/${encodeURIComponent(practiceId)}/start/theory-exam`,
    'POST'
  ).then(normalizePracticeStartResult)
}

export const startComprehensiveExamBatch = (practiceId: string) => {
  return requestYjAppPractice<PracticeStartResultResponse>(
    `/app-api/yj/practices/${encodeURIComponent(practiceId)}/start/comprehensive-exam`,
    'POST'
  ).then(normalizePracticeStartResult)
}

export const startInstructorExamBatch = (practiceId: string) => {
  return requestYjAppPractice<PracticeStartResultResponse>(
    `/app-api/yj/practices/${encodeURIComponent(practiceId)}/start/instructor-exam`,
    'POST'
  ).then(normalizePracticeStartResult)
}

export const fetchCatalogBatchDetail = (catalogBatchId: string) => {
  return requestYjAppPractice<PracticeCatalogBatchDetailResponse>(
    `/app-api/yj/practices/catalog-batches/${encodeURIComponent(catalogBatchId)}`,
    'GET'
  ).then(normalizeCatalogBatchDetail)
}

export const fetchLatestPracticeCatalogBatchDetail = (type: number, mode: 'practice' | 'chapter-test') => {
  return requestYjAppPractice<PracticeCatalogBatchDetailResponse | null>(
    `/app-api/yj/practices/catalog-batches/latest?type=${encodeURIComponent(String(type))}&mode=${encodeURIComponent(mode)}`,
    'GET'
  ).then((result) => (result ? normalizeCatalogBatchDetail(result) : null))
}

export const fetchAnswerCard = (recordId: string) => {
  return requestYjAppPractice<PracticeAnswerCard>(
    `/app-api/yj/practices/records/${encodeURIComponent(recordId)}/answer-card`,
    'GET'
  ).then(normalizeAnswerCard)
}

export const fetchPracticeQuestion = (
  practiceId: string,
  sessionId: string,
  mode: PracticeStartMode,
  index: number
) => {
  return fetchAppPracticeQuestion(practiceId, sessionId, mode, index)
}

export const fetchAppPracticeQuestion = (
  practiceId: string,
  sessionId: string,
  mode: PracticeStartMode,
  index: number
) => {
  const params = `mode=${mode}&index=${index}`
  return requestYjAppPractice<PracticeQuestionPage>(
    `/app-api/yj/practices/${encodeURIComponent(practiceId)}/sessions/${encodeURIComponent(sessionId)}/question?${params}`,
    'GET'
  ).then(normalizePracticeQuestionPage)
}

export const closeIncompleteExamBatches = () => {
  return requestYjAppPractice<number>('/app-api/yj/practices/exam-batches/close-incomplete', 'POST')
}

export const submitPracticeAnswer = (
  practiceId: string,
  sessionId: string,
  questionId: string,
  selectedOptionIds: string[],
  currentIndex: number
) => {
  return submitAppPracticeAnswer(practiceId, sessionId, questionId, selectedOptionIds, currentIndex)
}

export const submitAppPracticeAnswer = (
  practiceId: string,
  sessionId: string,
  questionId: string,
  selectedOptionIds: string[],
  currentIndex: number
) => {
  const normalizedSelectedOptionIds = Array.from(new Set(selectedOptionIds.filter(Boolean)))
  return requestYjAppPractice<PracticeAnswerResult>(
    `/app-api/yj/practices/${encodeURIComponent(practiceId)}/sessions/${encodeURIComponent(sessionId)}/answers`,
    'POST',
    {
      questionId,
      selectedOptionId: normalizedSelectedOptionIds[0] || '',
      selectedOptionIds: normalizedSelectedOptionIds,
      currentIndex
    }
  )
}

export const fetchAiAnswer = (
  practiceId: string,
  sessionId: string,
  mode: PracticeStartMode,
  questionId: string,
  selectedOptionId: string
) => {
  const params = `mode=${mode}&questionId=${encodeURIComponent(questionId)}&selectedOptionId=${encodeURIComponent(selectedOptionId)}`
  return requestPractice<AiAnswer>(
    `/api/practices/${encodeURIComponent(practiceId)}/sessions/${encodeURIComponent(sessionId)}/ai-answer?${params}`,
    'GET'
  )
}

export const streamAiAnswer = (
  practiceId: string,
  sessionId: string,
  mode: PracticeStartMode,
  questionId: string,
  selectedOptionId: string,
  onEvent: (event: AiAnswerStreamEvent) => void,
  signal?: AbortSignal
) => {
  const params = `mode=${mode}&questionId=${encodeURIComponent(questionId)}&selectedOptionId=${encodeURIComponent(selectedOptionId)}`
  return streamPractice<AiAnswerStreamEvent>(
    `/api/practices/${encodeURIComponent(practiceId)}/sessions/${encodeURIComponent(sessionId)}/ai-answer/stream?${params}`,
    'GET',
    onEvent,
    { signal }
  )
}

export const submitAiFollowUp = (
  practiceId: string,
  sessionId: string,
  questionId: string,
  selectedOptionId: string,
  prompt: string
) => {
  return requestPractice<AiFollowUp>(
    `/api/practices/${encodeURIComponent(practiceId)}/sessions/${encodeURIComponent(sessionId)}/ai-answer/follow-ups`,
    'POST',
    {
      questionId,
      selectedOptionId,
      prompt
    }
  )
}

export const streamAiFollowUp = (
  practiceId: string,
  sessionId: string,
  questionId: string,
  selectedOptionId: string,
  prompt: string,
  onEvent: (event: AiFollowUpStreamEvent) => void,
  signal?: AbortSignal
) => {
  return streamPractice<AiFollowUpStreamEvent>(
    `/api/practices/${encodeURIComponent(practiceId)}/sessions/${encodeURIComponent(sessionId)}/ai-answer/follow-ups/stream`,
    'POST',
    onEvent,
    {
      data: {
        questionId,
        selectedOptionId,
        prompt
      },
      signal
    }
  )
}
