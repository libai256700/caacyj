import request from '@/config/axios'

export type YjRecord = Record<string, any>

export interface YjPageResult {
  list: YjRecord[]
  total: number
}

export interface YjResourceMeta {
  resource: string
  tableName: string
  columns: string[]
}

export interface QwenPawAgentSyncResult {
  total: number
  created: number
  updated: number
  deleted: number
  skipped: number
  sourcePath: string
}

export interface QwenPawAgentCallResult {
  agentId: string
  sessionId: string
  content: string
  raw: YjRecord
}

export interface FeishuAuditRun {
  id: number
  taskId?: number
  folderToken: string
  status: string
  documentsSeen: number
  documentsProcessed: number
  documentsFailed: number
  jobsExtracted: number
  jobsCreated: number
  jobsUpdated: number
  jobsSkipped: number
  jobsFailed: number
  startedAt?: string
  finishedAt?: string
  errorMessage?: string
}

export interface FeishuDocumentPageResult {
  list: YjRecord[]
  total: number
}

const resourceEndpointMap: Record<string, string> = {
  'practice-category': '/practice/practice-category',
  'practice-exercise': '/practice/practice-exercises',
  'practice-exercise-answer': '/practice/practice-exercises-answer',
  'practice-exercise-answer-child': '/practice/practice-exercises-answer-child',
  'practice-record': '/practice/user-practice-exercises-record',
  'practice-record-detail': '/practice/user-practice-exercises-record/detail',
  post: '/postcollect/post',
  'collection-task': '/postcollect/post-collection-task',
  'collection-task-instance': '/yj/collection-task-instance',
  'post-instance': '/yj/post-instance',
  agreement: '/agreement/agreement',
  'agreement-detail': '/agreement/agreement-detail'
}

const getResourceEndpoint = (resource: string) => resourceEndpointMap[resource] || `/yj/${resource}`

export const YjApi = {
  getResources: async () => {
    return await request.get<YjResourceMeta[]>({ url: '/yj/resources' })
  },

  getPage: async (resource: string, params: Record<string, any>) => {
    return await request.get<YjPageResult>({ url: `${getResourceEndpoint(resource)}/page`, params })
  },

  get: async (resource: string, id: number) => {
    return await request.get<YjRecord>({ url: `${getResourceEndpoint(resource)}/get?id=${id}` })
  },

  create: async (resource: string, data: YjRecord) => {
    return await request.post<number>({ url: `${getResourceEndpoint(resource)}/create`, data })
  },

  update: async (resource: string, data: YjRecord) => {
    return await request.put<boolean>({ url: `${getResourceEndpoint(resource)}/update`, data })
  },

  delete: async (resource: string, id: number) => {
    return await request.delete<boolean>({ url: `${getResourceEndpoint(resource)}/delete?id=${id}` })
  },

  auditEnterprise: async (data: YjRecord) => {
    return await request.put<boolean>({ url: '/yj/enterprise-audit/audit', data })
  },

  auditStudent: async (data: YjRecord) => {
    return await request.put<boolean>({ url: '/yj/student-audit/audit', data })
  },

  publishAgreementDetail: async (data: YjRecord) => {
    return await request.put<boolean>({ url: '/agreement/agreement-detail/publish', data })
  },

  syncQwenPawAgents: async () => {
    return await request.post<QwenPawAgentSyncResult>({ url: '/yj/agent/sync-qwenpaw' })
  },

  callQwenPawAgent: async (data: YjRecord) => {
    return await request.post<QwenPawAgentCallResult>({ url: '/yj/agent/call-qwenpaw', data })
  },

  collectNow: async (id: number) => {
    return await request.post<boolean>({ url: '/postcollect/post-collection-task/collect-now', data: { id } })
  },

  getFeishuAuditRuns: async (folderToken?: string) => {
    return await request.get<FeishuAuditRun[]>({
      url: '/postcollect/feishu-audit/runs',
      params: folderToken ? { folderToken } : undefined
    })
  },

  getFeishuAuditRun: async (id: number) => {
    return await request.get<YjRecord>({ url: '/postcollect/feishu-audit/run', params: { id } })
  },

  getFeishuAuditDocument: async (id: number) => {
    return await request.get<YjRecord>({ url: '/postcollect/feishu-audit/document', params: { id } })
  },

  getFeishuAuditDocuments: async (runId: number) => {
    return await request.get<YjRecord[]>({ url: '/postcollect/feishu-audit/documents', params: { runId } })
  },

  getFeishuDocumentPage: async (params: Record<string, any>) => {
    return await request.get<FeishuDocumentPageResult>({
      url: '/postcollect/feishu-audit/documents/page',
      params
    })
  },

  getFeishuAuditItems: async (runId?: number, documentId?: number) => {
    return await request.get<YjRecord[]>({
      url: '/postcollect/feishu-audit/items',
      params: { runId, documentId }
    })
  },

  uploadCustomerMedia: async (data: FormData) => {
    return await request.upload<YjRecord>({ url: '/yj/customer-message/upload-media', data })
  },

  sendCustomerMessage: async (data: YjRecord) => {
    return await request.post<number>({ url: '/yj/customer-message/send', data })
  },

  queryKnowledge: async (question: string) => {
    return await request.post<YjRecord>({ url: '/yj/knowledge/query', data: { question } })
  }
}
