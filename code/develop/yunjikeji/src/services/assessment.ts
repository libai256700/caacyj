import {
  fetchAnswerCard,
  fetchAppPracticeQuestion,
  fetchCatalogBatchDetail,
  fetchPracticeTopics,
  fetchPracticeRecordDetail,
  fetchPracticeRecords,
  startAppPractice,
  submitAppPracticeAnswer,
  type PracticeAnswerResult,
  type PracticeQuestion,
  type PracticeRecordDetail,
  type PracticeRecord,
  type PracticeStartMode
} from './practice'
import { getYjAppApiBaseUrl } from './apiBase'
import { buildAuthHeader, handleUnauthorizedResponse } from './request'

export type AssessmentOption = {
  id: string
  label: string
  content: string
}

export type AssessmentQuestion = {
  id: string
  type: string
  title: string
  stem: string
  score: number
  index: number
  options: AssessmentOption[]
  isRequired: boolean
  stepName?: string
  stepStatus?: boolean
}

export type AssessmentAnswerSubmit = {
  questionId: string
  selectedOptionIds: string[]
}

export type AssessmentQuestionPage = {
  currentIndex: number
  totalQuestions: number
  question: AssessmentQuestion | null
  categoryName?: string
  savedAnswers?: Record<string, string[]>
}

export type AssessmentAnswerResult = {
  no: number
  questionId: string
  type: string
  question: string
  answer: string
  correct: string
  selectedOptionIds: string[]
  correctOptionIds: string[]
  correctFlag: boolean
  explanation: string
  stepName?: string
  stepStatus?: boolean
}

export type AssessmentSubmitSnapshot = {
  id: string
  sessionId?: string
  score: number
  level: string
  questionCount: number
  correctCount: number
  wrongCount: number
  summary: string
  suggestion: string
  reportHtml: string
  reportStatus?: string
  reportFailureReason?: string
  stepName?: string
  stepStatus?: boolean
  weakPoints: string[]
  answers: AssessmentAnswerResult[]
  finishedAt: string
}

export type AssessmentReport = AssessmentSubmitSnapshot

export type AssessmentRecord = {
  id: string
  score: number
  level: string
  questionCount: number
  correctCount: number
  wrongCount: number
  summary: string
  suggestion: string
  finishedAt: string
  timeRange: 'all' | 'today' | 'week' | 'month'
  answers: AssessmentAnswerResult[]
}

export type AssessmentResultStatus = {
  catalogBatchId: string
  recordId: string
  completed: boolean
  batchSaveStatus?: number
}

export type AssessmentRegenerateResult = {
  recordId: string
  reportStatus: string
}

const ASSESSMENT_PRACTICE_ID = 'uav-basic-001'
const ASSESSMENT_TOPIC_ID = 'assessment'
const ASSESSMENT_MODE: PracticeStartMode = 'assessment'

type AssessmentApiResponse<T> = {
  code?: number | string
  msg?: string
  message?: string
  data?: T
}

let assessmentPracticeId = ASSESSMENT_PRACTICE_ID
let assessmentSessionId = ''
let assessmentQuestions: AssessmentQuestion[] = []
let assessmentTotalQuestions = 0
let assessmentCategoryName = ''

const requestAssessment = <T>(path: string, method: 'GET' | 'POST') => new Promise<T>((resolve, reject) => {
  uni.request({
    url: `${getYjAppApiBaseUrl()}${path}`,
    method,
    header: buildAuthHeader(),
    success: (response) => {
      const body = response.data as AssessmentApiResponse<T>
      if (handleUnauthorizedResponse(body)) {
        reject(new Error(body.msg || body.message || '登录状态已过期，请重新登录'))
        return
      }
      if (response.statusCode >= 200 && response.statusCode < 300
        && (body.code === 0 || body.code === '0' || body.code === '00000') && body.data !== undefined) {
        resolve(body.data)
        return
      }
      reject(new Error(body.msg || body.message || '自测服务返回异常'))
    },
    fail: () => reject(new Error('自测服务暂不可用，请稍后重试'))
  })
})

const normalizeRequired = (value: unknown) => {
  if (value === undefined || value === null || value === '') {
    return true
  }
  if (value === false || value === 0) {
    return false
  }
  if (typeof value === 'string' && ['0', 'false', 'no', 'n'].includes(value.trim().toLowerCase())) {
    return false
  }
  return true
}

const normalizeQuestion = (question: PracticeQuestion, index: number): AssessmentQuestion => ({
  id: question.id,
  type: question.type,
  title: question.stem || question.title,
  stem: question.stem || question.title,
  score: question.score,
  index,
  options: question.options || [],
  isRequired: normalizeRequired(question.isRequired ?? (question as PracticeQuestion & { is_required?: unknown }).is_required),
  stepName: question.stepName,
  stepStatus: question.stepStatus
})

const normalizeIds = (ids: string[]) => Array.from(new Set(ids.map((id) => id.trim()).filter(Boolean)))

const findQuestion = (questionId: string) => assessmentQuestions.find((question) => question.id === questionId)

const buildSavedAssessmentAnswers = async (recordId: string) => {
  if (!recordId) {
    return {}
  }
  const detail = await fetchPracticeRecordDetail(recordId)
  return detail.answers.reduce<Record<string, string[]>>((result, answer) => {
    result[answer.questionId] = answer.selectedOptionIds || []
    return result
  }, {})
}

const resolveResumeQuestionIndex = async (recordId: string, fallbackIndex = 0) => {
  if (!recordId) {
    return Math.max(fallbackIndex, 0)
  }
  const answerCard = await fetchAnswerCard(recordId)
  const pendingIndex = [...answerCard.detail]
    .sort((left, right) => left.sortNo - right.sortNo)
    .findIndex((detail) => !detail.isCompleted)
  return pendingIndex >= 0 ? pendingIndex : Math.max(fallbackIndex, 0)
}

const optionLabels = (question: AssessmentQuestion | undefined, ids: string[]) => {
  if (!question) {
    return ids.join('、')
  }
  return ids
    .map((id) => question.options.find((option) => option.id === id)?.content || id)
    .filter(Boolean)
    .join('、')
}

const buildAnswerResult = (
  question: AssessmentQuestion | undefined,
  result: PracticeAnswerResult,
  no: number
): AssessmentAnswerResult => ({
  no,
  questionId: result.questionId,
  type: question?.type || '',
  question: question?.stem || question?.title || result.questionId,
  answer: optionLabels(question, result.selectedOptionIds || []),
  correct: optionLabels(question, result.correctOptionIds || []),
  selectedOptionIds: result.selectedOptionIds || [],
  correctOptionIds: result.correctOptionIds || [],
  correctFlag: result.correct,
  explanation: result.explanation || '',
  stepName: result.stepName || question?.stepName,
  stepStatus: result.stepStatus ?? question?.stepStatus
})

const buildAssessmentSubmitSnapshot = (
  answerResults: AssessmentAnswerResult[],
  recordId: string,
  evaluation?: PracticeAnswerResult
): AssessmentSubmitSnapshot => {
  const reportStatus = evaluation?.assessmentReportStatus || ''
  const summary = evaluation?.assessmentSummary
    || (reportStatus === 'PENDING' ? '个性化评测报告正在生成中。' : '本次个性化评测已完成。')
  const suggestion = evaluation?.assessmentSuggestion || '请查看完整报告了解评测结论与下一步建议。'

  return {
    id: recordId,
    sessionId: assessmentSessionId,
    score: 0,
    level: evaluation?.assessmentLevel || '个性化评测',
    questionCount: 0,
    correctCount: 0,
    wrongCount: 0,
    summary,
    suggestion,
    reportHtml: evaluation?.assessmentReportContent || '',
    reportStatus,
    reportFailureReason: evaluation?.assessmentReportFailureReason || '',
    stepName: evaluation?.stepName || answerResults.find((answer) => answer.stepName)?.stepName || '',
    stepStatus: evaluation?.stepStatus ?? answerResults.find((answer) => answer.stepStatus !== undefined)?.stepStatus,
    weakPoints: [],
    answers: answerResults,
    finishedAt: new Date().toISOString()
  }
}

const toAssessmentRecord = (record: PracticeRecord): AssessmentRecord => {
  return {
    id: record.id,
    score: 0,
    level: '个性化评测',
    questionCount: 0,
    correctCount: 0,
    wrongCount: 0,
    summary: '个性化评测已完成，可查看完整报告。',
    suggestion: '请查看完整报告了解评测结论与下一步建议。',
    finishedAt: record.practicedAt,
    timeRange: record.timeRange,
    answers: []
  }
}

type AssessmentReportDetail = Pick<PracticeRecordDetail, 'id'> & Partial<Pick<PracticeRecordDetail,
  | 'practicedAt'
  | 'assessmentTime'
  | 'selfReportContent'
  | 'assessmentReportStatus'
  | 'assessmentReportFailureReason'
  | 'stepName'
  | 'stepStatus'
  | 'answers'>>

const toAssessmentReport = (detail: AssessmentReportDetail): AssessmentReport => {
  const answers: AssessmentAnswerResult[] = (detail.answers || []).map((answer, index) => ({
    no: answer.no || index + 1,
    questionId: answer.questionId,
    type: answer.type,
    question: answer.question,
    answer: answer.answer,
    correct: answer.correct,
    selectedOptionIds: answer.selectedOptionIds || [],
    correctOptionIds: answer.correctOptionIds || [],
    correctFlag: answer.correctFlag,
    explanation: answer.explanation || '',
    stepName: answer.stepName,
    stepStatus: answer.stepStatus
  }))
  const selfReportContent = detail.selfReportContent?.trim()
  const reportStatus = detail.assessmentReportStatus?.trim().toUpperCase() || ''
  const reportFailureReason = detail.assessmentReportFailureReason?.trim() || ''
  const summary = reportStatus === 'SUCCESS'
    ? '个性化评测报告已生成，可查看完整报告。'
    : reportStatus === 'PENDING'
      ? '个性化评测报告正在生成中。'
      : reportStatus === 'FAILED'
        ? (reportFailureReason || '个性化评测报告生成失败。')
        : '本次个性化评测已完成。'
  const stepName = detail.stepName || answers.find((answer) => answer.stepName)?.stepName || ''
  const stepStatus = detail.stepStatus ?? answers.find((answer) => answer.stepStatus !== undefined)?.stepStatus

  return {
    id: detail.id,
    score: 0,
    level: '个性化评测',
    questionCount: 0,
    correctCount: 0,
    wrongCount: 0,
    summary,
    suggestion: '请查看完整报告了解评测结论与下一步建议。',
    reportHtml: selfReportContent || '',
    reportStatus,
    reportFailureReason,
    stepName,
    stepStatus,
    weakPoints: [],
    answers,
    finishedAt: detail.assessmentTime || detail.practicedAt || ''
  }
}

const toLightweightAssessmentReport = (detail: AssessmentReportDetail): AssessmentReport => {
  return toAssessmentReport({
    ...detail,
    practicedAt: detail.assessmentTime || '',
    answers: []
  })
}

const isAssessmentPracticeRecord = (record: PracticeRecord) =>
  record.category === ASSESSMENT_TOPIC_ID

export const fetchAssessmentQuestions = async () => {
  const assessmentTopics = await fetchPracticeTopics('', ASSESSMENT_MODE)
  assessmentCategoryName = assessmentTopics.find((topic) => topic.categoryName?.trim())?.categoryName?.trim() || ''

  const latestStatus = await fetchLatestAssessmentResultStatus()
  if (latestStatus?.completed === false && latestStatus.catalogBatchId && latestStatus.recordId) {
    const batch = await fetchCatalogBatchDetail(latestStatus.catalogBatchId)
    if (batch.completed === false && batch.practiceId && batch.sessionId && batch.recordId) {
      assessmentPracticeId = batch.practiceId || ASSESSMENT_PRACTICE_ID
      assessmentSessionId = batch.sessionId
      assessmentQuestions = []
      assessmentTotalQuestions = 0
      const [savedAnswers, resumeQuestionIndex] = await Promise.all([
        buildSavedAssessmentAnswers(batch.recordId),
        resolveResumeQuestionIndex(batch.recordId, batch.resumeQuestionIndex ?? 0)
      ])
      return {
        ...await fetchAssessmentQuestion(resumeQuestionIndex),
        savedAnswers
      }
    }
    throw new Error('未完成测评加载失败，请稍后重试')
  }

  const startResult = await startAppPractice(ASSESSMENT_PRACTICE_ID, ASSESSMENT_MODE)
  assessmentPracticeId = startResult.practiceId || ASSESSMENT_PRACTICE_ID
  assessmentSessionId = startResult.sessionId
  assessmentQuestions = []
  assessmentTotalQuestions = 0

  return fetchAssessmentQuestion(0)
}

export const hasCompletedAssessment = () =>
  requestAssessment<boolean>('/app-api/yj/practices/assessment-result/completed', 'GET')

export const fetchLatestAssessmentResultStatus = () =>
  requestAssessment<AssessmentResultStatus>('/app-api/yj/practices/assessment-result/latest-status', 'GET')

export const resetCompletedAssessment = () =>
  requestAssessment<boolean>('/app-api/yj/practices/assessment-result/reset', 'POST')

export const regenerateAssessmentReport = (recordId: string) =>
  requestAssessment<AssessmentRegenerateResult>(
    `/app-api/yj/practices/assessment-result/${encodeURIComponent(recordId)}/regenerate`,
    'POST'
  )

export const fetchAssessmentQuestion = async (index: number): Promise<AssessmentQuestionPage> => {
  if (!assessmentSessionId) {
    throw new Error('自测会话已失效，请重新开始自测')
  }

  const page = await fetchAppPracticeQuestion(assessmentPracticeId, assessmentSessionId, ASSESSMENT_MODE, index)
  const currentIndex = page.currentIndex ?? index
  const question = page.question ? normalizeQuestion(page.question, currentIndex) : null
  assessmentTotalQuestions = Math.max(page.totalQuestions || 0, 0)
  if (question) {
    assessmentQuestions[currentIndex] = question
  }
  return {
    currentIndex,
    totalQuestions: assessmentTotalQuestions,
    question,
    categoryName: assessmentCategoryName
  }
}

export const submitAssessmentAnswers = async (answers: AssessmentAnswerSubmit[]) => {
  if (!assessmentSessionId) {
    throw new Error('自测会话已失效，请重新开始自测')
  }

  const resultList: AssessmentAnswerResult[] = []
  let completedRecordId = ''
  let completedResult: PracticeAnswerResult | undefined
  for (const [index, answer] of answers.entries()) {
    const question = findQuestion(answer.questionId)
    const result = await submitAppPracticeAnswer(
      assessmentPracticeId,
      assessmentSessionId,
      answer.questionId,
      normalizeIds(answer.selectedOptionIds),
      question?.index ?? index
    )
    if (result.completed && result.recordId) {
      completedRecordId = result.recordId
      completedResult = result
    }
    resultList.push(buildAnswerResult(question, result, index + 1))
  }

  if (!completedRecordId) {
    throw new Error('自测报告生成失败，后端未返回报告记录 ID')
  }
  if (completedResult?.assessmentReportStatus === 'FAILED') {
    throw new Error(completedResult.assessmentReportFailureReason || '自测报告生成失败，请稍后重试')
  }

  const snapshot = buildAssessmentSubmitSnapshot(resultList, completedRecordId, completedResult)
  return snapshot
}

export const fetchAssessmentRecords = async () => {
  return (await fetchPracticeRecords()).filter(isAssessmentPracticeRecord).map(toAssessmentRecord)
}

export const fetchLatestAssessmentResult = async (): Promise<AssessmentReport | null> => {
  const records = await fetchAssessmentRecords()
  const record = records[0]
  if (!record) {
    return null
  }
  return fetchAssessmentResult(record.id)
}

export const fetchLatestSelfAssessmentReport = async (): Promise<AssessmentReport | null> => {
  const records = await fetchAssessmentRecords()
  const record = records[0]
  return record ? fetchSelfAssessmentReport(record.id) : null
}

export const fetchSelfAssessmentReport = async (recordId: string): Promise<AssessmentReport | null> => {
  if (!recordId) {
    return null
  }
  return requestAssessment<AssessmentReportDetail>(
    `/app-api/yj/practices/assessment-result/self/${encodeURIComponent(recordId)}`,
    'GET'
  ).then(toLightweightAssessmentReport)
}

export const fetchAssessmentResult = async (resultId: string): Promise<AssessmentReport | null> => {
  if (!resultId) {
    return null
  }
  return toAssessmentReport(await fetchPracticeRecordDetail(resultId))
}
