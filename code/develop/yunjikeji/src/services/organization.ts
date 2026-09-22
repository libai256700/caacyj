import { getYjAppApiBaseUrl } from './apiBase'
import { buildAuthHeader, handleUnauthorizedResponse } from './request'
import { buildQueryString } from './url'

export type OrganizationTagTone = 'blue' | 'green' | 'purple' | 'orange' | 'cyan'

export type OrganizationApplyMode = 'bind' | 'join'

export type OrganizationSummary = {
  id: string
  name: string
  province: string
  city: string
  memberCount: number
  tag: string
  tagTone: OrganizationTagTone
  applyMode: OrganizationApplyMode
  badgeText: string
  iconUrl: string
  tenantId: number
  contactName: string
  contactMobile: string
}

type CommonResult<T> = {
  code: number | string
  msg?: string
  message?: string
  data?: T
}

type PageResult<T> = {
  list?: T[]
  total?: number
}

type TenantPageItem = {
  id: number
  name: string
}

const iconUrls = [
  '/static/organization-bind/organization-logo-01.png',
  '/static/organization-bind/organization-logo-02.png',
  '/static/organization-bind/organization-logo-03.png',
  '/static/organization-bind/organization-logo-04.png',
  '/static/organization-bind/organization-logo-05.png'
]

const tagTones: OrganizationTagTone[] = ['blue', 'green', 'purple', 'orange', 'cyan']

const isSuccessCode = (code: number | string | undefined) => code === 0 || code === '0' || code === '00000'

const readErrorMessage = (body: CommonResult<unknown> | undefined, fallback: string) =>
  (body?.msg || body?.message || '').trim() || fallback

const toOrganizationSummary = (item: TenantPageItem, index: number): OrganizationSummary => ({
  id: String(item.id),
  tenantId: item.id,
  name: item.name || '未命名组织',
  province: '',
  city: '',
  memberCount: 0,
  tag: '企业组织',
  tagTone: tagTones[index % tagTones.length],
  applyMode: 'join',
  badgeText: (item.name || '').trim().slice(0, 1) || '组',
  iconUrl: iconUrls[index % iconUrls.length],
  contactName: '',
  contactMobile: ''
})

export const listApprovedOrganizations = async (keyword = ''): Promise<OrganizationSummary[]> => {
  const normalizedKeyword = keyword.trim()
  const query = buildQueryString({
    limit: '100',
    keyword: normalizedKeyword || undefined
  })

  return new Promise<OrganizationSummary[]>((resolve, reject) => {
    uni.request({
      url: `${getYjAppApiBaseUrl()}/app-api/yj/tenants?${query}`,
      method: 'GET',
      header: buildAuthHeader(),
      success: (response) => {
        const body = response.data as CommonResult<PageResult<TenantPageItem>>
        if (handleUnauthorizedResponse(body)) {
          reject(new Error(readErrorMessage(body, '登录状态已过期，请重新登录')))
          return
        }
        const list = Array.isArray(body?.data) ? body.data : body?.data?.list
        if (response.statusCode >= 200 && response.statusCode < 300 && isSuccessCode(body?.code) && Array.isArray(list)) {
          resolve(list.map(toOrganizationSummary))
          return
        }
        reject(new Error(readErrorMessage(body, '组织列表加载失败')))
      },
      fail: () => {
        reject(new Error('组织列表服务暂不可用，请稍后重试'))
      }
    })
  })
}
