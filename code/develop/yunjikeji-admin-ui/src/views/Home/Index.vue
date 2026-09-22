<template>
  <div v-if="isTenantOne" class="home-dashboard">
    <div class="dashboard-toolbar">
      <div>
        <div class="dashboard-title">管理首页</div>
        <div class="dashboard-subtitle">学员活跃、注册、知识图谱与做题情况</div>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col
        v-for="item in statCards"
        :key="item.key"
        :xl="6"
        :lg="6"
        :md="12"
        :sm="12"
        :xs="24"
      >
        <el-card class="metric-card" shadow="never">
          <el-skeleton :loading="summaryLoading || practiceLoading" :rows="2" animated>
            <div class="metric-card__body">
              <div class="metric-card__icon" :style="{ color: item.color, background: item.bg }">
                <Icon :icon="item.icon" :size="24" />
              </div>
              <div class="metric-card__content">
                <div class="metric-card__label">{{ item.label }}</div>
                <CountTo
                  class="metric-card__value"
                  :start-val="0"
                  :end-val="item.value"
                  :duration="900"
                />
              </div>
              <div class="metric-card__secondary">
                <span class="metric-card__secondary-label">{{ item.secondaryLabel }}:</span>
                <span class="metric-card__secondary-value">
                  {{ formatNumber(item.secondaryValue) }}
                </span>
              </div>
            </div>
          </el-skeleton>
        </el-card>
      </el-col>
    </el-row>

    <el-alert
      v-if="summaryError || trendError || practiceError"
      class="dashboard-alert"
      type="warning"
      show-icon
      :closable="false"
      title="部分首页数据加载失败，已显示空数据"
    />

    <div class="chart-toolbar">
      <el-date-picker
        class="home-date-range"
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        :clearable="false"
        :disabled-date="disabledFutureDate"
        @change="handleDateRangeChange"
      />
      <el-button :loading="trendLoading || practiceLoading" type="primary" @click="loadCharts">
        刷新
      </el-button>
    </div>

    <el-row :gutter="16">
      <el-col :xl="6" :lg="6" :md="12" :sm="24" :xs="24">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <div class="chart-card__header">
              <span>登录趋势</span>
              <el-tag v-if="loginTrendError" type="warning" effect="plain">加载失败</el-tag>
            </div>
          </template>
          <el-skeleton :loading="trendLoading" animated>
            <Echart :options="loginTrendOptions" height="300px" />
          </el-skeleton>
        </el-card>
      </el-col>

      <el-col :xl="6" :lg="6" :md="12" :sm="24" :xs="24">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <div class="chart-card__header">
              <span>注册趋势</span>
              <el-tag v-if="registerTrendError" type="warning" effect="plain">加载失败</el-tag>
            </div>
          </template>
          <el-skeleton :loading="trendLoading" animated>
            <Echart :options="registerTrendOptions" height="300px" />
          </el-skeleton>
        </el-card>
      </el-col>

      <el-col :xl="6" :lg="6" :md="12" :sm="24" :xs="24">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <div class="chart-card__header">
              <span>知识图谱调用趋势</span>
              <el-tag v-if="knowledgeTrendError" type="warning" effect="plain">加载失败</el-tag>
            </div>
          </template>
          <el-skeleton :loading="trendLoading" animated>
            <Echart :options="knowledgeTrendOptions" height="300px" />
          </el-skeleton>
        </el-card>
      </el-col>

      <el-col :xl="6" :lg="6" :md="12" :sm="24" :xs="24">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <div class="chart-card__header">
              <span>学员答题趋势</span>
              <el-tag v-if="practiceTrendError" type="warning" effect="plain">加载失败</el-tag>
            </div>
          </template>
          <el-skeleton :loading="practiceLoading" animated>
            <Echart :options="practiceTrendOptions" height="300px" />
          </el-skeleton>
        </el-card>
      </el-col>
    </el-row>
  </div>

  <div v-else class="home-welcome">
    欢迎你，{{ welcomeName }}.
  </div>
</template>

<script lang="ts" setup>
import dayjs from 'dayjs'
import type { EChartsOption } from 'echarts'
import { useUserStore } from '@/store/modules/user'
import { getTenantId } from '@/utils/auth'
import {
  HomeApi,
  type HomeMetricRespVO,
  type HomePracticeRespVO,
  type HomeSummaryRespVO,
  type HomeTrendPoint,
  type HomeTrendRespVO
} from '@/api/yj/home'
import { createLineChartOptions, type ChartPoint } from './echarts-data'

defineOptions({ name: 'Index' })

const userStore = useUserStore()
const isTenantOne = computed(() => Number(getTenantId()) === 1)
const welcomeName = computed(() => userStore.user.nickname || '用户')

interface HomeSummaryView {
  activeUserCount: number
  totalLoginCount: number
  todayRegisterCount: number
  registerTotalCount: number
  knowledgeCallTotalCount: number
  todayKnowledgeCallCount: number
}

interface HomePracticeView {
  todayAnswerCount: number
  answerTotal: number
}

const emptySummary = (): HomeSummaryView => ({
  activeUserCount: 0,
  totalLoginCount: 0,
  todayRegisterCount: 0,
  registerTotalCount: 0,
  knowledgeCallTotalCount: 0,
  todayKnowledgeCallCount: 0
})

const emptyPractice = (): HomePracticeView => ({
  todayAnswerCount: 0,
  answerTotal: 0
})

const defaultDateRange = (): [string, string] => [
  dayjs().subtract(6, 'day').format('YYYY-MM-DD'),
  dayjs().format('YYYY-MM-DD')
]

const summary = reactive<HomeSummaryView>(emptySummary())
const practice = reactive<HomePracticeView>(emptyPractice())
const dateRange = ref<[string, string]>(defaultDateRange())
const loginTrend = ref<ChartPoint[]>([])
const registerTrend = ref<ChartPoint[]>([])
const knowledgeTrend = ref<ChartPoint[]>([])
const practiceTrend = ref<ChartPoint[]>([])

const summaryLoading = ref(false)
const trendLoading = ref(false)
const practiceLoading = ref(false)
const summaryError = ref(false)
const practiceError = ref(false)
const loginTrendError = ref(false)
const registerTrendError = ref(false)
const knowledgeTrendError = ref(false)
const practiceTrendError = ref(false)

const trendError = computed(
  () => loginTrendError.value || registerTrendError.value || knowledgeTrendError.value
)

const statCards = computed(() => [
  {
    key: 'activeUserCount',
    label: '当天活跃人数',
    value: summary.activeUserCount,
    secondaryLabel: '登录总次数',
    secondaryValue: summary.totalLoginCount,
    icon: 'ep:user-filled',
    color: '#0f766e',
    bg: '#ccfbf1'
  },
  {
    key: 'todayRegisterCount',
    label: '当天注册数',
    value: summary.todayRegisterCount,
    secondaryLabel: '注册总数',
    secondaryValue: summary.registerTotalCount,
    icon: 'ep:user',
    color: '#16a34a',
    bg: '#dcfce7'
  },
  {
    key: 'todayKnowledgeCallCount',
    label: '当天知识图谱调用数',
    value: summary.todayKnowledgeCallCount,
    secondaryLabel: '知识图谱调用总数',
    secondaryValue: summary.knowledgeCallTotalCount,
    icon: 'ep:data-analysis',
    color: '#be123c',
    bg: '#ffe4e6'
  },
  {
    key: 'todayAnswerCount',
    label: '学员当天答题数',
    value: practice.todayAnswerCount,
    secondaryLabel: '答题总数',
    secondaryValue: practice.answerTotal,
    icon: 'ep:document-checked',
    color: '#0369a1',
    bg: '#e0f2fe'
  }
])

const loginTrendOptions = computed<EChartsOption>(() =>
  createLineChartOptions('登录趋势', '登录次数', loginTrend.value, '#2563eb')
)
const registerTrendOptions = computed<EChartsOption>(() =>
  createLineChartOptions('注册趋势', '注册人数', registerTrend.value, '#16a34a')
)
const knowledgeTrendOptions = computed<EChartsOption>(() =>
  createLineChartOptions('知识图谱调用趋势', '调用次数', knowledgeTrend.value, '#c2410c')
)
const practiceTrendOptions = computed<EChartsOption>(() =>
  createLineChartOptions('学员答题趋势', '答题数', practiceTrend.value, '#0369a1')
)

const toNumber = (value: unknown) => {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : 0
}

const readNumber = (source: Record<string, unknown>, keys: string[]) => {
  const key = keys.find((item) => source[item] !== undefined && source[item] !== null)
  return key ? toNumber(source[key]) : 0
}

const normalizeMetric = (data: HomeMetricRespVO | undefined, keys: string[]) => {
  if (typeof data === 'number' || typeof data === 'string') {
    return toNumber(data)
  }
  const record = (data || {}) as Record<string, unknown>
  return readNumber(record, ['value', 'count', 'total', 'num', ...keys])
}

const getListPayload = (payload: unknown): Record<string, unknown>[] => {
  if (Array.isArray(payload)) {
    return payload as Record<string, unknown>[]
  }
  if (!payload || typeof payload !== 'object') {
    return []
  }
  const record = payload as Record<string, unknown>
  const list = record.list || record.items || record.data || record.records
  return Array.isArray(list) ? (list as Record<string, unknown>[]) : []
}

const normalizeSummary = (data: HomeSummaryRespVO | undefined): HomeSummaryView => {
  const record = (data || {}) as Record<string, unknown>
  return {
    activeUserCount: readNumber(record, [
      'todayActiveUserCount',
      'activeUserCount',
      'activeUsers',
      'activeUserTotal'
    ]),
    totalLoginCount: readNumber(record, ['todayLoginCount', 'totalLoginCount', 'loginTotalCount', 'loginCount']),
    todayRegisterCount: readNumber(record, ['todayRegisterCount', 'registerTodayCount']),
    registerTotalCount: readNumber(record, ['totalRegisterCount', 'registerTotalCount']),
    knowledgeCallTotalCount: readNumber(record, [
      'totalKnowledgeCallCount',
      'knowledgeCallTotalCount',
      'knowledgeTotalCount'
    ]),
    todayKnowledgeCallCount: readNumber(record, [
      'todayKnowledgeCallCount',
      'knowledgeCallTodayCount',
      'knowledgeTodayCount'
    ])
  }
}

const normalizeTrend = (data: HomeTrendRespVO | HomeTrendPoint[] | undefined, keys: string[]) => {
  const record = (data || {}) as Record<string, unknown>
  if (Array.isArray(record.dates) && Array.isArray(record.values)) {
    return record.dates.map((date, index) => ({
      name: String(date),
      value: toNumber((record.values as unknown[])[index])
    }))
  }

  return getListPayload(data).map((item) => ({
    name: String(item.date || item.day || item.statDate || item.name || ''),
    value: readNumber(item, keys)
  }))
}

const normalizePractice = (data: HomePracticeRespVO | PracticeChartItem[] | undefined) => {
  const record = Array.isArray(data) ? { items: data } : ((data || {}) as Record<string, unknown>)
  const todayAnswerCount = readNumber(record, [
    'todayAnsweredQuestionCount',
    'todayAnswerCount',
    'answerTodayCount',
    'answeredTodayCount'
  ])
  const rangeAnswerTotal = readNumber(record, [
    'answeredQuestionCount',
    'answerRangeTotal',
    'rangeAnsweredQuestionCount'
  ])
  const answerTotal = readNumber(record, [
    'totalAnsweredQuestionCount',
    'answerTotal',
    'answeredTotal',
    'questionAnswerTotal',
    'answeredQuestionCount'
  ])

  return {
    todayAnswerCount,
    answerTotal
  }
}

const resetSummary = () => {
  Object.assign(summary, emptySummary())
}

const resetPractice = () => {
  Object.assign(practice, emptyPractice())
}

const getTrendParams = () => ({
  startDate: dateRange.value[0],
  endDate: dateRange.value[1]
})

const loadSummary = async () => {
  summaryLoading.value = true
  summaryError.value = false
  try {
    const [
      overviewResult,
      activeUsersResult,
      loginsTodayResult,
      registersTodayResult,
      registersTotalResult,
      knowledgeTodayResult,
      knowledgeTotalResult
    ] = await Promise.allSettled([
      HomeApi.getSummary(),
      HomeApi.getActiveUsersToday(),
      HomeApi.getLoginsToday(),
      HomeApi.getRegistersToday(),
      HomeApi.getRegistersTotal(),
      HomeApi.getKnowledgeCallsToday(),
      HomeApi.getKnowledgeCallsTotal()
    ])
    const nextSummary =
      overviewResult.status === 'fulfilled' ? normalizeSummary(overviewResult.value) : emptySummary()

    if (activeUsersResult.status === 'fulfilled') {
      nextSummary.activeUserCount = normalizeMetric(activeUsersResult.value, [
        'todayActiveUserCount',
        'activeUserCount',
        'activeUsers',
        'activeUserTotal'
      ])
    }
    if (loginsTodayResult.status === 'fulfilled') {
      nextSummary.totalLoginCount = normalizeMetric(loginsTodayResult.value, [
        'todayLoginCount',
        'totalLoginCount',
        'loginTotalCount',
        'loginCount'
      ])
    }
    if (registersTodayResult.status === 'fulfilled') {
      nextSummary.todayRegisterCount = normalizeMetric(registersTodayResult.value, [
        'todayRegisterCount',
        'registerTodayCount'
      ])
    }
    if (registersTotalResult.status === 'fulfilled') {
      nextSummary.registerTotalCount = normalizeMetric(registersTotalResult.value, [
        'registerTotalCount',
        'totalRegisterCount'
      ])
    }
    if (knowledgeTodayResult.status === 'fulfilled') {
      nextSummary.todayKnowledgeCallCount = normalizeMetric(knowledgeTodayResult.value, [
        'todayKnowledgeCallCount',
        'knowledgeCallTodayCount',
        'knowledgeTodayCount'
      ])
    }
    if (knowledgeTotalResult.status === 'fulfilled') {
      nextSummary.knowledgeCallTotalCount = normalizeMetric(knowledgeTotalResult.value, [
        'knowledgeCallTotalCount',
        'totalKnowledgeCallCount',
        'knowledgeTotalCount'
      ])
    }

    Object.assign(summary, nextSummary)
    summaryError.value = [
      overviewResult,
      activeUsersResult,
      loginsTodayResult,
      registersTodayResult,
      registersTotalResult,
      knowledgeTodayResult,
      knowledgeTotalResult
    ].some((item) => item.status === 'rejected')
    if (summaryError.value) {
      ElMessage.error('首页概览加载失败')
    }
  } catch (error) {
    resetSummary()
    summaryError.value = true
    ElMessage.error('首页概览加载失败')
  } finally {
    summaryLoading.value = false
  }
}

const loadTrends = async () => {
  trendLoading.value = true
  loginTrendError.value = false
  registerTrendError.value = false
  knowledgeTrendError.value = false
  const params = getTrendParams()
  const [loginResult, registerResult, knowledgeResult] = await Promise.allSettled([
    HomeApi.getLoginTrend(params),
    HomeApi.getRegisterTrend(params),
    HomeApi.getKnowledgeTrend(params)
  ])

  if (loginResult.status === 'fulfilled') {
    loginTrend.value = normalizeTrend(loginResult.value, ['loginCount', 'totalLoginCount', 'value', 'count'])
  } else {
    loginTrend.value = []
    loginTrendError.value = true
    console.error('登录趋势加载失败', loginResult.reason)
  }

  if (registerResult.status === 'fulfilled') {
    registerTrend.value = normalizeTrend(registerResult.value, [
      'registerCount',
      'todayRegisterCount',
      'value',
      'count'
    ])
  } else {
    registerTrend.value = []
    registerTrendError.value = true
    console.error('注册趋势加载失败', registerResult.reason)
  }

  if (knowledgeResult.status === 'fulfilled') {
    knowledgeTrend.value = normalizeTrend(knowledgeResult.value, [
      'knowledgeCallCount',
      'callCount',
      'value',
      'count'
    ])
  } else {
    knowledgeTrend.value = []
    knowledgeTrendError.value = true
    console.error('知识图谱调用趋势加载失败', knowledgeResult.reason)
  }

  if (trendError.value) {
    ElMessage.error('趋势数据加载失败')
  }
  trendLoading.value = false
}

const loadPractice = async () => {
  practiceLoading.value = true
  practiceError.value = false
  practiceTrendError.value = false
  try {
    const params = getTrendParams()
    const [statsResult, trendResult] = await Promise.allSettled([
      HomeApi.getPractice(),
      HomeApi.getPracticeTrend(params)
    ])

    if (statsResult.status === 'fulfilled') {
      Object.assign(practice, normalizePractice(statsResult.value))
    } else {
      resetPractice()
      practiceError.value = true
      console.error('做题统计加载失败', statsResult.reason)
    }

    if (trendResult.status === 'fulfilled') {
      practiceTrend.value = normalizeTrend(trendResult.value, [
        'practiceCount',
        'answerTotal',
        'answerCount',
        'answeredQuestionCount',
        'value',
        'count'
      ])
    } else {
      practiceTrend.value = []
      practiceTrendError.value = true
      console.error('学员答题趋势加载失败', trendResult.reason)
    }

    if (practiceError.value || practiceTrendError.value) {
      ElMessage.error('做题情况加载失败')
    }
  } catch (error) {
    resetPractice()
    practiceTrend.value = []
    practiceError.value = true
    practiceTrendError.value = true
    console.error('做题情况加载失败', error)
    ElMessage.error('做题情况加载失败')
  } finally {
    practiceLoading.value = false
  }
}

const loadCharts = async () => {
  await Promise.all([loadTrends(), loadPractice()])
}

const loadDashboard = async () => {
  await Promise.all([loadSummary(), loadCharts()])
}

const disabledFutureDate = (date: Date) => dayjs(date).isAfter(dayjs(), 'day')

const handleDateRangeChange = async (value: [string, string] | null) => {
  if (!value) {
    dateRange.value = defaultDateRange()
    await loadCharts()
    return
  }

  const start = dayjs(value[0])
  const end = dayjs(value[1])
  if (end.diff(start, 'day') + 1 > 7) {
    ElMessage.warning('查询时间范围不能超过 7 天')
    dateRange.value = defaultDateRange()
  } else {
    dateRange.value = value
  }
  await loadCharts()
}

const formatNumber = (value: number) => value.toLocaleString('zh-CN')

onMounted(() => {
  if (isTenantOne.value) {
    loadDashboard()
  }
})
</script>

<style lang="scss" scoped>
.home-dashboard {
  padding: 4px;
}

.home-welcome {
  padding: 32px;
  color: var(--el-text-color-primary);
  font-size: 24px;
  font-weight: 600;
}

.dashboard-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.dashboard-title {
  color: var(--el-text-color-primary);
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
}

.dashboard-subtitle {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.chart-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-bottom: 16px;
}

.chart-toolbar :deep(.el-date-editor) {
  width: 210px;
  max-width: 100%;
}

.home-date-range {
  width: 210px !important;
  flex: 0 0 210px;
}

.home-date-range :deep(.el-input__wrapper) {
  width: 100%;
}

.chart-toolbar :deep(.el-date-editor .el-range-input) {
  width: 72px;
  font-size: 13px;
}

.chart-toolbar :deep(.el-date-editor .el-range-separator) {
  flex: 0 0 20px;
  padding: 0;
}

.metric-card,
.chart-card {
  margin-bottom: 16px;
  border-radius: 8px;
}

.metric-card :deep(.el-card__body) {
  height: 100%;
  padding: 20px;
}

.metric-card__body {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  aspect-ratio: 1 / 1;
  min-height: 188px;
  padding: 18px 12px 34px;
  text-align: center;
}

.metric-card__icon {
  display: flex;
  flex: 0 0 58px;
  align-items: center;
  justify-content: center;
  width: 58px;
  height: 58px;
  border-radius: 8px;
}

.metric-card__content {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 0;
  width: 100%;
}

.metric-card__label {
  display: -webkit-box;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: 14px;
  line-height: 20px;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.metric-card__value {
  margin-top: 10px;
  color: var(--el-text-color-primary);
  font-size: 34px;
  font-weight: 700;
  line-height: 42px;
}

.metric-card__secondary {
  position: absolute;
  right: 12px;
  bottom: 10px;
  left: 12px;
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
  gap: 2px;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-card__secondary-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.metric-card__secondary-value {
  color: var(--el-text-color-primary);
  font-size: 18px;
  font-weight: 800;
}

.dashboard-alert {
  margin-bottom: 16px;
}

.chart-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 24px;
  font-weight: 600;
}

@media (max-width: 768px) {
  .dashboard-toolbar,
  .chart-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .chart-toolbar :deep(.el-date-editor) {
    width: 100%;
  }

  .home-date-range {
    width: 100% !important;
    flex: 0 0 auto;
  }

  .metric-card__body {
    aspect-ratio: auto;
  }
}
</style>
