import { appState, clearUserSession, getCurrentPageUrl, setLoginRedirect } from '@/stores/appState'

const SESSION_STORAGE_KEY = 'yunjikeji-user-session'
const LOGIN_PAGE_URL = '/pages/auth/login'

let isRedirectingToLogin = false

type StoredSession = {
  token?: string
  tenantId?: number
}

type UnauthorizedResult = {
  code?: number | string
}

export const buildAuthHeader = (): Record<string, string> => {
  const storedSession = uni.getStorageSync(SESSION_STORAGE_KEY) as StoredSession | null
  const token = appState.userSession?.token?.trim() || storedSession?.token?.trim()
  if (!token) {
    return {}
  }
  const tenantId = appState.userSession?.tenantId || storedSession?.tenantId
  const header: Record<string, string> = {
    Authorization: `Bearer ${token}`
  }
  if (tenantId) {
    header['tenant-id'] = `${tenantId}`
  }
  return header
}

export const handleUnauthorizedResponse = (body: UnauthorizedResult | undefined | null) => {
  if (body?.code !== 401 && body?.code !== '401') {
    return false
  }

  const currentPageUrl = getCurrentPageUrl()
  clearUserSession()
  setLoginRedirect(currentPageUrl)
  if (!isRedirectingToLogin) {
    isRedirectingToLogin = true
    uni.reLaunch({
      url: LOGIN_PAGE_URL,
      complete: () => {
        isRedirectingToLogin = false
      }
    })
  }
  return true
}
