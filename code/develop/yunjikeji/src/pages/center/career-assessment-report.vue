<template>
  <view class="career-report" :style="$appSafeAreaStyle">
    <view class="career-report__content">
      <view class="career-report__nav">
        <button aria-label="返回首页" @tap="goHome"><uv-icon name="arrow-left" color="#06224A" size="46rpx" /></button>
        <text>职业规划评测报告</text>
        <view />
      </view>
      <view v-if="errorMessage" class="career-report__status">{{ errorMessage }}</view>
      <view v-else-if="emptyMessage" class="career-report__status">{{ emptyMessage }}</view>
      <view v-else-if="reportHtml" class="career-report__html"><rich-text :nodes="reportHtml" /></view>
      <button v-if="reportStatus === 'FAILED'" class="career-report__retry" :disabled="regenerating" @tap="regenerate">
        {{ regenerating ? '重新生成中...' : '重新生成职业规划评测报告' }}
      </button>
    </view>
    <SelfTestLoadingOverlay
      :show="!reportOverlayDismissed && !errorMessage && (loading || generating)"
      title="报告正在生成中"
      message="正在整理职业规划评测报告，请稍候。"
      @close="dismissReportOverlay"
    />
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import { fetchCareerAssessmentReport, regenerateCareerAssessmentReport } from '@/services/careerAssessment'
import { requireLogin } from '@/stores/appState'

const loading = ref(true)
const generating = ref(false)
const regenerating = ref(false)
const reportOverlayDismissed = ref(false)
const errorMessage = ref('')
const emptyMessage = ref('')
const reportHtml = ref('')
const reportStatus = ref('')
let recordId = ''
let active = true
let pollTimer: ReturnType<typeof setTimeout> | null = null

const stopPolling = () => {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}

const schedulePolling = () => {
  stopPolling()
  if (active && recordId) pollTimer = setTimeout(() => void loadReport(true), 3000)
}

const sanitizeHtml = (value: string) => value
  .replace(/```(?:html)?/gi, '')
  .replace(/```/g, '')
  .replace(/<\/?(?:html|body|head|style|meta|script)[^>]*>/gi, '')
  .trim()

const loadReport = async (silent = false) => {
  if (!silent) loading.value = true
  errorMessage.value = ''
  emptyMessage.value = ''
  try {
    const report = await fetchCareerAssessmentReport(recordId)
    reportHtml.value = sanitizeHtml(report.reportHtml)
    reportStatus.value = report.reportStatus
    if (report.reportStatus === 'FAILED') {
      generating.value = false
      errorMessage.value = report.reportFailureReason || '职业规划评测报告生成失败，请稍后重试'
      stopPolling()
    } else if (report.reportStatus === 'SUCCESS' || reportHtml.value) {
      generating.value = false
      stopPolling()
      if (!reportHtml.value) emptyMessage.value = '报告已生成，但内容为空，请稍后重试。'
    } else {
      generating.value = true
      schedulePolling()
    }
  } catch (error) {
    if (silent && generating.value) schedulePolling()
    else {
      generating.value = false
      errorMessage.value = error instanceof Error ? error.message : '职业规划评测报告加载失败，请稍后重试'
    }
  } finally {
    if (!silent) loading.value = false
  }
}

const regenerate = async () => {
  if (!recordId || regenerating.value) return
  regenerating.value = true
  stopPolling()
  try {
    const result = await regenerateCareerAssessmentReport(recordId)
    recordId = result.recordId || recordId
    reportStatus.value = result.reportStatus || 'PENDING'
    errorMessage.value = ''
    reportOverlayDismissed.value = false
    await loadReport()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重新生成职业规划评测报告失败，请稍后重试'
  } finally {
    regenerating.value = false
  }
}

const goHome = () => uni.reLaunch({ url: '/pages/home' })

const dismissReportOverlay = () => {
  reportOverlayDismissed.value = true
}

onLoad((query) => {
  active = true
  if (!requireLogin()) return
  recordId = typeof query?.id === 'string' ? query.id : ''
  if (!recordId) {
    loading.value = false
    emptyMessage.value = '暂无可查看的职业规划评测报告。'
    return
  }
  void loadReport()
})

onUnload(() => {
  active = false
  stopPolling()
})
</script>

<style lang="scss">
page { min-height: 100%; background: #eaf6ff; }
.career-report { min-height: 100vh; color: #09244a; background: #eaf6ff; }
.career-report__content { box-sizing: border-box; min-height: 100vh; padding: var(--app-safe-area-top) 28rpx calc(env(safe-area-inset-bottom) + 48rpx); }
.career-report__nav { display: grid; height: var(--app-page-header-height); grid-template-columns: 140rpx minmax(0, 1fr) 140rpx; align-items: center; }
.career-report__nav button { width: 120rpx; height: var(--app-page-header-height); margin: 0; padding: 0; border: 0; background: transparent; text-align: left; }
.career-report__nav button::after { border: 0; }
.career-report__nav text { font-size: 37rpx; line-height: 1.2; font-weight: 700; text-align: center; }
.career-report__status, .career-report__html { box-sizing: border-box; margin-top: 34rpx; padding: 28rpx; border: 1rpx solid #d6e2ed; border-radius: 14rpx; background: #fff; font-size: 29rpx; line-height: 1.7; }
.career-report__html { color: #172b46; }
.career-report__html h1, .career-report__html h2, .career-report__html h3 { color: #09244a; }
.career-report__retry { width: 100%; height: 88rpx; margin-top: 30rpx; border: 0; border-radius: 14rpx; background: #fe5701; color: #fff; font-size: 31rpx; line-height: 88rpx; }
.career-report__retry::after { border: 0; }
</style>
