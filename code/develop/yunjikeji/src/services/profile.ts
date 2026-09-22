import { getApiBaseUrl } from './apiBase'
import { buildAuthHeader, handleUnauthorizedResponse } from './request'

export type ProfileSummary = {
  userId: number
  mobile: string
  nickname: string
  avatarUrl: string
  studentNo: string
  schoolName: string
  majorName: string
  roleLabel: string
  trainingDirection: string
}

export type LearningSummary = {
  courseTotal: number
  practiceTotal: number
  learningProgress: number
  currentCourseTitle: string
  currentCourseProgress: number
  continueDays: number
}

export type ResumeSummary = {
  resumeStatus: string
  completionPercent: number
  suggestionCount: number
  latestNote: string
}

export type ApplicationSummary = {
  id: number
  companyName: string
  positionName: string
  applicationStatus: string
  appliedAt: string
  note: string
}

export type InterviewSummary = {
  id: number
  companyName: string
  positionName: string
  interviewStatus: string
  interviewTime: string
  note: string
}

export type ProfileAggregate = {
  profile: ProfileSummary
  learning: LearningSummary
  resume: ResumeSummary
  applications: ApplicationSummary[]
  interviews: InterviewSummary[]
}

type ApiResponse<T> = {
  code: string
  message: string
  data: T
  timestamp: string
}

export const fetchProfileAggregate = (userId: number) => {
  return new Promise<ProfileAggregate>((resolve, reject) => {
    uni.request({
      url: `${getApiBaseUrl()}/api/profile/aggregate?userId=${encodeURIComponent(String(userId))}`,
      method: 'GET',
      header: {
        ...buildAuthHeader()
      },
      success: (response) => {
        const body = response.data as ApiResponse<ProfileAggregate>
        if (handleUnauthorizedResponse(body)) {
          reject(new Error(body?.message || '登录状态已过期，请重新登录'))
          return
        }
        if (response.statusCode >= 200 && response.statusCode < 300 && body?.code === '00000' && body.data) {
          resolve(body.data)
          return
        }
        reject(new Error(body?.message || '我的页内容加载失败'))
      },
      fail: () => {
        reject(new Error('我的页服务暂不可用，请稍后重试'))
      }
    })
  })
}
