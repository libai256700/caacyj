import { getYjAppApiBaseUrl } from './apiBase'
import { buildAuthHeader, handleUnauthorizedResponse } from './request'
import {
  fetchAppPracticeQuestion,
  submitAppPracticeAnswer,
  type PracticeAnswerResult,
  type PracticeQuestion,
  type PracticeRecordDetail
} from './practice'

export type CareerAssessmentOption = {
  id: string
  label: string
  content: string
}

export type CareerAssessmentQuestion = {
  id: string
  type: string
  title: string
  stem: string
  score: number
  index: number
  options: CareerAssessmentOption[]
  isRequired: boolean
  stepName?: string
}

export type CareerAssessmentQuestionPage = {
  currentIndex: number
  totalQuestions: number
  question: CareerAssessmentQuestion | null
}

export type CareerAssessmentQuestionLoad = CareerAssessmentQuestionPage & CareerAssessmentStartResult
export type CareerAssessmentAnswerSubmit = {
  questionId: string
  selectedOptionIds: string[]
  index: number
}

export type CareerAssessmentResultStatus = {
  catalogBatchId: string
  recordId: string
  completed: boolean
  batchSaveStatus?: number
}

export type CareerAssessmentReport = {
  id: string
  reportHtml: string
  reportStatus: string
  reportFailureReason: string
}

export type CareerAssessmentRegenerateResult = {
  recordId: string
  reportStatus: string
}

type ApiResponse<T> = {
  code?: number | string
  msg?: string
  message?: string
  data?: T
}

type StartResponse = {
  practiceId: string | number
  sessionId: string | number
  catalogBatchId?: string | number
  batchId?: string | number
  recordId: string | number
}

export type CareerAssessmentStartResult = {
  practiceId: string
  sessionId: string
  catalogBatchId: string
  recordId: string
}

const CAREER_PRACTICE_ID = 'uav-basic-001'
const CAREER_REQUEST_TIMEOUT_MS = 20000

const requestCareer = <T>(path: string, method: 'GET' | 'POST') => new Promise<T>((resolve, reject) => {
  uni.request({
    url: `${getYjAppApiBaseUrl()}${path}`,
    method,
    timeout: CAREER_REQUEST_TIMEOUT_MS,
    firstIpv4: true,
    header: buildAuthHeader(),
    success: (response) => {
      const body = response.data as ApiResponse<T>
      if (handleUnauthorizedResponse(body)) {
        reject(new Error(body.msg || body.message || '登录状态已过期，请重新登录'))
        return
      }
      if (response.statusCode >= 200 && response.statusCode < 300
        && (body.code === 0 || body.code === '0' || body.code === '00000') && body.data !== undefined) {
        resolve(body.data)
        return
      }
      reject(new Error(body.msg || body.message || '职业规划评测服务返回异常'))
    },
    fail: () => reject(new Error('职业规划评测服务暂不可用，请稍后重试'))
  })
})

const toString = (value: unknown) => value === undefined || value === null ? '' : String(value)

const normalizeRequired = (value: unknown) => !(
  value === false || value === 0 || value === '0' || value === 'false'
)

const normalizeQuestion = (question: PracticeQuestion, index: number): CareerAssessmentQuestion => ({
  id: question.id,
  type: question.type,
  title: question.stem || question.title,
  stem: question.stem || question.title,
  score: question.score,
  index,
  options: question.options || [],
  isRequired: normalizeRequired(question.isRequired ?? (question as PracticeQuestion & { is_required?: unknown }).is_required),
  stepName: question.stepName
})

const toStartResult = (result: StartResponse): CareerAssessmentStartResult => ({
  practiceId: toString(result.practiceId),
  sessionId: toString(result.sessionId),
  catalogBatchId: toString(result.catalogBatchId ?? result.batchId),
  recordId: toString(result.recordId)
})

export const startCareerAssessment = () => requestCareer<StartResponse>(
  `/app-api/yj/practices/${encodeURIComponent(CAREER_PRACTICE_ID)}/start/career-assessment`,
  'POST'
).then(toStartResult)

export const hasCompletedCareerAssessment = () =>
  requestCareer<boolean>('/app-api/yj/practices/assessment-result/career/completed', 'GET')

export const fetchLatestCareerAssessmentStatus = () =>
  requestCareer<CareerAssessmentResultStatus>('/app-api/yj/practices/assessment-result/career/latest-status', 'GET')

export const fetchLatestCareerAssessmentReportEntry = () =>
  requestCareer<CareerAssessmentResultStatus>('/app-api/yj/practices/assessment-result/career/report-entry', 'GET')

export const fetchCareerAssessmentQuestion = async (
  practiceId: string,
  sessionId: string,
  index: number
): Promise<CareerAssessmentQuestionPage> => {
  const page = await fetchAppPracticeQuestion(
    practiceId,
    sessionId,
    'assessment',
    index
  )
  const currentIndex = page.currentIndex ?? index
  return {
    currentIndex,
    totalQuestions: Math.max(page.totalQuestions || 0, 0),
    question: page.question ? normalizeQuestion(page.question, currentIndex) : null
  }
}

export const fetchCareerAssessmentQuestions = async (): Promise<CareerAssessmentQuestionLoad> => {
  const start = await startCareerAssessment()
  const firstPage = await fetchCareerAssessmentQuestion(start.practiceId, start.sessionId, 0)

  return {
    ...start,
    ...firstPage
  }
}

export const submitCareerAssessmentAnswer = (
  practiceId: string,
  sessionId: string,
  questionId: string,
  selectedOptionIds: string[],
  currentIndex: number
) => submitAppPracticeAnswer(practiceId, sessionId, questionId, Array.from(new Set(selectedOptionIds.filter(Boolean))), currentIndex)

export const submitCareerAssessmentAnswers = async (
  practiceId: string,
  sessionId: string,
  answers: CareerAssessmentAnswerSubmit[]
) => {
  let completedRecordId = ''
  let completedResult: PracticeAnswerResult | undefined
  for (const answer of answers) {
    const result = await submitCareerAssessmentAnswer(
      practiceId,
      sessionId,
      answer.questionId,
      answer.selectedOptionIds,
      answer.index
    )
    if (result.completed && result.recordId) {
      completedRecordId = result.recordId
      completedResult = result
    }
  }
  if (!completedRecordId) {
    throw new Error('职业规划报告生成失败，后端未返回报告记录 ID')
  }
  if (completedResult?.assessmentReportStatus === 'FAILED') {
    throw new Error(completedResult.assessmentReportFailureReason || '职业规划报告生成失败，请稍后重试')
  }
  return {
    recordId: completedRecordId,
    reportStatus: (completedResult?.assessmentReportStatus || '').trim().toUpperCase()
  }
}

const toCareerReport = (detail: PracticeRecordDetail): CareerAssessmentReport => ({
  id: detail.id,
  reportHtml: detail.selfReportContent || '',
  reportStatus: (detail.assessmentReportStatus || '').trim().toUpperCase(),
  reportFailureReason: detail.assessmentReportFailureReason || ''
})

export const fetchCareerAssessmentReport = (recordId: string) => requestCareer<PracticeRecordDetail>(
  `/app-api/yj/practices/assessment-result/career/${encodeURIComponent(recordId)}`,
  'GET'
).then(toCareerReport)

export const regenerateCareerAssessmentReport = (recordId: string) => requestCareer<PracticeAnswerResult>(
  `/app-api/yj/practices/assessment-result/career/${encodeURIComponent(recordId)}/regenerate`,
  'POST'
).then((result) => ({
  recordId: result.recordId || recordId,
  reportStatus: (result.assessmentReportStatus || '').trim().toUpperCase()
}))
