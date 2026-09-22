<template>
  <view
    class="report-page"
    :class="{ 'report-page--empty': reportEmptyMessage || reportLoading || reportGenerating }"
    :style="$appSafeAreaStyle"
  >
    <view class="report-page__bg"></view>

    <scroll-view class="report-scroll" scroll-y>
      <view class="report-page__content">
        <view class="report-nav">
          <button class="report-nav__back" aria-label="返回" @tap="goBack">
            <uv-icon name="arrow-left" color="#06224A" size="50rpx" />
          </button>
          <text class="report-nav__title">自测报告</text>
          <view class="report-nav__spacer"></view>
        </view>

        <view v-if="reportError" class="report-status">
          <text>{{ reportError }}</text>
        </view>
        <view v-else-if="!reportError && reportEmptyMessage" class="report-empty">
          <view class="report-empty__illustration" aria-hidden="true">
            <view class="report-empty__document">
              <view class="report-empty__fold"></view>
              <view class="report-empty__line report-empty__line--accent"></view>
              <view class="report-empty__line"></view>
              <view class="report-empty__line"></view>
              <view class="report-empty__line"></view>
            </view>
            <view class="report-empty__warning">
              <uv-icon name="error-circle-fill" color="#0878EE" size="58rpx" />
            </view>
          </view>
          <text class="report-empty__title">AI 报告内容为空</text>
          <text class="report-empty__message">{{ reportEmptyMessage }}</text>
        </view>
        <view v-else-if="!reportError && reportHtml" class="report-html-card">
          <rich-text class="report-html" :nodes="reportHtml"></rich-text>
        </view>

        <button
          v-if="isReportFailed"
          class="report-action"
          :loading="reportRegenerating"
          :disabled="reportRegenerating"
          @tap="regenerateReport"
        >
          {{ reportRegenerating ? '重新生成中...' : '重新生成自测报告' }}
        </button>
      </view>
    </scroll-view>
    <SelfTestLoadingOverlay
      :show="!reportOverlayDismissed && !reportError && (reportLoading || reportGenerating)"
      title="报告正在生成中"
      message="正在整理自测报告，请稍候。"
      @close="dismissReportOverlay"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import { requireLogin } from '@/stores/appState'
import {
  fetchSelfAssessmentReport,
  fetchLatestSelfAssessmentReport,
  regenerateAssessmentReport,
  type AssessmentReport
} from '@/services/assessment'

type ReportData = {
  score: number
  level: string
  summary: string
  suggestion: string
  reportHtml: string
  reportStatus: string
  reportFailureReason: string
  stepName: string
  stepStatus?: boolean
}

const fallbackReport: ReportData = {
  score: 0,
  level: '暂无报告',
  summary: '暂无自测记录',
  suggestion: '暂无自测报告，请先在首页完成一次自我测评。',
  reportHtml: '',
  reportStatus: '',
  reportFailureReason: '',
  stepName: '',
  stepStatus: undefined
}

const stripUnsafeHtmlShell = (value = '') => {
  const text = value
    .replace(/```(?:html)?/gi, '')
    .replace(/```/g, '')
    .replace(/<\/?(?:html|body|head|style|meta|script)[^>]*>/gi, '')
    .trim()
  return text
}

const toReportData = (source: Partial<AssessmentReport & ReportData> | null | undefined): ReportData | null => {
  if (!source) {
    return null
  }
  const suggestion = typeof source.suggestion === 'string' ? source.suggestion : fallbackReport.suggestion
  const rawHtml = typeof source.reportHtml === 'string' ? source.reportHtml : ''

  return {
    score: typeof source.score === 'number' ? source.score : fallbackReport.score,
    level: typeof source.level === 'string' ? source.level : fallbackReport.level,
    summary: typeof source.summary === 'string' ? source.summary : fallbackReport.summary,
    suggestion,
    reportHtml: stripUnsafeHtmlShell(rawHtml),
    reportStatus: typeof source.reportStatus === 'string' ? source.reportStatus.trim().toUpperCase() : '',
    reportFailureReason:
      typeof source.reportFailureReason === 'string' ? source.reportFailureReason.trim() : '',
    stepName: typeof source.stepName === 'string' ? source.stepName.trim() : '',
    stepStatus: typeof source.stepStatus === 'boolean' ? source.stepStatus : undefined
  }
}

const reportState = ref<ReportData>(fallbackReport)
const reportLoading = ref(true)
const reportGenerating = ref(false)
const reportRegenerating = ref(false)
const reportOverlayDismissed = ref(false)
const reportError = ref('')
const reportEmptyMessage = ref('')
const report = computed(() => reportState.value)
const reportHtml = computed(() => report.value.reportHtml)
const isReportFailed = computed(() => report.value.reportStatus === 'FAILED')
let reportResultId = ''
let reportPollTimer: ReturnType<typeof setTimeout> | null = null
let reportPageActive = true

const stopReportPolling = () => {
  if (reportPollTimer !== null) {
    clearTimeout(reportPollTimer)
    reportPollTimer = null
  }
}

const scheduleReportPolling = () => {
  stopReportPolling()
  if (!reportPageActive || !reportResultId) {
    return
  }
  reportPollTimer = setTimeout(() => {
    void loadReport(reportResultId, true)
  }, 3000)
}

const goBack = () => {
  goHome()
}

const goHome = () => {
  uni.reLaunch({
    url: '/pages/home'
  })
}

const dismissReportOverlay = () => {
  reportOverlayDismissed.value = true
}

const regenerateReport = async () => {
  if (reportRegenerating.value || !reportResultId) {
    return
  }

  reportRegenerating.value = true
  stopReportPolling()
  try {
    const result = await regenerateAssessmentReport(reportResultId)
    reportResultId = result.recordId || reportResultId
    reportState.value = {
      ...reportState.value,
      reportStatus: result.reportStatus?.trim().toUpperCase() || 'PENDING',
      reportFailureReason: ''
    }
    reportError.value = ''
    reportEmptyMessage.value = ''
    reportGenerating.value = true
    reportOverlayDismissed.value = false

    if (reportState.value.reportStatus === 'SUCCESS') {
      await loadReport(reportResultId, true)
    } else {
      scheduleReportPolling()
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : '重新生成自测报告失败，请稍后重试'
    reportError.value = message
    uni.showToast({ title: message, icon: 'none' })
  } finally {
    reportRegenerating.value = false
  }
}

const loadReport = async (resultId = '', silent = false) => {
  if (!silent) {
    reportLoading.value = true
  }
  reportError.value = ''
  reportEmptyMessage.value = ''
  try {
    const result = resultId ? await fetchSelfAssessmentReport(resultId) : await fetchLatestSelfAssessmentReport()
    reportState.value = toReportData(result) || fallbackReport
    if (!result) {
      reportGenerating.value = false
      reportEmptyMessage.value = '请先完成一次自测。'
      stopReportPolling()
    } else {
      reportResultId = result.id || reportResultId
    }
    if (result && reportState.value.reportStatus === 'FAILED') {
      reportGenerating.value = false
      reportError.value = reportState.value.reportFailureReason || '自测报告生成失败，请稍后重试'
      stopReportPolling()
    } else if (result && (reportState.value.reportStatus === 'SUCCESS' || reportState.value.reportHtml)) {
      reportGenerating.value = false
      stopReportPolling()
      if (!reportState.value.reportHtml) {
        reportEmptyMessage.value = '报告已生成，但内容为空，请稍后重试。'
      }
    } else if (result) {
      reportGenerating.value = true
      scheduleReportPolling()
    }
  } catch (error) {
    if (silent && reportGenerating.value) {
      scheduleReportPolling()
    } else {
      reportState.value = fallbackReport
      reportGenerating.value = false
      reportError.value = error instanceof Error ? error.message : '自测报告加载失败，请稍后重试'
    }
  } finally {
    if (!silent) {
      reportLoading.value = false
    }
  }
}

onLoad((query) => {
  reportPageActive = true
  if (!requireLogin()) {
    return
  }
  reportResultId = typeof query?.id === 'string' ? query.id : ''
  void loadReport(reportResultId)
})

onUnload(() => {
  reportPageActive = false
  stopReportPolling()
})
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #eaf6ff;
}

button::after {
  border: 0;
}

.report-page {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  color: #071b3e;
  background: #eaf6ff;
}

.report-page__bg {
  position: fixed;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(239, 248, 255, 0.96) 0%, rgba(230, 244, 255, 0.94) 48%, #f7fbff 100%),
    url('@/static/backgrounds/focus-atmosphere.png') center top / 100% auto repeat-y;
}

.report-scroll {
  position: relative;
  z-index: 1;
  height: 100vh;
}

.report-page__content {
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--app-safe-area-top) 28rpx calc(env(safe-area-inset-bottom) + 48rpx);
}

.report-nav {
  height: var(--app-page-header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.report-nav__back,
.report-nav__spacer {
  min-width: 72rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
}

.report-nav__back {
  padding: 0 8rpx 0 0;
}

.report-nav__title {
  font-size: 38rpx;
  line-height: 1.2;
  font-weight: 900;
  color: #06224a;
}

.report-status {
  box-sizing: border-box;
  margin-top: 18rpx;
  padding: 18rpx 22rpx;
  border: 1rpx solid rgba(201, 222, 244, 0.9);
  border-radius: 12rpx;
  background: rgba(255, 255, 255, 0.84);
  color: #5b7190;
  font-size: 25rpx;
  line-height: 1.4;
  text-align: center;
}

.report-html-card {
  box-sizing: border-box;
  border: 1rpx solid rgba(224, 238, 249, 0.96);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 18rpx 42rpx rgba(52, 91, 129, 0.1);
}

.report-html-card {
  margin-top: 34rpx;
  padding: 32rpx;
  border-radius: 20rpx;
}

.report-html {
  display: block;
  color: #0b2448;
  font-size: 27rpx;
  line-height: 1.72;
  word-break: break-word;
}

.report-html h1,
.report-html h2,
.report-html h3,
.report-html h4,
.report-html p,
.report-html ul,
.report-html ol,
.report-html table,
.report-html blockquote,
.report-html hr {
  margin: 0;
  padding: 0;
}

.report-html h1 {
  margin-top: 34rpx;
  color: #061f42;
  font-size: 34rpx;
  line-height: 1.28;
  font-weight: 900;
}

.report-html h1:first-child {
  margin-top: 0;
}

.report-html h2 {
  margin-top: 28rpx;
  color: #0865ea;
  font-size: 29rpx;
  line-height: 1.34;
  font-weight: 900;
}

.report-html h3,
.report-html h4 {
  margin-top: 22rpx;
  color: #0b2448;
  font-size: 26rpx;
  line-height: 1.36;
  font-weight: 850;
}

.report-html p,
.report-html li,
.report-html td,
.report-html th {
  color: #2a3d57;
  font-size: 25rpx;
  line-height: 1.72;
}

.report-html p {
  margin-top: 16rpx;
}

.report-html ul,
.report-html ol {
  margin-top: 16rpx;
  padding-left: 34rpx;
}

.report-html table {
  width: 100%;
  margin-top: 20rpx;
  border-collapse: collapse;
  overflow: hidden;
  border-radius: 12rpx;
}

.report-html th,
.report-html td {
  padding: 16rpx 14rpx;
  border: 1rpx solid #dbeafa;
  text-align: left;
}

.report-html th {
  color: #075dbb;
  background: #edf7ff;
  font-weight: 900;
}

.report-html blockquote {
  margin-top: 20rpx;
  padding: 18rpx 22rpx;
  border-left: 7rpx solid #0865ea;
  border-radius: 10rpx;
  background: #eef7ff;
  color: #2a3d57;
}

.report-html hr {
  height: 1rpx;
  margin: 30rpx 0;
  border: 0;
  background: #d7e8f9;
}

.report-action {
  width: 100%;
  height: 82rpx;
  margin: 34rpx 0 0;
  border-radius: 18rpx;
  background: linear-gradient(90deg, #168bf2 0%, #0076e8 100%);
  color: #ffffff;
  font-size: 28rpx;
  line-height: 82rpx;
  font-weight: 900;
  box-shadow: 0 14rpx 30rpx rgba(0, 118, 232, 0.24);
}

.report-page--empty {
  color: #0c2f56;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: #F5F9FF;
}

.report-page--empty .report-page__bg {
  overflow: hidden;
  background:
    url('@/static/practice-record/contour-top-right.png') right -8rpx top 110rpx / 330rpx auto no-repeat,
    url('@/static/practice-record/contour-bottom-left.png') left -115rpx bottom / 430rpx auto no-repeat,
    linear-gradient(rgba(247, 251, 255, 0.78), rgba(247, 251, 255, 0.78)),
    url('@/static/practice-start/paper-texture.jpg') center top / 320rpx 150rpx repeat;
  background-color: #F5F9FF;
}

.report-page--empty .report-page__bg::before,
.report-page--empty .report-page__bg::after {
  content: '';
  position: absolute;
  pointer-events: none;
}

.report-page--empty .report-page__bg::before {
  left: 427rpx;
  top: 219rpx;
  box-sizing: border-box;
  width: 442rpx;
  height: 226rpx;
  border: 3rpx dashed rgba(173, 211, 246, 0.72);
  border-radius: 50%;
  clip-path: inset(0 50% 50% 0);
}

.report-page--empty .report-page__bg::after {
  left: 635rpx;
  top: 206rpx;
  width: 26rpx;
  height: 26rpx;
  border-radius: 50% 50% 50% 0;
  background: radial-gradient(circle at 50% 50%, #F5F9FF 0 3rpx, #D8EAFF 4rpx);
  transform: rotate(-45deg);
}

.report-page--empty .report-nav {
  position: relative;
}

.report-page--empty .report-nav__back,
.report-page--empty .report-nav__spacer {
  width: 88rpx;
  height: 88rpx;
}

.report-page--empty .report-nav__back {
  margin-left: -20rpx;
}

.report-page--empty .report-nav__spacer {
  margin-right: -20rpx;
}

.report-page--empty .report-nav__title {
  position: absolute;
  left: 50%;
  color: #0c2f56;
  font-size: 40rpx;
  font-weight: 700;
  transform: translateX(-50%);
}

.report-empty {
  box-sizing: border-box;
  width: 557rpx;
  height: 507rpx;
  margin: calc(340rpx - var(--app-safe-area-top)) auto 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  overflow: hidden;
  border: 1rpx solid rgba(222, 234, 246, 0.82);
  border-radius: 42rpx;
  background: rgba(255, 255, 255, 0.94);
  box-shadow:
    0 18rpx 46rpx rgba(24, 64, 109, 0.14),
    inset 0 1rpx 0 rgba(255, 255, 255, 0.96);
}

.report-empty__illustration {
  position: relative;
  width: 165rpx;
  height: 209rpx;
  flex: 0 0 auto;
  margin-top: 72rpx;
}

.report-empty__document {
  position: relative;
  box-sizing: border-box;
  width: 165rpx;
  height: 209rpx;
  padding: 57rpx 31rpx 0;
  overflow: hidden;
  border: 2rpx solid #E6EFF8;
  border-radius: 28rpx 22rpx 28rpx 28rpx;
  background: #F8FBFF;
  box-shadow: 0 14rpx 24rpx rgba(24, 63, 107, 0.16);
}

.report-empty__fold {
  position: absolute;
  top: -2rpx;
  right: -2rpx;
  width: 55rpx;
  height: 60rpx;
  border-left: 2rpx solid #E6EFF8;
  border-bottom: 2rpx solid #E6EFF8;
  border-bottom-left-radius: 17rpx;
  background: #F7FAFE;
}

.report-empty__line {
  position: relative;
  z-index: 1;
  width: 101rpx;
  height: 10rpx;
  margin-top: 17rpx;
  border-radius: 999rpx;
  background: #E6EEF7;
}

.report-empty__line--accent {
  width: 46rpx;
  height: 9rpx;
  margin-top: 0;
  background: #0878EE;
}

.report-empty__line--accent + .report-empty__line {
  margin-top: 24rpx;
}

.report-empty__warning {
  position: absolute;
  z-index: 2;
  right: -18rpx;
  bottom: -12rpx;
  width: 58rpx;
  height: 58rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  filter: drop-shadow(0 7rpx 8rpx rgba(12, 101, 214, 0.2));
}

.report-empty__warning :deep(.uv-icon) {
  line-height: 1;
}

.report-empty__title,
.report-empty__message {
  display: block;
  color: #0c2f56;
  text-align: center;
}

.report-empty__title {
  margin-top: 43rpx;
  font-size: 42rpx;
  line-height: 51rpx;
  font-weight: 700;
}

.report-empty__message {
  margin-top: 25rpx;
  font-size: 30rpx;
  line-height: 42rpx;
  font-weight: 400;
}

.report-page--empty .report-action {
  width: 632rpx;
  height: 106rpx;
  margin: 69rpx auto 0;
  padding: 0;
  border-radius: 22rpx;
  background: linear-gradient(90deg, #168BF2 0%, #0868F4 100%);
  color: #ffffff;
  font-size: 36rpx;
  line-height: 106rpx;
  font-weight: 700;
  box-shadow: 0 15rpx 28rpx rgba(12, 98, 211, 0.28);
}

@media (max-width: 360px) {
  .report-page__content {
    padding-left: 22rpx;
    padding-right: 22rpx;
  }

  .report-html-card {
    padding: 26rpx;
  }
}
</style>
