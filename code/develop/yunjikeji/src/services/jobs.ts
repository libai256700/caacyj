import { getYjAppApiBaseUrl } from './apiBase'
import { buildAuthHeader, handleUnauthorizedResponse } from './request'
import { buildQueryString } from './url'

type CommonResult<T> = {
  code: number | string
  msg?: string
  message?: string
  data?: T
}

export type JobPost = {
  id: number
  name: string
  companyName: string
  sourceCode: string
  externalPostId: string
  salaryRange: string
  workArea: string
  publishDate: string
  detailUrl: string
  status: boolean
  createTime: string | number
}

export type JobPostPage = {
  list: JobPost[]
  total: number
}

export type JobPostPageParams = {
  pageNo?: number
  pageSize?: number
  keyword?: string
  name?: string
  sourceCode?: string
  workArea?: string
  salaryRange?: string
  status?: boolean
}

const JOB_POST_BASE = '/app-api/yj/posts'
const ALL_JOBS_PAGE_SIZE = 100

const isSuccessCode = (code: number | string | undefined) => code === 0 || code === '0' || code === '00000'

const readErrorMessage = (body: CommonResult<unknown> | undefined, fallback: string) => {
  const message = body?.msg || body?.message || ''
  return message.trim() || fallback
}

export const fetchJobPostPage = (params: JobPostPageParams = {}) => {
  return new Promise<JobPostPage>((resolve, reject) => {
    uni.request({
      url: `${getYjAppApiBaseUrl()}${JOB_POST_BASE}?${buildQueryString({
        pageNo: 1,
        pageSize: 10,
        status: true,
        ...params
      })}`,
      method: 'GET',
      header: {
        ...buildAuthHeader()
      },
      success: (response) => {
        const body = response.data as CommonResult<JobPostPage>
        if (handleUnauthorizedResponse(body)) {
          reject(new Error(readErrorMessage(body, '登录状态已过期，请重新登录')))
          return
        }
        if (response.statusCode >= 200 && response.statusCode < 300 && isSuccessCode(body?.code) && body.data) {
          resolve(body.data)
          return
        }
        reject(new Error(readErrorMessage(body, '岗位信息加载失败')))
      },
      fail: (error) => {
        const errMsg = typeof error?.errMsg === 'string' ? error.errMsg : ''
        if (errMsg.includes('timeout')) {
          reject(new Error('岗位服务响应超时，请稍后重试'))
          return
        }
        reject(new Error('岗位服务暂不可用，请检查接口配置或后端服务'))
      }
    })
  })
}

export const fetchAllJobPosts = async (params: Omit<JobPostPageParams, 'pageNo'> = {}) => {
  const pageSize = params.pageSize || ALL_JOBS_PAGE_SIZE
  const baseParams = {
    ...params,
    pageSize
  }
  const firstPage = await fetchJobPostPage({
    ...baseParams,
    pageNo: 1
  })
  const total = firstPage.total || firstPage.list.length

  if (firstPage.list.length >= total) {
    return firstPage
  }

  const effectivePageSize = firstPage.list.length || pageSize
  const pageCount = Math.ceil(total / effectivePageSize)
  const restPosts: JobPost[] = []

  for (let pageNo = 2; pageNo <= pageCount; pageNo += 1) {
    const page = await fetchJobPostPage({
      ...baseParams,
      pageNo
    })
    restPosts.push(...page.list)
  }

  return {
    list: [...firstPage.list, ...restPosts],
    total
  }
}
