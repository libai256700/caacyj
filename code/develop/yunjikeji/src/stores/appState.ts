import { computed, reactive } from 'vue'

export type AppTabKey = 'students' | 'practice' | 'center' | 'service' | 'jobs' | 'profile'

export type AppAsyncStatus = 'ready' | 'loading' | 'empty' | 'error'

export type LoginIdentity = 'student' | 'enterprise'

export type OrganizationBindingStatus = 'unbound' | 'pending' | 'approved' | 'skipped'

export type OrganizationBindingApplyMode = 'bind' | 'join' | ''

export type OrganizationBindingEntry = 'login' | 'rebind' | 'direct'

export type EnterpriseReviewStatus = 'pending' | 'reviewing' | 'approved' | 'rejected'

export type UserSession = {
  userId: number
  phone: string
  name: string
  role: string
  token: string
  refreshToken: string
  expiresTime: string
  tenantId?: number
  auditStatus?: number
  hasWtPost?: boolean
  isPreview?: boolean
  loggedInAt: string
}

export type UserSessionPayload = {
  userId: number
  mobile: string
  nickname: string
  token: string
  refreshToken?: string
  expiresTime?: string
  tenantId?: number
  auditStatus?: number
  hasWtPost?: boolean
  isPreview?: boolean
}

export type PracticeItem = {
  id: string
  title: string
  category: string
  progress: number
  status: AppAsyncStatus
}

export type OrganizationBindingState = {
  status: OrganizationBindingStatus
  organizationId: string
  organizationName: string
  applyMode: OrganizationBindingApplyMode
  updatedAt: string
  lastEntry: OrganizationBindingEntry
}

export type EnterpriseRegistrationState = {
  status: EnterpriseReviewStatus
  enterpriseName: string
  legalPersonName: string
  legalPersonId: string
  contactName: string
  contactPhone: string
  unifiedSocialCreditCode: string
  licenseFileName: string
  rejectReason: string
  submittedAt: string
  updatedAt: string
}

type AppState = {
  activeTab: AppTabKey
  loginIdentity: LoginIdentity | ''
  userSession: UserSession | null
  organizationBinding: OrganizationBindingState
  enterpriseRegistration: EnterpriseRegistrationState | null
  moduleStatus: Record<AppTabKey, AppAsyncStatus>
  practices: PracticeItem[]
}

const SESSION_STORAGE_KEY = 'yunjikeji-user-session'
const LAST_AUTHENTICATED_PHONE_STORAGE_KEY = 'yunjikeji-last-authenticated-phone'
const LOGIN_IDENTITY_STORAGE_KEY = 'yunjikeji-login-identity'
const ORGANIZATION_BINDING_STORAGE_KEY = 'yunjikeji-organization-binding'
const ENTERPRISE_REGISTRATION_STORAGE_KEY = 'yunjikeji-enterprise-registration'
const LOGIN_REDIRECT_STORAGE_KEY = 'yunjikeji-login-redirect'

const defaultPractices: PracticeItem[] = [
  {
    id: 'uav-basic-001',
    title: '无人机安全起飞基础',
    category: '理论入门',
    progress: 42,
    status: 'ready'
  },
  {
    id: 'uav-route-002',
    title: '航线规划与风险识别',
    category: '任务训练',
    progress: 18,
    status: 'ready'
  }
]

const isStoredSession = (value: unknown): value is UserSession => {
  return Boolean(
    value &&
      typeof value === 'object' &&
      'phone' in value &&
      'token' in value &&
      'userId' in value
  )
}

const readSession = (): UserSession | null => {
  const stored = uni.getStorageSync(SESSION_STORAGE_KEY)
  return isStoredSession(stored) ? stored : null
}

const normalizeAuthenticatedPhone = (value: unknown) => {
  const phone = typeof value === 'string' ? value.replace(/\D/g, '').slice(0, 11) : ''
  return /^1\d{10}$/.test(phone) ? phone : ''
}

const persistAuthenticatedPhone = (value: unknown) => {
  const phone = normalizeAuthenticatedPhone(value)
  if (phone) {
    uni.setStorageSync(LAST_AUTHENTICATED_PHONE_STORAGE_KEY, phone)
  }
}

export const getLastAuthenticatedPhone = () =>
  normalizeAuthenticatedPhone(uni.getStorageSync(LAST_AUTHENTICATED_PHONE_STORAGE_KEY))

const isLoginIdentity = (value: unknown): value is LoginIdentity =>
  value === 'student' || value === 'enterprise'

const readLoginIdentity = (): LoginIdentity | '' => {
  const stored = uni.getStorageSync(LOGIN_IDENTITY_STORAGE_KEY)
  return isLoginIdentity(stored) ? stored : ''
}

const defaultOrganizationBinding = (): OrganizationBindingState => ({
  status: 'unbound',
  organizationId: '',
  organizationName: '',
  applyMode: '',
  updatedAt: '',
  lastEntry: 'direct'
})

const isOrganizationBindingStatus = (value: unknown): value is OrganizationBindingStatus =>
  value === 'unbound' || value === 'pending' || value === 'approved' || value === 'skipped'

const isOrganizationBindingApplyMode = (value: unknown): value is OrganizationBindingApplyMode =>
  value === '' || value === 'bind' || value === 'join'

const isOrganizationBindingEntry = (value: unknown): value is OrganizationBindingEntry =>
  value === 'login' || value === 'rebind' || value === 'direct'

const readOrganizationBinding = (): OrganizationBindingState => {
  const stored = uni.getStorageSync(ORGANIZATION_BINDING_STORAGE_KEY)

  if (!stored || typeof stored !== 'object') {
    return defaultOrganizationBinding()
  }

  const source = stored as Record<string, unknown>

  return {
    status: isOrganizationBindingStatus(source.status) ? source.status : 'unbound',
    organizationId: typeof source.organizationId === 'string' ? source.organizationId : '',
    organizationName: typeof source.organizationName === 'string' ? source.organizationName : '',
    applyMode: isOrganizationBindingApplyMode(source.applyMode) ? source.applyMode : '',
    updatedAt: typeof source.updatedAt === 'string' ? source.updatedAt : '',
    lastEntry: isOrganizationBindingEntry(source.lastEntry) ? source.lastEntry : 'direct'
  }
}

const persistOrganizationBinding = (binding: OrganizationBindingState) => {
  uni.setStorageSync(ORGANIZATION_BINDING_STORAGE_KEY, binding)
}

const isEnterpriseReviewStatus = (value: unknown): value is EnterpriseReviewStatus =>
  value === 'pending' || value === 'reviewing' || value === 'approved' || value === 'rejected'

const readEnterpriseRegistration = (): EnterpriseRegistrationState | null => {
  const stored = uni.getStorageSync(ENTERPRISE_REGISTRATION_STORAGE_KEY)

  if (!stored || typeof stored !== 'object') {
    return null
  }

  const source = stored as Record<string, unknown>
  if (!isEnterpriseReviewStatus(source.status)) {
    return null
  }

  return {
    status: source.status,
    enterpriseName: typeof source.enterpriseName === 'string' ? source.enterpriseName : '',
    legalPersonName: typeof source.legalPersonName === 'string' ? source.legalPersonName : '',
    legalPersonId: typeof source.legalPersonId === 'string' ? source.legalPersonId : '',
    contactName: typeof source.contactName === 'string' ? source.contactName : '',
    contactPhone: typeof source.contactPhone === 'string' ? source.contactPhone : '',
    unifiedSocialCreditCode: typeof source.unifiedSocialCreditCode === 'string' ? source.unifiedSocialCreditCode : '',
    licenseFileName: typeof source.licenseFileName === 'string' ? source.licenseFileName : '',
    rejectReason: typeof source.rejectReason === 'string' ? source.rejectReason : '',
    submittedAt: typeof source.submittedAt === 'string' ? source.submittedAt : '',
    updatedAt: typeof source.updatedAt === 'string' ? source.updatedAt : ''
  }
}

const persistEnterpriseRegistration = (registration: EnterpriseRegistrationState) => {
  uni.setStorageSync(ENTERPRISE_REGISTRATION_STORAGE_KEY, registration)
}

export const appState = reactive<AppState>({
  activeTab: 'practice',
  loginIdentity: readLoginIdentity(),
  userSession: readSession(),
  organizationBinding: readOrganizationBinding(),
  enterpriseRegistration: readEnterpriseRegistration(),
  moduleStatus: {
    students: 'ready',
    practice: defaultPractices.length > 0 ? 'ready' : 'empty',
    center: 'ready',
    service: 'ready',
    jobs: 'ready',
    profile: 'ready'
  },
  practices: defaultPractices
})

export const isLoggedIn = computed(() => Boolean(appState.userSession))

export const setActiveTab = (tab: AppTabKey) => {
  appState.activeTab = tab
}

export const setModuleStatus = (tab: AppTabKey, status: AppAsyncStatus) => {
  appState.moduleStatus[tab] = status
}

export const setLoginIdentity = (identity: LoginIdentity) => {
  appState.loginIdentity = identity
  uni.setStorageSync(LOGIN_IDENTITY_STORAGE_KEY, identity)
}

export const setUserSession = (payload: UserSessionPayload) => {
  const isEnterprise = appState.loginIdentity === 'enterprise'
  const session: UserSession = {
    userId: payload.userId,
    phone: payload.mobile,
    name: payload.nickname || (isEnterprise ? '企业用户' : '飞行学员'),
    role: isEnterprise ? '企业账号' : '无人机培训学员',
    token: payload.token,
    refreshToken: payload.refreshToken || '',
    expiresTime: payload.expiresTime || '',
    tenantId: payload.tenantId,
    auditStatus: payload.auditStatus,
    hasWtPost: payload.hasWtPost,
    isPreview: payload.isPreview,
    loggedInAt: new Date().toISOString()
  }
  appState.userSession = session
  uni.setStorageSync(SESSION_STORAGE_KEY, session)
  if (!payload.isPreview) {
    persistAuthenticatedPhone(payload.mobile)
  }
}

export const updateUserPhoneBinding = (phone: string) => {
  if (!appState.userSession) {
    return
  }

  const session: UserSession = {
    ...appState.userSession,
    phone
  }

  appState.userSession = session
  uni.setStorageSync(SESSION_STORAGE_KEY, session)
  persistAuthenticatedPhone(phone)
}

export const updateUserAuditStatus = (auditStatus?: number) => {
  if (!appState.userSession || auditStatus === undefined || Number.isNaN(Number(auditStatus))) {
    return
  }

  const session: UserSession = {
    ...appState.userSession,
    auditStatus: Number(auditStatus)
  }

  appState.userSession = session
  uni.setStorageSync(SESSION_STORAGE_KEY, session)
}

export const setOrganizationBinding = (payload: {
  organizationId: string
  organizationName: string
  applyMode: Exclude<OrganizationBindingApplyMode, ''>
  entry: OrganizationBindingEntry
}) => {
  const binding: OrganizationBindingState = {
    status: 'pending',
    organizationId: payload.organizationId,
    organizationName: payload.organizationName,
    applyMode: payload.applyMode,
    updatedAt: new Date().toISOString(),
    lastEntry: payload.entry
  }
  appState.organizationBinding = binding
  persistOrganizationBinding(binding)
}

export const markOrganizationBindingApproved = (entry: OrganizationBindingEntry = 'direct') => {
  const current = appState.organizationBinding
  const binding: OrganizationBindingState = {
    ...current,
    status: 'approved',
    updatedAt: new Date().toISOString(),
    lastEntry: entry
  }
  appState.organizationBinding = binding
  persistOrganizationBinding(binding)
}

export const skipOrganizationBinding = (entry: OrganizationBindingEntry) => {
  const binding: OrganizationBindingState = {
    status: 'skipped',
    organizationId: '',
    organizationName: '',
    applyMode: '',
    updatedAt: new Date().toISOString(),
    lastEntry: entry
  }
  appState.organizationBinding = binding
  persistOrganizationBinding(binding)
}

export const setEnterpriseRegistration = (payload: Omit<EnterpriseRegistrationState, 'status' | 'rejectReason' | 'submittedAt' | 'updatedAt'>) => {
  const now = new Date().toISOString()
  const registration: EnterpriseRegistrationState = {
    ...payload,
    status: 'reviewing',
    rejectReason: '',
    submittedAt: now,
    updatedAt: now
  }
  appState.enterpriseRegistration = registration
  persistEnterpriseRegistration(registration)
}

export const setEnterpriseReviewStatus = (status: EnterpriseReviewStatus, rejectReason = '') => {
  const current = appState.enterpriseRegistration
  const registration: EnterpriseRegistrationState = {
    status,
    enterpriseName: current?.enterpriseName || '云技无人机服务有限公司',
    legalPersonName: current?.legalPersonName || '张明',
    legalPersonId: current?.legalPersonId || '',
    contactName: current?.contactName || '李航',
    contactPhone: current?.contactPhone || '13800000000',
    unifiedSocialCreditCode: current?.unifiedSocialCreditCode || '91440300MA5K9UAV8X',
    licenseFileName: current?.licenseFileName || '营业执照.jpg',
    rejectReason: status === 'rejected' ? rejectReason || '提交的资料不符合要求，请补充完整后重新提交。' : '',
    submittedAt: current?.submittedAt || new Date().toISOString(),
    updatedAt: new Date().toISOString()
  }
  appState.enterpriseRegistration = registration
  persistEnterpriseRegistration(registration)
}

export const clearUserSession = () => {
  if (appState.userSession && !appState.userSession.isPreview) {
    persistAuthenticatedPhone(appState.userSession.phone)
  }
  appState.userSession = null
  uni.removeStorageSync(SESSION_STORAGE_KEY)
  const binding = defaultOrganizationBinding()
  appState.organizationBinding = binding
  uni.removeStorageSync(ORGANIZATION_BINDING_STORAGE_KEY)
  appState.enterpriseRegistration = null
  uni.removeStorageSync(ENTERPRISE_REGISTRATION_STORAGE_KEY)
}

const normalizeLoginRedirect = (url: string) => {
  if (!url || !url.startsWith('/pages/') || url.startsWith('/pages/auth/login')) {
    return ''
  }
  return url
}

type CurrentPageWithOptions = {
  route?: string
  options?: Record<string, unknown>
}

export const getCurrentPageUrl = () => {
  const pages = getCurrentPages()
  const currentPage = pages[pages.length - 1] as CurrentPageWithOptions | undefined
  if (!currentPage?.route) {
    return ''
  }

  const query = currentPage.options || {}
  const queryString = Object.entries(query)
    .filter(([, value]) => value !== undefined && value !== null && `${value}` !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(`${value}`)}`)
    .join('&')

  return `/${currentPage.route}${queryString ? `?${queryString}` : ''}`
}

export const setLoginRedirect = (url: string) => {
  const redirectUrl = normalizeLoginRedirect(url)
  if (!redirectUrl) {
    uni.removeStorageSync(LOGIN_REDIRECT_STORAGE_KEY)
    return
  }
  uni.setStorageSync(LOGIN_REDIRECT_STORAGE_KEY, redirectUrl)
}

export const consumeLoginRedirect = () => {
  const stored = uni.getStorageSync(LOGIN_REDIRECT_STORAGE_KEY)
  uni.removeStorageSync(LOGIN_REDIRECT_STORAGE_KEY)
  return typeof stored === 'string' ? normalizeLoginRedirect(stored) : ''
}

export const requireLogin = () => {
  if (appState.userSession) {
    return true
  }

  setLoginRedirect(getCurrentPageUrl())
  uni.reLaunch({
    url: '/pages/auth/login'
  })
  return false
}

export const shouldPromptOrganizationBinding = () => {
  if (!appState.userSession) {
    return false
  }

  if (appState.loginIdentity === 'enterprise') {
    return false
  }

  const status = appState.organizationBinding.status
  return status === 'unbound'
}
