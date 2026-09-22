import request from '@/config/axios'

export interface HomeDateRangeReqVO {
  startDate: string
  endDate: string
}

export type HomeSummaryRespVO = Record<string, unknown>

export interface HomeTrendPoint {
  date?: string
  day?: string
  statDate?: string
  name?: string
  value?: number
  count?: number
  [key: string]: unknown
}

export type HomeTrendRespVO =
  | HomeTrendPoint[]
  | {
      dates?: string[]
      values?: number[]
      list?: HomeTrendPoint[]
      items?: HomeTrendPoint[]
      records?: HomeTrendPoint[]
      data?: HomeTrendPoint[]
      [key: string]: unknown
    }

export type HomePracticeRespVO =
  | Record<string, unknown>
  | Array<{
      name?: string
      label?: string
      type?: string
      value?: number
      count?: number
      total?: number
      [key: string]: unknown
    }>

export type HomeMetricRespVO = number | Record<string, unknown>

export const HomeApi = {
  getSummary: async () => {
    return await request.get<HomeSummaryRespVO>({ url: '/chart/overview' })
  },

  getActiveUsersToday: async () => {
    return await request.get<HomeMetricRespVO>({ url: '/chart/active-users/today' })
  },

  getLoginsToday: async () => {
    return await request.get<HomeMetricRespVO>({ url: '/chart/logins/today' })
  },

  getLoginTrend: async (params: HomeDateRangeReqVO) => {
    return await request.get<HomeTrendRespVO>({ url: '/chart/logins/trend', params })
  },

  getRegistersToday: async () => {
    return await request.get<HomeMetricRespVO>({ url: '/chart/registers/today' })
  },

  getRegistersTotal: async () => {
    return await request.get<HomeMetricRespVO>({ url: '/chart/registers/total' })
  },

  getRegisterTrend: async (params: HomeDateRangeReqVO) => {
    return await request.get<HomeTrendRespVO>({ url: '/chart/registers/trend', params })
  },

  getKnowledgeCallsToday: async () => {
    return await request.get<HomeMetricRespVO>({ url: '/chart/knowledge-calls/today' })
  },

  getKnowledgeCallsTotal: async () => {
    return await request.get<HomeMetricRespVO>({ url: '/chart/knowledge-calls/total' })
  },

  getKnowledgeTrend: async (params: HomeDateRangeReqVO) => {
    return await request.get<HomeTrendRespVO>({ url: '/chart/knowledge-calls/trend', params })
  },

  getPractice: async () => {
    return await request.get<HomePracticeRespVO>({ url: '/chart/practice/stats' })
  },

  getPracticeTrend: async (params: HomeDateRangeReqVO) => {
    return await request.get<HomeTrendRespVO>({ url: '/chart/practice/trend', params })
  }
}
