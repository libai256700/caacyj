import { getYjAppApiBaseUrl } from './apiBase'
import { appState } from '@/stores/appState'
import { buildAbsoluteWebSocketUrl } from './url'

export const CUSTOMER_SERVICE_SOCKET_MESSAGE_TYPE = 'yj_customer_service_message'
const CUSTOMER_SERVICE_SOCKET_SEND_TYPE = 'yj_customer_service_send'
const SESSION_STORAGE_KEY = 'yunjikeji-user-session'

type StoredSession = {
  token?: string
}

export type CustomerServiceRealtimeMessage = {
  id: number
  conversationId: string
  sessionId: number
  sessionFrom: number
  sessionTo: number
  studentId: number
  tenantId: number
  messageType: string
  content: string
  createTime: string
}

type SocketEnvelope<T> = {
  type?: string
  content?: T
}

const parseSocketContent = (content: unknown) => {
  if (typeof content === 'string') {
    try {
      return JSON.parse(content) as unknown
    } catch {
      return null
    }
  }
  return content
}

const readToken = () => {
  const storedSession = uni.getStorageSync(SESSION_STORAGE_KEY) as StoredSession | null
  return appState.userSession?.token?.trim() || storedSession?.token?.trim() || ''
}

const toWebSocketUrl = () => {
  const token = readToken()
  if (!token) {
    throw new Error('登录状态已失效，请重新登录')
  }

  const baseUrl = getYjAppApiBaseUrl()
  const normalizedBase = baseUrl.replace(/\/$/, '')

  if (/^https?:\/\//.test(normalizedBase)) {
    return buildAbsoluteWebSocketUrl(normalizedBase, '/infra/ws', { token })
  }

  if (typeof window !== 'undefined' && window.location?.origin) {
    return buildAbsoluteWebSocketUrl(`${window.location.origin}${normalizedBase}`, '/infra/ws', { token })
  }

  throw new Error('当前环境未配置可用的 WebSocket 地址')
}

const readNumber = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return 0
}

const readString = (value: unknown) => {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return `${value}`
  return ''
}

const normalizeRealtimeMessage = (payload: unknown): CustomerServiceRealtimeMessage | null => {
  if (!payload || typeof payload !== 'object') return null
  const source = payload as Record<string, unknown>
  const id = readNumber(source.id)
  const sessionId = readNumber(source.sessionId)
  if (!id || !sessionId) return null

  return {
    id,
    conversationId: readString(source.conversationId) || `${sessionId}`,
    sessionId,
    sessionFrom: readNumber(source.sessionFrom),
    sessionTo: readNumber(source.sessionTo),
    studentId: readNumber(source.studentId),
    tenantId: readNumber(source.tenantId),
    messageType: readString(source.messageType) || 'text',
    content: readString(source.content),
    createTime: readString(source.createTime)
  }
}

export const createCustomerServiceSocket = (handlers: {
  onMessage: (message: CustomerServiceRealtimeMessage) => void
  onError?: (message: string) => void
}) => {
  let socketTask: UniApp.SocketTask | null = null
  let manuallyClosed = false

  const connect = () => {
    if (socketTask) return
    manuallyClosed = false

    socketTask = uni.connectSocket({
      url: toWebSocketUrl(),
      complete: () => {}
    })

    socketTask.onMessage((event) => {
      try {
        const envelope = JSON.parse(event.data) as SocketEnvelope<unknown>
        if (envelope?.type !== CUSTOMER_SERVICE_SOCKET_MESSAGE_TYPE) return
        const message = normalizeRealtimeMessage(parseSocketContent(envelope.content))
        if (message) {
          handlers.onMessage(message)
        }
      } catch (error) {
        handlers.onError?.(error instanceof Error ? error.message : '实时消息解析失败')
      }
    })

    socketTask.onError((event) => {
      if (!manuallyClosed) {
        handlers.onError?.(event?.errMsg || '实时连接失败')
      }
    })

    socketTask.onClose(() => {
      socketTask = null
    })
  }

  const sendTextMessage = (payload: { conversationId?: number; studentId?: number; content: string }) => {
    if (!socketTask) {
      throw new Error('实时连接尚未建立')
    }
    return new Promise<void>((resolve, reject) => {
      socketTask?.send({
        data: JSON.stringify({
          type: CUSTOMER_SERVICE_SOCKET_SEND_TYPE,
          content: JSON.stringify({
            conversationId: payload.conversationId,
            studentId: payload.studentId,
            content: payload.content
          })
        }),
        success: () => resolve(),
        fail: (error) => reject(new Error(error?.errMsg || '实时消息发送失败'))
      })
    })
  }

  const close = () => {
    manuallyClosed = true
    if (!socketTask) return
    socketTask.close({ complete: () => {} })
    socketTask = null
  }

  return {
    connect,
    sendTextMessage,
    close
  }
}
