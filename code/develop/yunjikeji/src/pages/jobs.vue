<template>
  <view class="jobs-page" :style="[$appSafeAreaStyle, jobsPageBackgroundStyle]" @tap="closePicker">
    <scroll-view
      class="jobs-scroll"
      scroll-y
      refresher-enabled
      refresher-default-style="black"
      refresher-background="#F7FAFE"
      :refresher-triggered="isRefreshing"
      lower-threshold="120"
      @refresherrefresh="refreshJobs"
      @scrolltolower="loadMoreJobs"
    >
      <view class="jobs-content">
        <view class="jobs-header">
          <button class="jobs-header__back" aria-label="返回" @tap="goBack">
            <uv-icon name="arrow-left" color="#001b3a" size="44rpx" />
          </button>
          <text class="jobs-header__title">岗位招聘</text>
        </view>

        <view class="jobs-filter" @tap.stop>
          <view
            class="jobs-filter__item"
            :class="{ 'jobs-filter__item--open': pickerType === 'keyword' }"
            @tap.stop="togglePicker('keyword')"
          >
            <text class="jobs-filter__label">关键词</text>
            <view class="jobs-filter__select">
              <text>{{ selectedKeywordLabel }}</text>
              <uv-icon name="arrow-down" color="#001b3a" size="28rpx" />
            </view>

            <view v-if="pickerType === 'keyword'" class="jobs-filter__dropdown">
              <view
                v-for="option in keywordOptions"
                :key="option.value || 'all'"
                class="jobs-filter__option"
                :class="{ 'jobs-filter__option--active': option.value === selectedKeyword }"
                @tap.stop="selectKeywordOption(option.value)"
              >
                <text>{{ option.label }}</text>
                <uv-icon
                  v-if="option.value === selectedKeyword"
                  name="checkmark"
                  color="#0878EE"
                  size="26rpx"
                />
              </view>
            </view>
          </view>

          <view
            class="jobs-filter__item"
            :class="{ 'jobs-filter__item--open': pickerType === 'workArea' }"
            @tap.stop="togglePicker('workArea')"
          >
            <text class="jobs-filter__label">地域</text>
            <view class="jobs-filter__select">
              <text>{{ selectedWorkAreaLabel }}</text>
              <uv-icon name="arrow-down" color="#001b3a" size="28rpx" />
            </view>

            <view v-if="pickerType === 'workArea'" class="jobs-filter__dropdown jobs-filter__dropdown--scrollable">
              <view
                v-for="option in workAreaOptions"
                :key="option.value || 'all'"
                class="jobs-filter__option"
                :class="{ 'jobs-filter__option--active': option.value === selectedWorkArea }"
                @tap.stop="selectWorkAreaOption(option.value)"
              >
                <text>{{ option.label }}</text>
                <uv-icon
                  v-if="option.value === selectedWorkArea"
                  name="checkmark"
                  color="#0878EE"
                  size="26rpx"
                />
              </view>
            </view>
          </view>

          <view
            class="jobs-filter__item"
            :class="{ 'jobs-filter__item--open': pickerType === 'salaryRange' }"
            @tap.stop="togglePicker('salaryRange')"
          >
            <text class="jobs-filter__label">工资区间</text>
            <view class="jobs-filter__select">
              <text>{{ selectedSalaryRangeLabel }}</text>
              <uv-icon name="arrow-down" color="#001b3a" size="28rpx" />
            </view>

            <view v-if="pickerType === 'salaryRange'" class="jobs-filter__dropdown">
              <view
                v-for="option in salaryRangeOptions"
                :key="option.value || 'all'"
                class="jobs-filter__option"
                :class="{ 'jobs-filter__option--active': option.value === selectedSalaryRange }"
                @tap.stop="selectSalaryRangeOption(option.value)"
              >
                <text>{{ option.label }}</text>
                <uv-icon
                  v-if="option.value === selectedSalaryRange"
                  name="checkmark"
                  color="#0878EE"
                  size="26rpx"
                />
              </view>
            </view>
          </view>
        </view>

        <view v-if="isRefreshing" class="refresh-loading">
          <view class="loading-spinner"></view>
          <text>正在刷新...</text>
        </view>

        <SelfTestLoadingOverlay
          :show="state.moduleStatus.jobs === 'loading'"
          title="正在加载岗位列表"
          message="请稍候，系统正在同步岗位信息。"
        />

        <AppStateView
          v-if="state.moduleStatus.jobs !== 'ready' && state.moduleStatus.jobs !== 'loading'"
          :status="state.moduleStatus.jobs"
          :title="stateTitle"
          :message="stateMessage"
          action-text="重新加载"
          @retry="loadJobs"
        />

        <view v-else class="job-list">
          <view
            v-for="job in jobs"
            :key="job.id"
            class="job-card"
          >
            <text class="job-type-label">{{ job.meta[0].text }}</text>
            <text class="job-title">{{ job.title }}</text>

            <text
              class="job-company"
              :class="{ 'job-company--expanded': expandedCompanyIds.has(job.id) }"
              hover-class="job-company--pressed"
              @tap.stop="toggleCompanyName(job)"
            >
              {{ job.company }}
            </text>

            <view class="meta-row">
              <text class="meta-item meta-item--source">{{ job.industry }}</text>
              <view class="meta-separator meta-separator--first"></view>
              <text class="meta-item meta-item--area">{{ job.address }}</text>
              <view class="meta-separator meta-separator--second"></view>
              <text class="meta-item meta-item--date">{{ job.meta[2].text }}</text>
            </view>

            <view class="job-card__divider"></view>

            <view class="salary" :class="{ 'salary--warm': job.salaryTone === 'warm' }">
              <text class="salary-main">{{ job.salary }}</text>
            </view>

            <view
              class="detail-button"
              hover-class="detail-button--pressed"
              @tap.stop="openJobDetail(job)"
            >
              <view class="detail-button__content">
                <text>查看详情</text>
                <uv-icon name="arrow-right" color="#005BD8" size="23rpx" />
              </view>
            </view>
          </view>

          <view v-if="isLoadingMore" class="list-loading">
            <view class="loading-spinner"></view>
            <text>正在加载更多...</text>
          </view>
        </view>

        <view v-if="state.moduleStatus.jobs === 'ready'" class="summary-card">
          <view class="summary-icon">
            <view class="summary-bar summary-bar--one"></view>
            <view class="summary-bar summary-bar--two"></view>
            <view class="summary-bar summary-bar--three"></view>
          </view>
          <view class="summary-copy">
            <text class="summary-title">本周岗位总结</text>
            <text class="summary-text">{{ summaryText }}</text>
          </view>
        </view>
      </view>
    </scroll-view>
    <OrganizationBindingRequiredDialog
      :visible="bindingRequiredDialogVisible"
      title="暂不可查看详情"
      description="请先绑定企业，绑定成功后即可查看招聘详情。"
      notice="绑定后也可使用所属企业提供的题库训练内容。"
      @cancel="closeBindingRequiredDialog"
      @close="closeBindingRequiredDialog"
      @service="openCustomerService"
      @bind="openOrganizationBinding"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppStateView from '@/components/AppStateView.vue'
import OrganizationBindingRequiredDialog from '@/components/OrganizationBindingRequiredDialog.vue'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import contourTopRightUrl from '@/static/jobs/contour-top-right.png'
import contourBottomLeftUrl from '@/static/jobs/contour-bottom-left.png'
import { appState as state, requireLogin, setModuleStatus } from '@/stores/appState'
import { fetchCurrentStudentAudit } from '@/services/customerAuth'
import { fetchJobPostPage, type JobPost } from '@/services/jobs'

type JobMeta = {
  icon: string
  text: string
}

type JobItem = {
  id: number
  title: string
  company: string
  industry: string
  salary: string
  salaryTone: 'blue' | 'warm'
  logoTone: 'blue' | 'deep' | 'sky'
  logoType: 'cloud' | 'wing' | 'sky'
  logoName: string
  meta: JobMeta[]
  address: string
  detailUrl: string
}

type JobFilterOption = {
  label: string
  value: string
}

type JobFilterPickerType = 'keyword' | 'workArea' | 'salaryRange' | ''

const keywordOptions: JobFilterOption[] = [
  { label: '全部', value: '' },
  { label: '飞手类', value: '飞手' },
  { label: '工程师类', value: '工程师' },
  { label: '教培类', value: '教培' },
  { label: '其他类', value: '__other__' }
]

const workAreaOptions: JobFilterOption[] = [
  { label: '全部', value: '' },
  ...[
    '北京市',
    '天津市',
    '上海市',
    '重庆市',
    '河北省',
    '山西省',
    '辽宁省',
    '吉林省',
    '黑龙江省',
    '江苏省',
    '浙江省',
    '安徽省',
    '福建省',
    '江西省',
    '山东省',
    '河南省',
    '湖北省',
    '湖南省',
    '广东省',
    '海南省',
    '四川省',
    '贵州省',
    '云南省',
    '陕西省',
    '甘肃省',
    '青海省',
    '台湾省',
    '内蒙古自治区',
    '广西壮族自治区',
    '西藏自治区',
    '宁夏回族自治区',
    '新疆维吾尔自治区',
    '香港特别行政区',
    '澳门特别行政区'
  ].map((value) => ({ label: value, value }))
]

const salaryRangeOptions: JobFilterOption[] = [
  { label: '全部', value: '' },
  { label: '0-3000', value: '0-3000' },
  { label: '3000-5000', value: '3000-5000' },
  { label: '5000-10000', value: '5000-10000' },
  { label: '10000-30000', value: '10000-30000' },
  { label: '30000-200000', value: '30000-200000' }
]

const jobs = ref<JobItem[]>([])
const jobTotal = ref(0)
const errorMessage = ref('')
const expandedCompanyIds = ref<Set<number>>(new Set())
const pageNo = ref(1)
const pageSize = ref(10)
const hasMore = ref(true)
const isLoadingMore = ref(false)
const isRefreshing = ref(false)
const isLoadingFirstPage = ref(false)
const bindingRequiredDialogVisible = ref(false)
const isCheckingJobAccess = ref(false)
const selectedKeyword = ref('')
const selectedWorkArea = ref('')
const selectedSalaryRange = ref('')
const pickerType = ref<JobFilterPickerType>('')
let hasRequestedInitialJobs = false
const MIN_REFRESH_VISIBLE_MS = 500
const MIN_LOAD_MORE_VISIBLE_MS = 400
const organizationBindingApproved = computed(() => state.organizationBinding.status === 'approved')
const jobsPageBackgroundStyle = {
  background: `
    url(${contourTopRightUrl}) right top / 288rpx auto no-repeat,
    url(${contourBottomLeftUrl}) left bottom / 413rpx auto no-repeat,
    linear-gradient(180deg, #F7FAFE 0%, #F7FAFE 64%, #F7FAFE 100%)
  `
}

const stateTitle = computed(() => {
  if (state.moduleStatus.jobs === 'loading') {
    return '正在同步岗位信息'
  }
  if (state.moduleStatus.jobs === 'empty') {
    return hasActiveFilters.value ? '暂无匹配岗位' : '暂无招聘岗位'
  }
  return '岗位信息暂不可用'
})

const stateMessage = computed(() => {
  if (state.moduleStatus.jobs === 'loading') {
    return '请稍候，系统正在从招聘接口获取最新岗位。'
  }
  if (state.moduleStatus.jobs === 'empty') {
    if (hasActiveFilters.value) {
      return '当前筛选条件下暂无匹配岗位，请切换条件后重试。'
    }
    return '当前还没有上架岗位，请稍后再来查看。'
  }
  return errorMessage.value || '岗位服务暂时无法返回，请稍后重试。'
})

const hasActiveFilters = computed(() =>
  Boolean(selectedKeyword.value || selectedWorkArea.value || selectedSalaryRange.value)
)

const selectedKeywordLabel = computed(() => {
  return keywordOptions.find((item) => item.value === selectedKeyword.value)?.label || '全部'
})

const selectedWorkAreaLabel = computed(() => {
  return workAreaOptions.find((item) => item.value === selectedWorkArea.value)?.label || '全部'
})

const selectedSalaryRangeLabel = computed(() => {
  return salaryRangeOptions.find((item) => item.value === selectedSalaryRange.value)?.label || '全部'
})

const summaryText = computed(() => {
  const count = jobTotal.value || jobs.value.length
  if (!count) {
    return '当前暂无可展示岗位。'
  }
  const areas = Array.from(new Set(jobs.value.map((job) => job.address).filter(Boolean))).slice(0, 3)
  const areaText = areas.length ? `，覆盖${areas.join('、')}等工作区域` : ''
  return `当前共获取到 ${count} 个在招岗位${areaText}。可根据薪资范围、工作地点与岗位来源，持续关注适合自己的无人机行业机会。`
})

onShow(() => {
  if (requireLogin() && !hasRequestedInitialJobs) {
    // Keeping the existing scroll-view and data prevents an external detail
    // page from resetting the user's position when the app returns to front.
    hasRequestedInitialJobs = true
    void loadJobs()
  }
})

function goBack() {
  uni.navigateBack({
    delta: 1,
    fail: () => {
      uni.reLaunch({ url: '/pages/home' })
    }
  })
}

async function loadJobs() {
  if (isLoadingFirstPage.value || isLoadingMore.value || isRefreshing.value) {
    return
  }

  isLoadingFirstPage.value = true
  pageNo.value = 1
  hasMore.value = true
  setModuleStatus('jobs', 'loading')
  errorMessage.value = ''

  try {
    const result = await fetchJobPostPage(buildJobQueryParams(1))
    applyJobPage(result.list, result.total, 'replace')
    expandedCompanyIds.value = new Set()
    setModuleStatus('jobs', jobs.value.length ? 'ready' : 'empty')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '岗位信息加载失败'
    setModuleStatus('jobs', 'error')
  } finally {
    isLoadingFirstPage.value = false
  }
}

async function loadMoreJobs() {
  if (!hasMore.value || isLoadingMore.value || isLoadingFirstPage.value || isRefreshing.value) {
    return
  }

  isLoadingMore.value = true
  const loadingStartedAt = Date.now()
  const nextPageNo = pageNo.value + 1

  try {
    const result = await fetchJobPostPage(buildJobQueryParams(nextPageNo))
    pageNo.value = nextPageNo
    applyJobPage(result.list, result.total, 'append')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '岗位信息加载失败'
    uni.showToast({
      title: errorMessage.value,
      icon: 'none'
    })
  } finally {
    await waitForLoadingVisibleTime(loadingStartedAt, MIN_LOAD_MORE_VISIBLE_MS)
    isLoadingMore.value = false
  }
}

async function refreshJobs() {
  if (isRefreshing.value || isLoadingFirstPage.value || isLoadingMore.value) {
    uni.stopPullDownRefresh()
    return
  }

  const refreshStartedAt = Date.now()
  const previousPageNo = pageNo.value
  const previousHasMore = hasMore.value
  isRefreshing.value = true
  pageNo.value = 1
  hasMore.value = true
  errorMessage.value = ''

  try {
    const result = await fetchJobPostPage(buildJobQueryParams(1))
    applyJobPage(result.list, result.total, 'replace')
    expandedCompanyIds.value = new Set()
    setModuleStatus('jobs', jobs.value.length ? 'ready' : 'empty')
  } catch (error) {
    pageNo.value = previousPageNo
    hasMore.value = previousHasMore
    errorMessage.value = error instanceof Error ? error.message : '岗位信息加载失败'
    setModuleStatus('jobs', jobs.value.length ? 'ready' : 'error')
    uni.showToast({
      title: errorMessage.value,
      icon: 'none'
    })
  } finally {
    await waitForLoadingVisibleTime(refreshStartedAt, MIN_REFRESH_VISIBLE_MS)
    isRefreshing.value = false
    uni.stopPullDownRefresh()
  }
}

function applyJobPage(list: JobPost[], total: number, mode: 'replace' | 'append') {
  const nextItems = list.map(toJobItem)
  jobs.value = mode === 'replace' ? nextItems : [...jobs.value, ...nextItems]
  jobTotal.value = total || jobs.value.length
  hasMore.value = jobs.value.length < jobTotal.value && list.length >= pageSize.value
}

function buildJobQueryParams(targetPageNo: number) {
  return {
    pageNo: targetPageNo,
    pageSize: pageSize.value,
    status: true,
    name: selectedKeyword.value || undefined,
    workArea: selectedWorkArea.value || undefined,
    salaryRange: selectedSalaryRange.value || undefined
  }
}

function waitForLoadingVisibleTime(startedAt: number, minVisibleMs: number) {
  const elapsed = Date.now() - startedAt
  const remaining = minVisibleMs - elapsed
  if (remaining <= 0) {
    return Promise.resolve()
  }
  return new Promise<void>((resolve) => {
    setTimeout(resolve, remaining)
  })
}

function toJobItem(post: JobPost): JobItem {
  const company = normalizeText(post.companyName, '招聘企业')
  const sourceText = formatSource(post.sourceCode)
  const publishDate = normalizeText(post.publishDate, '发布时间待定')
  const workArea = normalizeText(post.workArea, '工作地点待定')

  return {
    id: post.id,
    title: normalizeText(post.name, '未命名岗位'),
    company,
    industry: sourceText,
    salary: normalizeText(post.salaryRange, '薪资面议'),
    salaryTone: readSalaryTone(post.salaryRange),
    logoTone: readLogoTone(post.id),
    logoType: readLogoType(post.id),
    logoName: company,
    meta: [
      { icon: 'bag', text: '招聘岗位' },
      { icon: 'checkmark-circle', text: sourceText },
      { icon: 'tags', text: publishDate }
    ],
    address: workArea,
    detailUrl: post.detailUrl || ''
  }
}

function togglePicker(type: JobFilterPickerType) {
  pickerType.value = pickerType.value === type ? '' : type
}

function closePicker() {
  pickerType.value = ''
}

function selectKeywordOption(value: string) {
  if (selectedKeyword.value === value) {
    closePicker()
    return
  }
  selectedKeyword.value = value
  closePicker()
  void loadJobs()
}

function selectWorkAreaOption(value: string) {
  if (selectedWorkArea.value === value) {
    closePicker()
    return
  }
  selectedWorkArea.value = value
  closePicker()
  void loadJobs()
}

function selectSalaryRangeOption(value: string) {
  if (selectedSalaryRange.value === value) {
    closePicker()
    return
  }
  selectedSalaryRange.value = value
  closePicker()
  void loadJobs()
}

async function openJobDetail(job: JobItem) {
  if (isCheckingJobAccess.value || bindingRequiredDialogVisible.value) {
    return
  }

  isCheckingJobAccess.value = true
  try {
    const studentAudit = await fetchCurrentStudentAudit()
    if (studentAudit?.auditStatus === 2) {
      openExternalJobDetail(job)
      return
    }
    bindingRequiredDialogVisible.value = true
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '组织申请状态加载失败',
      icon: 'none'
    })
  } finally {
    isCheckingJobAccess.value = false
  }
}

function openExternalJobDetail(job: JobItem) {
  const detailUrl = normalizeExternalUrl(job.detailUrl)
  if (!detailUrl) {
    uni.showToast({
      title: '暂无岗位详情链接',
      icon: 'none'
    })
    return
  }

  const runtime = globalThis as typeof globalThis & {
    plus?: {
      runtime?: {
        openURL?: (url: string) => void
      }
    }
    window?: Window
  }

  if (runtime.plus?.runtime?.openURL) {
    runtime.plus.runtime.openURL(detailUrl)
    return
  }

  if (typeof window !== 'undefined' && window.open) {
    window.open(detailUrl, '_blank')
    return
  }

  uni.setClipboardData({
    data: detailUrl,
    success: () => {
      uni.showToast({
        title: '链接已复制',
        icon: 'none'
      })
    }
  })
}

function closeBindingRequiredDialog() {
  bindingRequiredDialogVisible.value = false
}

function openCustomerService() {
  closeBindingRequiredDialog()
  uni.navigateTo({
    url: '/pages/service/customer-service-chat?conversationId=default'
  })
}

function openOrganizationBinding() {
  closeBindingRequiredDialog()
  uni.navigateTo({
    url: '/pages/enterprise/organization-bind?entry=direct'
  })
}

function toggleCompanyName(job: JobItem) {
  const nextExpandedCompanyIds = new Set(expandedCompanyIds.value)
  if (nextExpandedCompanyIds.has(job.id)) {
    nextExpandedCompanyIds.delete(job.id)
  } else {
    nextExpandedCompanyIds.add(job.id)
  }
  expandedCompanyIds.value = nextExpandedCompanyIds
}

function normalizeExternalUrl(url: string) {
  const trimmedUrl = url.trim()
  if (!trimmedUrl) {
    return ''
  }
  if (/^https?:\/\//i.test(trimmedUrl)) {
    return trimmedUrl
  }
  if (/^[\w.-]+\.[a-z]{2,}(\/|$)/i.test(trimmedUrl)) {
    return `https://${trimmedUrl}`
  }
  return ''
}

function normalizeText(value: string | undefined | null, fallback: string) {
  return value?.trim() || fallback
}

function formatSource(sourceCode: string | undefined | null) {
  if (!organizationBindingApproved.value) {
    return '***'
  }
  const sourceMap: Record<string, string> = {
    boss_zhipin: 'BOSS直聘',
    liepin: '猎聘',
    zhilian: '智联招聘',
    guopin: '国聘',
    '51job': '前程无忧'
  }
  const code = sourceCode?.trim()
  return code ? sourceMap[code] || code : '岗位来源'
}

function readSalaryTone(salaryRange: string | undefined | null): JobItem['salaryTone'] {
  return salaryRange?.includes('面议') ? 'warm' : 'blue'
}

function readLogoTone(id: number): JobItem['logoTone'] {
  const tones: JobItem['logoTone'][] = ['blue', 'deep', 'sky']
  return tones[Math.abs(id) % tones.length]
}

function readLogoType(id: number): JobItem['logoType'] {
  const types: JobItem['logoType'][] = ['cloud', 'wing', 'sky']
  return types[Math.abs(id) % types.length]
}
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #F7FAFE;
}

button::after {
  border: 0;
}

.jobs-page {
  position: relative;
  height: 100vh;
  overflow: hidden;
  color: #001b3a;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  letter-spacing: 0;
}

.jobs-scroll {
  position: relative;
  z-index: 1;
  height: 100vh;
}

.jobs-content {
  box-sizing: border-box;
  display: flex;
  min-height: 100vh;
  flex-direction: column;
  gap: 0;
  padding: 0 40rpx calc(env(safe-area-inset-bottom) + 40rpx);
}

.jobs-header {
  position: relative;
  flex: 0 0 calc(var(--app-safe-area-top) + 107rpx);
  height: calc(var(--app-safe-area-top) + 107rpx);
}

.jobs-header__back {
  position: absolute;
  top: var(--app-safe-area-top);
  left: -22rpx;
  box-sizing: border-box;
  width: 72rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 0;
  background: transparent;
  line-height: 1;
}

.jobs-header__back:active {
  opacity: 0.68;
}

.jobs-header__title {
  position: absolute;
  top: calc(var(--app-safe-area-top) + 2rpx);
  left: 50%;
  display: block;
  color: #001b3a;
  font-size: 40rpx;
  font-weight: 600;
  line-height: 56rpx;
  white-space: nowrap;
  transform: translateX(-50%);
}

.jobs-filter {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 0 0 24rpx;
  padding: 24rpx 20rpx 22rpx;
  border: 1rpx solid rgba(211, 224, 237, 0.72);
  border-radius: 24rpx;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 8rpx 24rpx rgba(17, 43, 74, 0.08);
}

.jobs-filter__item {
  position: relative;
  min-width: 0;
  padding: 0 16rpx;
}

.jobs-filter__item + .jobs-filter__item {
  border-left: 1rpx solid rgba(216, 228, 240, 0.88);
}

.jobs-filter__item--open {
  z-index: 10;
}

.jobs-filter__label {
  display: block;
  color: #61707f;
  font-size: 22rpx;
  line-height: 32rpx;
}

.jobs-filter__select {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8rpx;
  margin-top: 10rpx;
  color: #001b3a;
}

.jobs-filter__select text {
  min-width: 0;
  overflow: hidden;
  font-size: 26rpx;
  font-weight: 600;
  line-height: 38rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.jobs-filter__dropdown {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 16rpx);
  max-height: 420rpx;
  overflow-y: auto;
  border: 1rpx solid rgba(217, 229, 241, 0.98);
  border-radius: 16rpx;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 18rpx 40rpx rgba(17, 43, 74, 0.14);
}

.jobs-filter__dropdown--scrollable {
  max-height: 520rpx;
}

.jobs-filter__option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10rpx;
  min-height: 72rpx;
  padding: 0 18rpx;
  color: #001b3a;
  font-size: 23rpx;
  font-weight: 600;
  line-height: 1.2;
  background: #fff;
}

.jobs-filter__option + .jobs-filter__option {
  border-top: 1rpx solid rgba(230, 238, 247, 0.98);
}

.jobs-filter__option--active {
  color: #0878EE;
  background: #F1F7FD;
}

.jobs-filter__option text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 26rpx;
}

.refresh-loading,
.list-loading {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12rpx;
  min-height: 72rpx;
  color: #31505b;
}

.refresh-loading {
  margin: -8rpx 0 20rpx;
}

.list-loading {
  padding: 20rpx 0;
}

.refresh-loading text,
.list-loading text {
  display: block;
  font-size: 22rpx;
  line-height: 1;
  font-weight: 500;
}

.loading-spinner {
  width: 28rpx;
  height: 28rpx;
  border-radius: 50%;
  border: 4rpx solid rgba(0, 91, 216, 0.16);
  border-top-color: #005BD8;
  animation: jobs-loading-rotate 0.78s linear infinite;
}

@keyframes jobs-loading-rotate {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

.job-card {
  position: relative;
  box-sizing: border-box;
  min-height: 376rpx;
  overflow: hidden;
  padding: 32rpx 34rpx 28rpx;
  border: 1rpx solid rgba(233, 233, 233, 0.72);
  border-radius: 18rpx;
  background: #fff;
  box-shadow: 0 6rpx 18rpx rgba(17, 43, 74, 0.08);
}

.job-type-label {
  position: absolute;
  top: 32rpx;
  right: 32rpx;
  box-sizing: border-box;
  width: 120rpx;
  height: 50rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2rpx solid #B7D9FA;
  border-radius: 8rpx;
  color: #0b3150;
  font-size: 28rpx;
  font-weight: 400;
  line-height: 46rpx;
  white-space: nowrap;
}

.job-title {
  display: block;
  max-width: calc(100% - 146rpx);
  overflow: hidden;
  color: #001b3a;
  font-size: 42rpx;
  font-weight: 600;
  line-height: 56rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-company {
  display: block;
  max-width: 100%;
  margin-top: 12rpx;
  overflow: hidden;
  color: #001b3a;
  font-size: 30rpx;
  font-weight: 400;
  line-height: 42rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-company--pressed {
  opacity: 0.72;
}

.job-company--expanded {
  overflow: visible;
  text-overflow: clip;
  white-space: normal;
  word-break: break-all;
}

.meta-row {
  position: relative;
  display: block;
  height: 36rpx;
  min-width: 0;
  margin: 40rpx 0 0;
}

.meta-item {
  position: absolute;
  top: 0;
  display: block;
  overflow: hidden;
  color: #001b3a;
  font-size: 26rpx;
  font-weight: 400;
  line-height: 36rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-item--source {
  left: 0;
  width: 106rpx;
}

.meta-item--area {
  left: 167rpx;
  width: 110rpx;
}

.meta-item--date {
  left: 320rpx;
  right: 0;
}

.meta-separator {
  position: absolute;
  top: 5rpx;
  width: 2rpx;
  height: 26rpx;
  margin: 0;
  background: #e9e9e9;
}

.meta-separator--first {
  left: 120rpx;
}

.meta-separator--second {
  left: 291rpx;
}

.job-card__divider {
  width: 100%;
  height: 2rpx;
  margin-top: 28rpx;
  background: #e9e9e9;
}

.salary,
.salary--warm {
  display: flex;
  align-items: baseline;
  margin-top: 35rpx;
  padding: 0;
  color: #005BD8;
  white-space: nowrap;
}

.salary-main {
  display: block;
  color: #005BD8;
  font-size: 40rpx;
  font-weight: 600;
  line-height: 54rpx;
}

.detail-button {
  position: absolute;
  right: 32rpx;
  bottom: 40rpx;
  box-sizing: border-box;
  width: 163rpx;
  min-width: 163rpx;
  height: 61rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 0;
  border: 2rpx solid #005BD8;
  border-radius: 9rpx;
  background: #fff;
  box-shadow: none;
}

.detail-button__content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10rpx;
}

.detail-button--pressed {
  opacity: 0.76;
  transform: translateY(1rpx);
}

.detail-button text {
  display: block;
  color: #005BD8;
  font-size: 25rpx;
  font-weight: 500;
  line-height: 59rpx;
  white-space: nowrap;
}

.summary-card {
  display: none !important;
}

@media (max-width: 360px) {
  .jobs-filter {
    padding-left: 16rpx;
    padding-right: 16rpx;
  }

  .jobs-filter__item {
    padding-left: 10rpx;
    padding-right: 10rpx;
  }

  .jobs-filter__select text {
    font-size: 24rpx;
  }

  .jobs-filter__option {
    padding-left: 14rpx;
    padding-right: 14rpx;
    font-size: 21rpx;
  }

  .meta-item--date {
    right: -8rpx;
  }
}
</style>
