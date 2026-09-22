import { getYjAppApiBaseUrl } from './apiBase'
import { buildAuthHeader, handleUnauthorizedResponse } from './request'
import { refreshCompanyToken } from './customerAuth'
import { appState, setUserSession } from '@/stores/appState'

type CommonResult<T> = {
  code: number | string
  msg?: string
  message?: string
  data?: T
}

type CustomerServiceRequestData = Record<string, string | number | boolean | undefined>
type CustomerServiceMediaType = 'image' | 'video'

type BosUploadResult = {
  url: string
  bosUri?: string
  bucketName?: string
  endpoint?: string
  objectKey?: string
  eTag?: string
}

export type CustomerServiceMessage = {
  id: number
  sessionId: number
  sessionFrom: number
  sessionTo: number
  messageType: 'text' | string
  content: string
  createTime: string
  mine: boolean
}

export type CustomerServiceSession = {
  id: number
  sessionFrom: number
  sessionTo: number
  lastMessageContent: string
  lastMessageTime: string
  unreadCount: number
  messages: CustomerServiceMessage[]
}

export type EnterpriseStudentConversation = {
  studentId: number
  studentName: string
  studentPhone: string
  tenantId: number | null
  conversationId: string | null
  lastMessageContent: string
  lastMessageTime: string
  unreadCount: number
}

const CUSTOMER_SERVICE_BASE = '/app-api/yj/customer-service'
const COMPANY_STUDENTS_BASE = '/app-api/yj/company-students'

const isSuccessCode = (code: number | string | undefined) => code === 0 || code === '0' || code === '00000'
const TENANT_ACCESS_DENIED_MESSAGE = '\u60a8\u65e0\u6743\u8bbf\u95ee\u8be5\u79df\u6237\u7684\u6570\u636e'

const normalizeCustomerServiceErrorMessage = (message: string, fallback: string) => {
  const normalizedMessage = message.trim()
  if (!normalizedMessage) {
    return fallback
  }

  return normalizedMessage
}

const readErrorMessage = (body: CommonResult<unknown> | undefined, fallback: string) => {
  const message = body?.msg || body?.message || ''
  return normalizeCustomerServiceErrorMessage(message, fallback)
}

const canRefreshEnterpriseTenantToken = (body: CommonResult<unknown> | undefined) =>
  appState.loginIdentity === 'enterprise' &&
  Boolean(appState.userSession?.refreshToken) &&
  readErrorMessage(body, '').includes(TENANT_ACCESS_DENIED_MESSAGE)

const refreshEnterpriseTenantToken = async () => {
  const refreshToken = appState.userSession?.refreshToken || ''
  const tenantId = appState.userSession?.tenantId
  const refreshedSession = await refreshCompanyToken(refreshToken, tenantId)
  setUserSession(refreshedSession)
}

const requestCustomerService = <T>(options: {
  base?: string
  path: string
  method: 'GET' | 'POST'
  data?: CustomerServiceRequestData
  fallbackError: string
  retriedTenantToken?: boolean
}) => {
  return new Promise<T>((resolve, reject) => {
    uni.request({
      url: `${getYjAppApiBaseUrl()}${options.base || CUSTOMER_SERVICE_BASE}${options.path}`,
      method: options.method,
      header: {
        'content-type': 'application/json',
        ...buildAuthHeader()
      },
      data: options.data,
      success: (response) => {
        const body = response.data as CommonResult<T>
        if (handleUnauthorizedResponse(body)) {
          reject(new Error(readErrorMessage(body, '登录状态已过期，请重新登录')))
          return
        }
        if (response.statusCode >= 200 && response.statusCode < 300 && isSuccessCode(body?.code) && body.data !== undefined) {
          resolve(body.data)
          return
        }
        if (!options.retriedTenantToken && canRefreshEnterpriseTenantToken(body)) {
          refreshEnterpriseTenantToken()
            .then(() => requestCustomerService<T>({ ...options, retriedTenantToken: true }))
            .then(resolve)
            .catch(reject)
          return
        }
        reject(new Error(readErrorMessage(body, options.fallbackError)))
      },
      fail: (error) => {
        const errMsg = typeof error?.errMsg === 'string' ? error.errMsg : ''
        if (errMsg.includes('timeout')) {
          reject(new Error('客服服务响应超时，请稍后重试'))
          return
        }
        reject(new Error('客服服务暂不可用，请稍后重试'))
      }
    })
  })
}

const readNumber = (source: Record<string, unknown>, keys: string[]) => {
  for (const key of keys) {
    const value = source[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  }
  return 0
}

const readString = (source: Record<string, unknown>, keys: string[]) => {
  for (const key of keys) {
    const value = source[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number' && Number.isFinite(value)) return `${value}`
  }
  return ''
}

const readList = (data: unknown): unknown[] => {
  if (Array.isArray(data)) return data
  if (!data || typeof data !== 'object') return []

  const source = data as Record<string, unknown>
  const candidates = [source.list, source.records, source.rows, source.items, source.data]
  const list = candidates.find(Array.isArray)
  return Array.isArray(list) ? list : []
}

const toEnterpriseStudentConversation = (item: unknown): EnterpriseStudentConversation | null => {
  if (!item || typeof item !== 'object') return null

  const source = item as Record<string, unknown>
  const studentId = readNumber(source, ['customerAccountId', 'studentId', 'customerId', 'id', 'userId'])
  const itemTenantId = readNumber(source, ['tenantId', 'companyId'])

  if (!studentId) {
    return null
  }

  const studentName =
    readString(source, ['studentName', 'customerName', 'nickname', 'nickName', 'realName', 'name']) ||
    `学员${studentId}`
  const studentPhone = readString(source, ['mobile', 'phone', 'studentPhone', 'customerMobile', 'contactMobile'])
  const conversationId = readString(source, ['conversationId', 'sessionId']) || null

  return {
    studentId,
    studentName,
    studentPhone,
    tenantId: itemTenantId > 0 ? itemTenantId : null,
    conversationId,
    lastMessageContent: readString(source, ['lastMessageContent', 'lastMessage', 'message']) || '点击打开聊天框',
    lastMessageTime: readString(source, ['lastMessageTime', 'updateTime', 'auditTime', 'createTime']),
    unreadCount: readNumber(source, ['unreadCount'])
  }
}

export const fetchCustomerServiceSession = () =>
  requestCustomerService<CustomerServiceSession>({
    path: '/session',
    method: 'GET',
    fallbackError: '客服会话加载失败'
  })

export const fetchEnterpriseStudentConversations = async (pageNo = 1, pageSize = 50) => {
  const data = await requestCustomerService<unknown>({
    base: COMPANY_STUDENTS_BASE,
    path: '',
    method: 'GET',
    data: { pageNo, pageSize },
    fallbackError: '学员列表加载失败'
  })

  return readList(data)
    .map(toEnterpriseStudentConversation)
    .filter((item): item is EnterpriseStudentConversation => Boolean(item))
}

export const fetchCustomerServiceMessages = (pageNo = 1, pageSize = 100) =>
  requestCustomerService<CustomerServiceMessage[]>({
    path: '/messages',
    method: 'GET',
    data: { pageNo, pageSize },
    fallbackError: '客服消息加载失败'
  })

export const startEnterpriseStudentConversation = (studentId: number) =>
  requestCustomerService<EnterpriseStudentConversation>({
    base: COMPANY_STUDENTS_BASE,
    path: '/conversations/start',
    method: 'POST',
    data: { studentId },
    fallbackError: '发起学员会话失败'
  })

export const fetchEnterpriseStudentMessages = (conversationId: number, studentId: number, pageNo = 1, pageSize = 200) =>
  requestCustomerService<CustomerServiceMessage[]>({
    base: COMPANY_STUDENTS_BASE,
    path: '/messages',
    method: 'GET',
    data: { conversationId, studentId, pageNo, pageSize },
    fallbackError: '学员消息加载失败'
  })

export const fetchAllEnterpriseStudentMessages = async (conversationId: number, studentId: number, pageSize = 200) => {
  const messages: CustomerServiceMessage[] = []
  let pageNo = 1
  while (true) {
    const page = await fetchEnterpriseStudentMessages(conversationId, studentId, pageNo, pageSize)
    messages.push(...page)
    if (page.length < pageSize) break
    pageNo += 1
  }
  return messages
}

export const sendCustomerServiceTextMessage = (content: string) =>
  requestCustomerService<CustomerServiceMessage>({
    path: '/messages',
    method: 'POST',
    data: { messageType: 'text', content },
    fallbackError: '消息发送失败'
  })

export const sendEnterpriseStudentTextMessage = (conversationId: number, studentId: number, content: string) =>
  requestCustomerService<CustomerServiceMessage>({
    base: COMPANY_STUDENTS_BASE,
    path: '/messages/send',
    method: 'POST',
    data: { conversationId, studentId, messageType: 'text', content },
    fallbackError: '消息发送失败'
  })

export const sendCustomerServiceMediaMessage = (messageType: CustomerServiceMediaType, content: string) =>
  requestCustomerService<CustomerServiceMessage>({
    path: '/messages',
    method: 'POST',
    data: { messageType, content },
    fallbackError: '消息发送失败'
  })

export const sendEnterpriseStudentMediaMessage = (conversationId: number, studentId: number,
  messageType: CustomerServiceMediaType, content: string) =>
  requestCustomerService<CustomerServiceMessage>({
    base: COMPANY_STUDENTS_BASE,
    path: '/messages/send',
    method: 'POST',
    data: { conversationId, studentId, messageType, content },
    fallbackError: '消息发送失败'
  })

export const uploadCustomerServiceMedia = (filePath: string, messageType: CustomerServiceMediaType) =>
  new Promise<BosUploadResult>((resolve, reject) => {
    uni.uploadFile({
      url: `${getYjAppApiBaseUrl()}${CUSTOMER_SERVICE_BASE}/media`,
      filePath,
      name: 'file',
      fileType: messageType,
      formData: { messageType },
      header: buildAuthHeader(),
      success: (response) => {
        let body: CommonResult<BosUploadResult> | undefined
        try {
          body = typeof response.data === 'string'
            ? JSON.parse(response.data) as CommonResult<BosUploadResult>
            : response.data as CommonResult<BosUploadResult>
        } catch {
          reject(new Error('媒体上传失败，请稍后重试'))
          return
        }

        if (response.statusCode >= 200 && response.statusCode < 300 && isSuccessCode(body?.code) && body?.data?.url) {
          resolve(body.data)
          return
        }
        if (handleUnauthorizedResponse(body)) {
          reject(new Error(readErrorMessage(body, '登录状态已过期，请重新登录')))
          return
        }
        reject(new Error(readErrorMessage(body, '媒体上传失败，请稍后重试')))
      },
      fail: () => {
        reject(new Error('媒体上传失败，请检查网络或服务配置'))
      }
    })
  })
