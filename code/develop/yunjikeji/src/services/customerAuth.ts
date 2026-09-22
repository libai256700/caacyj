import { getYjAppApiBaseUrl } from './apiBase'
import { buildAuthHeader, handleUnauthorizedResponse } from './request'
import { buildQueryString } from './url'
import type { UserSessionPayload } from '@/stores/appState'

type CommonResult<T> = {
  code: number | string
  msg?: string
  message?: string
  data?: T
  result?: T
  success?: boolean
}

export type CustomerAuthResponse = {
  customerId: number
  tenantId?: number
  mobile: string
  nickname: string
  auditStatus?: number
  accessToken: string
  refreshToken: string
  expiresTime: string
}

export type CompanyAuthResponse = {
  companyAccountFrontId: number
  tenantId?: number
  username: string
  status: boolean
  auditStatus: number
  accessToken: string
  refreshToken: string
  expiresTime: string
}

export type CompanyPostCodesResponse = {
  userMatched: boolean
  postCodes: string[]
  hasWtPost: boolean
  tenantId?: number
}

export type CustomerProfile = {
  customerId: number
  tenantId?: number
  mobile: string
  nickname: string
  realName: string
  idCard?: string
  avatarUrl: string
  studentNo: string
  schoolName?: string
  majorName: string
  roleLabel: string
  trainingDirection: string
}

export type CompanyProfile = {
  companyAccountFrontId: number
  tenantId?: number
  tenantName?: string
  tenantContactName?: string
  tenantContactMobile?: string
  username: string
  status: boolean
  auditStatus: number
  nickname?: string
  deptName?: string
}

export type EnterpriseAuditSubmitPayload = {
  name: string
  creditCode?: string
  legalPerson: string
  legalPersonId?: string
  contactName: string
  contactMobile: string
  attachments?: Array<{
    filePath: string
    fileName: string
    fileType: string
  }>
}

export type EnterpriseAuditSubmitRequest = {
  companyAccountFrontId: number
}

export type StudentAuditSubmitPayload = {
  tenantId: number
  customerAccountId: number
}

type ApiDateTime = string | number

export type StudentAuditStatus = {
  id: number
  tenantId?: number
  companyId?: number
  customerAccountId: number
  auditStatus: number
  auditStatusText?: string
  auditReason?: string
  auditTime?: string
}

export type CompanyStudentAuditStatus = {
  id: number
  tenantId?: number
  companyId?: number
  customerAccountId: number
  studentName: string
  studentPhone: string
  auditStatus: number
  auditStatusText?: string
  auditReason?: string
  applyTime?: ApiDateTime
  auditTime?: ApiDateTime
}

type PageResult<T> = {
  total: number
  list: T[]
}

export type CompanyStudentAuditActionPayload = {
  id: number
  auditStatus: 2 | 3
  auditReason?: string
}

export type CustomerInfoSavePayload = {
  nickName?: string
  realName?: string
  idCard?: string
  sex?: string
  email?: string
  avatarUrl?: string
  studentNo?: string
  schoolName?: string
  majorName?: string
  roleLabel?: string
  trainingDirection?: string
}

type UploadFileResponse = {
  code: number | string
  msg?: string
  message?: string
  data?: string
  result?: string
  success?: boolean
}

type RequestData = Record<string, unknown> | string | undefined
type BrowserUploadSource = File | Blob | null | undefined
type AppFileUploadOptions = {
  filePath: string
  directory: string
  fallbackError: string
  defaultFileName: string
  requestPath?: string
  rawFile?: BrowserUploadSource
}

const CUSTOMER_AUTH_BASE = '/app-api/yj/customer-auth'
const CUSTOMER_INFO_BASE = '/app-api/yj/customer-info'
const COMPANY_AUTH_BASE = '/app-api/yj/company-auth'
const ENTERPRISE_AUDIT_BASE = '/app-api/yj/enterprise-audit'
const CUSTOMER_AVATAR_UPLOAD_PATH = '/app-api/yj/customer-info/avatar/upload'
const ENTERPRISE_LICENSE_UPLOAD_PATH = '/app-api/yj/enterprise-audit/license/upload'
const STUDENT_AUDIT_BASE = '/app-api/yj/student-audit'
const COMPANY_STUDENT_AUDIT_BASE = '/app-api/yj/company/student-audit'
const MEMBER_AUTH_BASE = '/app-api/member/auth'
const MEMBER_LOGIN_SMS_SCENE = 1
const REQUEST_TIMEOUT_MS = 20000

const isSuccessCode = (code: number | string | undefined) => code === 0 || code === '0' || code === '00000'
const readResponseData = <T>(body: CommonResult<T> | UploadFileResponse | undefined) =>
  body?.data !== undefined ? body.data : body?.result

const readErrorMessage = (body: CommonResult<unknown> | undefined, fallback: string) => {
  const message = body?.msg || body?.message || ''
  return message.trim() || fallback
}

const buildUploadRequestUrl = (requestPath?: string) =>
  `${getYjAppApiBaseUrl()}${requestPath || '/app-api/infra/file/upload'}`

const toFormUrlEncoded = (payload: Record<string, unknown>) => {
  return buildQueryString(payload)
}

const isCredentialError = (error: unknown) => {
  const message = error instanceof Error ? error.message : ''
  return (
    message.includes('密码') ||
    message.includes('验证码') ||
    message.includes('错误') ||
    message.includes('UNAUTHORIZED') ||
    message.includes('Unauthorized')
  )
}

// #ifdef H5
const guessExtensionByMimeType = (mimeType: string) => {
  const normalized = mimeType.toLowerCase()
  if (normalized.includes('jpeg')) return '.jpg'
  if (normalized.includes('png')) return '.png'
  if (normalized.includes('webp')) return '.webp'
  if (normalized.includes('gif')) return '.gif'
  if (normalized.includes('bmp')) return '.bmp'
  if (normalized.includes('pdf')) return '.pdf'
  return ''
}

const sanitizeFileName = (value: string) => value.replace(/[?#].*$/, '').trim()

const resolveUploadFileName = (filePath: string, fallbackName: string, mimeType: string) => {
  const normalizedFallbackName = sanitizeFileName(fallbackName) || 'upload-file'
  const segments = filePath.split(/[\\/]/)
  const lastSegment = sanitizeFileName(decodeURIComponent(segments[segments.length - 1] || ''))

  if (lastSegment && /\.[a-z0-9]+$/i.test(lastSegment)) {
    return lastSegment
  }

  const extension = guessExtensionByMimeType(mimeType)
  if (extension && !normalizedFallbackName.toLowerCase().endsWith(extension)) {
    return `${normalizedFallbackName}${extension}`
  }

  return normalizedFallbackName
}

const toBrowserUploadFile = async (
  filePath: string,
  fallbackName: string,
  rawFile?: BrowserUploadSource
) => {
  if (typeof File !== 'undefined' && rawFile instanceof File) {
    return rawFile
  }

  if (typeof Blob !== 'undefined' && rawFile instanceof Blob) {
    const fileName = resolveUploadFileName(filePath, fallbackName, rawFile.type || '')
    try {
      return new File([rawFile], fileName, { type: rawFile.type || 'application/octet-stream' })
    } catch (error) {
      const uploadBlob = rawFile as Blob & { name?: string }
      uploadBlob.name = uploadBlob.name || fileName
      return uploadBlob
    }
  }

  const response = await fetch(filePath)
  if (!response.ok) {
    throw new Error('file-read-failed')
  }

  const blob = await response.blob()
  const fileName = resolveUploadFileName(filePath, fallbackName, blob.type || '')
  try {
    return new File([blob], fileName, { type: blob.type || 'application/octet-stream' })
  } catch (error) {
    const uploadBlob = blob as Blob & { name?: string }
    uploadBlob.name = uploadBlob.name || fileName
    return uploadBlob
  }
}

const uploadAppFileByBrowser = async (options: AppFileUploadOptions) => {
  const uploadFile = await toBrowserUploadFile(options.filePath, options.defaultFileName, options.rawFile)
  const requestUrl = buildUploadRequestUrl(options.requestPath)

  return new Promise<string>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    formData.append('file', uploadFile, (uploadFile as File).name || options.defaultFileName)
    formData.append('directory', options.directory)

    xhr.open('POST', requestUrl, true)
    xhr.timeout = REQUEST_TIMEOUT_MS
    Object.entries(buildAuthHeader()).forEach(([key, value]) => {
      xhr.setRequestHeader(key, value)
    })

    xhr.onload = () => {
      let body: UploadFileResponse | undefined
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) as UploadFileResponse : undefined
      } catch (error) {
        reject(new Error(options.fallbackError))
        return
      }

      if (handleUnauthorizedResponse(body)) {
        reject(new Error(readErrorMessage(body, '登录状态已过期，请重新登录')))
        return
      }

      const responseData = readResponseData(body)
      const isSuccess = isSuccessCode(body?.code) || body?.success === true
      if (xhr.status >= 200 && xhr.status < 300 && isSuccess && typeof responseData === 'string' && responseData.trim()) {
        resolve(responseData)
        return
      }

      reject(new Error(readErrorMessage(body, options.fallbackError)))
    }

    xhr.onerror = () => {
      reject(new Error(`${options.fallbackError}，请检查网络或服务配置`))
    }

    xhr.ontimeout = () => {
      reject(new Error(`${options.fallbackError}，请求超时，请稍后重试`))
    }

    xhr.send(formData)
  })
}
// #endif

// #ifdef APP-PLUS
const uploadAppFileByAppPlus = (options: AppFileUploadOptions) =>
  new Promise<string>((resolve, reject) => {
    uni.uploadFile({
      url: buildUploadRequestUrl(options.requestPath),
      filePath: options.filePath,
      name: 'file',
      fileType: 'image',
      timeout: REQUEST_TIMEOUT_MS,
      formData: {
        directory: options.directory
      },
      header: buildAuthHeader(),
      success: (response) => {
        let body: UploadFileResponse | undefined
        try {
          body = typeof response.data === 'string'
            ? JSON.parse(response.data) as UploadFileResponse
            : response.data as UploadFileResponse
        } catch (error) {
          reject(new Error(options.fallbackError))
          return
        }

        if (handleUnauthorizedResponse(body)) {
          reject(new Error(readErrorMessage(body, '登录状态已过期，请重新登录')))
          return
        }

        const responseData = readResponseData(body)
        const isSuccess = isSuccessCode(body?.code) || body?.success === true
        if (
          response.statusCode >= 200 &&
          response.statusCode < 300 &&
          isSuccess &&
          typeof responseData === 'string' &&
          responseData.trim()
        ) {
          resolve(responseData)
          return
        }

        reject(new Error(readErrorMessage(body, options.fallbackError)))
      },
      fail: () => {
        reject(new Error(`${options.fallbackError}，请检查网络或服务配置`))
      }
    })
  })
// #endif

const uploadAppFile = (options: AppFileUploadOptions) => {
  // #ifdef APP-PLUS
  return uploadAppFileByAppPlus(options)
  // #endif

  // #ifdef H5
  return uploadAppFileByBrowser(options)
  // #endif

  return Promise.reject(new Error('当前平台不支持文件上传'))
}

export const toStudentSessionPayload = (data: CustomerAuthResponse): UserSessionPayload => ({
  userId: data.customerId,
  mobile: data.mobile,
  nickname: data.nickname,
  token: data.accessToken,
  refreshToken: data.refreshToken,
  expiresTime: data.expiresTime,
  tenantId: data.tenantId,
  auditStatus: data.auditStatus
})

export const toCompanySessionPayload = (data: CompanyAuthResponse): UserSessionPayload => ({
  userId: data.companyAccountFrontId,
  mobile: data.username,
  nickname: '企业用户',
  token: data.accessToken,
  refreshToken: data.refreshToken,
  expiresTime: data.expiresTime,
  tenantId: data.tenantId,
  auditStatus: data.auditStatus
})

const requestAppApi = <T>(options: {
  base: string
  path: string
  method: 'GET' | 'POST' | 'PUT'
  data?: RequestData
  query?: Record<string, string>
  auth?: boolean
  headers?: Record<string, string>
  fallbackError: string
}) => {
  return new Promise<T>((resolve, reject) => {
    const query = options.query
      ? `?${Object.entries(options.query)
          .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
          .join('&')}`
      : ''
    const requestUrl = `${getYjAppApiBaseUrl()}${options.base}${options.path}${query}`

    uni.request({
      url: requestUrl,
      method: options.method,
      timeout: REQUEST_TIMEOUT_MS,
      firstIpv4: true,
      header: {
        'content-type': 'application/json',
        ...(options.auth ? buildAuthHeader() : {}),
        ...(options.headers || {})
      },
      data: options.data,
      success: (response) => {
        const body = response.data as CommonResult<T>
        const responseData = body?.data !== undefined ? body.data : body?.result
        const isSuccess = isSuccessCode(body?.code) || body?.success === true
        if (handleUnauthorizedResponse(body)) {
          reject(new Error(readErrorMessage(body, '登录状态已过期，请重新登录')))
          return
        }
        if (response.statusCode >= 200 && response.statusCode < 300 && isSuccess && responseData !== undefined) {
          resolve(responseData as T)
          return
        }
        reject(new Error(readErrorMessage(body, options.fallbackError)))
      },
      fail: (error) => {
        const errMsg = typeof error?.errMsg === 'string' ? error.errMsg : ''
        console.error('[customerAuth] request failed', {
          url: requestUrl,
          errMsg,
          error
        })
        if (errMsg.includes('timeout')) {
          reject(new Error('登录服务响应超时，请稍后重试'))
          return
        }
        reject(new Error('账号服务不可用，请检查接口配置或后端服务'))
      }
    })
  })
}

const requestCustomerAuth = <T>(options: Omit<Parameters<typeof requestAppApi<T>>[0], 'base'>) =>
  requestAppApi<T>({ ...options, base: CUSTOMER_AUTH_BASE })

const requestCompanyAuth = <T>(options: Omit<Parameters<typeof requestAppApi<T>>[0], 'base'>) =>
  requestAppApi<T>({ ...options, base: COMPANY_AUTH_BASE })

export const sendLoginSmsCode = (mobile: string) =>
  requestAppApi<boolean>({
    base: MEMBER_AUTH_BASE,
    path: '/send-sms-code',
    method: 'POST',
    data: {
      mobile,
      scene: MEMBER_LOGIN_SMS_SCENE
    },
    fallbackError: '验证码发送失败，请稍后重试'
  })

export const loginCustomer = async (mobile: string, code: string) => {
  const data = await requestCustomerAuth<CustomerAuthResponse>({
    path: '/login-or-register',
    method: 'POST',
    data: { mobile, code, password: code },
    fallbackError: '手机号或验证码错误'
  })
  return toStudentSessionPayload(data)
}

export const bindCustomerMobile = (mobile: string, code: string) =>
  requestCustomerAuth<boolean>({
    path: '/bind-mobile',
    method: 'POST',
    auth: true,
    data: { mobile, code },
    fallbackError: '手机号绑定失败，请稍后重试'
  })

export const registerCustomer = async (mobile: string, password: string, nickname: string) => {
  const data = await requestCustomerAuth<CustomerAuthResponse>({
    path: '/register',
    method: 'POST',
    data: { mobile, password, nickname },
    fallbackError: '注册失败，请稍后重试'
  })
  return toStudentSessionPayload(data)
}

export const loginCompany = async (username: string, code: string) => {
  const data = await requestCompanyAuth<CompanyAuthResponse>({
    path: '/login-or-register',
    method: 'POST',
    data: { mobile: username, code, password: code },
    fallbackError: '手机号或验证码错误'
  })
  return toCompanySessionPayload(data)
}

export const registerCompany = async (username: string, password: string) => {
  const data = await requestCompanyAuth<CompanyAuthResponse>({
    path: '/register',
    method: 'POST',
    data: { username, password },
    fallbackError: '注册失败，请稍后重试'
  })
  return toCompanySessionPayload(data)
}

export const loginOrRegisterCompany = (mobile: string, code: string) => loginCompany(mobile, code)

export const fetchCompanyPostCodes = (mobile: string) =>
  requestCompanyAuth<CompanyPostCodesResponse>({
    path: '/post-codes',
    method: 'GET',
    query: { mobile },
    auth: true,
    fallbackError: '企业岗位信息加载失败'
  })

export const refreshCustomerToken = async (refreshToken: string) => {
  const data = await requestCustomerAuth<CustomerAuthResponse>({
    path: '/refresh-token',
    method: 'POST',
    query: { refreshToken },
    fallbackError: '登录状态已过期，请重新登录'
  })
  return toStudentSessionPayload(data)
}

export const refreshCompanyToken = async (refreshToken: string, tenantId?: number) => {
  const data = await requestCompanyAuth<CompanyAuthResponse>({
    path: '/refresh-token',
    method: 'POST',
    query: { refreshToken },
    headers: tenantId ? { 'tenant-id': `${tenantId}` } : undefined,
    fallbackError: '鐧诲綍鐘舵€佸凡杩囨湡锛岃閲嶆柊鐧诲綍'
  })
  return {
    ...toCompanySessionPayload(data),
    tenantId: tenantId || data.tenantId
  }
}

export const fetchCurrentCustomer = () =>
  requestCustomerAuth<CustomerProfile>({
    path: '/me',
    method: 'GET',
    auth: true,
    fallbackError: '学员信息加载失败'
  })

export const fetchCurrentCompany = () =>
  requestCompanyAuth<CompanyProfile>({
    path: '/me',
    method: 'GET',
    auth: true,
    fallbackError: '企业信息加载失败'
  })

export const saveCustomerInfo = (payload: CustomerInfoSavePayload) =>
  requestAppApi<boolean>({
    base: CUSTOMER_INFO_BASE,
    path: '/save',
    method: 'POST',
    auth: true,
    data: payload,
    fallbackError: '学员信息保存失败'
  })

export const uploadAvatarImage = (filePath: string, fileName = 'avatar.jpg', rawFile?: BrowserUploadSource) =>
  uploadAppFile({
    filePath,
    directory: 'avatar',
    fallbackError: '头像上传失败，请稍后重试',
    defaultFileName: fileName,
    requestPath: CUSTOMER_AVATAR_UPLOAD_PATH,
    rawFile
  })

export const uploadEnterpriseLicenseImage = (
  filePath: string,
  fileName = 'business-license.jpg',
  rawFile?: BrowserUploadSource
) =>
  uploadAppFile({
    filePath,
    directory: 'enterprise/license',
    fallbackError: '营业执照上传失败，请稍后重试',
    defaultFileName: fileName,
    requestPath: ENTERPRISE_LICENSE_UPLOAD_PATH,
    rawFile
  })

export const submitStudentAudit = (payload: StudentAuditSubmitPayload) =>
  requestAppApi<number>({
    base: STUDENT_AUDIT_BASE,
    path: '/submit',
    method: 'POST',
    auth: true,
    data: payload,
    fallbackError: '提交组织申请失败，请稍后重试'
  })

export const fetchCurrentStudentAudit = () =>
  requestAppApi<StudentAuditStatus | null>({
    base: STUDENT_AUDIT_BASE,
    path: '/my',
    method: 'GET',
    auth: true,
    fallbackError: '组织申请状态加载失败'
  })

export const fetchCompanyStudentAudits = () =>
  requestAppApi<PageResult<CompanyStudentAuditStatus>>({
    base: COMPANY_STUDENT_AUDIT_BASE,
    path: '/page',
    method: 'GET',
    auth: true,
    query: {
      pageNo: '1',
      pageSize: '200',
      auditStatus: '1'
    },
    fallbackError: '学员审核列表加载失败'
  })

export const auditCompanyStudent = (payload: CompanyStudentAuditActionPayload) =>
  requestAppApi<boolean>({
    base: COMPANY_STUDENT_AUDIT_BASE,
    path: '/audit',
    method: 'PUT',
    auth: true,
    data: payload,
    fallbackError: payload.auditStatus === 2 ? '学员审核通过失败，请稍后重试' : '学员审核拒绝失败，请稍后重试'
  })

export const logoutCustomer = () =>
  requestCustomerAuth<boolean>({
    path: '/logout',
    method: 'POST',
    auth: true,
    fallbackError: '退出登录失败，请稍后重试'
  })

export const logoutCompany = () =>
  requestCompanyAuth<boolean>({
    path: '/logout',
    method: 'POST',
    auth: true,
    fallbackError: '退出登录失败，请稍后重试'
  })

export const saveEnterpriseAudit = (payload: EnterpriseAuditSubmitPayload) =>
  requestAppApi<number>({
    base: ENTERPRISE_AUDIT_BASE,
    path: '/save',
    method: 'POST',
    auth: true,
    data: payload,
    fallbackError: '保存企业信息失败，请稍后重试'
  })

export const submitEnterpriseAudit = (payload: EnterpriseAuditSubmitRequest) =>
  requestAppApi<number>({
    base: ENTERPRISE_AUDIT_BASE,
    path: '/submit',
    method: 'POST',
    auth: true,
    data: payload,
    fallbackError: '提交审核失败，请稍后重试'
  })

export const saveEnterpriseAuditForm = (payload: EnterpriseAuditSubmitPayload) =>
  requestAppApi<number>({
    base: ENTERPRISE_AUDIT_BASE,
    path: '/save',
    method: 'POST',
    auth: true,
    data: toFormUrlEncoded(payload as Record<string, unknown>),
    headers: {
      'content-type': 'application/x-www-form-urlencoded'
    },
    fallbackError: '保存企业信息失败，请稍后重试'
  })

export const submitEnterpriseAuditForm = (payload: EnterpriseAuditSubmitRequest) =>
  requestAppApi<number>({
    base: ENTERPRISE_AUDIT_BASE,
    path: '/submit',
    method: 'POST',
    auth: true,
    data: toFormUrlEncoded(payload as Record<string, unknown>),
    headers: {
      'content-type': 'application/x-www-form-urlencoded'
    },
    fallbackError: '提交审核失败，请稍后重试'
  })
