<template>
  <view class="self-test-record-page" :style="$appSafeAreaStyle">
    <view class="self-test-record-page__bg"></view>

    <scroll-view class="self-test-record-scroll" scroll-y>
      <view class="self-test-record-content">
        <view class="self-test-record-nav">
          <button class="self-test-record-nav__back" aria-label="返回" @tap="goBack">
            <uv-icon name="arrow-left" color="#061F42" size="46rpx" />
          </button>
          <text class="self-test-record-nav__title">自测记录</text>
          <button class="self-test-record-nav__report" @tap="openReport">
            <text>查看报告</text>
          </button>
        </view>

        <view class="self-test-section self-test-hero">
          <view class="section-heading">
            <view class="section-heading__icon">
              <uv-icon name="calendar" color="#FFFFFF" size="36rpx" />
            </view>
            <text>本次自测信息</text>
          </view>
          <view class="self-test-hero__copy">
            <uv-icon name="clock" color="#0B345A" size="34rpx" />
            <text class="self-test-hero__label">自测时间</text>
            <text class="self-test-hero__time">{{ selfTestInfo.startedAt }}</text>
          </view>
          <view class="self-test-hero__drone">
            <view class="drone-body"></view>
            <view class="drone-arm drone-arm--left"></view>
            <view class="drone-arm drone-arm--right"></view>
            <view class="drone-rotor drone-rotor--one"></view>
            <view class="drone-rotor drone-rotor--two"></view>
            <view class="drone-rotor drone-rotor--three"></view>
            <view class="drone-rotor drone-rotor--four"></view>
          </view>
        </view>

        <view class="self-test-section">
          <view class="section-heading">
            <view class="section-heading__icon">
              <uv-icon name="file-text" color="#FFFFFF" size="36rpx" />
            </view>
            <text>回答快照</text>
          </view>
          <text class="self-test-section__hint">展示最近一次自测的回答摘要，便于回看输入快照</text>

          <view v-if="recordError" class="self-test-empty">
            <text>{{ recordError }}</text>
          </view>
          <view v-else-if="!latestRecord" class="self-test-empty">
            <text>暂无自测记录，请先在首页完成一次自我测评。</text>
            <button class="self-test-empty__action" @tap="startSelfTest">
              开始自测
            </button>
          </view>
          <view v-else-if="!answerSnapshots.length" class="self-test-empty">
            <text>本次自测暂无回答快照。</text>
          </view>
          <view v-else class="snapshot-list">
            <view v-for="item in answerSnapshots" :key="item.no" class="snapshot-card">
              <view class="snapshot-card__index">
                <text>{{ item.no }}</text>
              </view>
              <view class="snapshot-card__question">
                <text class="snapshot-card__label">问题</text>
                <text class="snapshot-card__text">{{ item.question }}</text>
              </view>
              <view class="snapshot-card__divider"></view>
              <view class="snapshot-card__answer">
                <text class="snapshot-card__label">答案摘要</text>
                <view class="answer-pill">
                  <text v-for="part in item.answerParts" :key="part">{{ part }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <view class="self-test-section self-test-summary">
          <view class="section-heading">
            <view class="section-heading__icon">
              <uv-icon name="level" color="#FFFFFF" size="38rpx" />
            </view>
            <text>结果摘要</text>
          </view>

          <view class="summary-list">
            <view v-for="item in resultSummary" :key="item.label" class="summary-row">
              <view class="summary-row__icon" :class="`summary-row__icon--${item.tone}`">
                <uv-icon :name="item.icon" color="#0B345A" size="40rpx" />
              </view>
              <text class="summary-row__label">{{ item.label }}</text>
              <view class="summary-row__value" :class="`summary-row__value--${item.tone}`">
                <text>{{ item.value }}</text>
              </view>
            </view>
          </view>
        </view>
      </view>
    </scroll-view>
    <SelfTestLoadingOverlay
      :show="recordLoading"
      title="正在加载自测记录"
      message="请稍候，系统正在同步自测记录。"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import { requireLogin } from '@/stores/appState'
import {
  fetchAssessmentRecords,
  fetchAssessmentResult,
  type AssessmentRecord,
  type AssessmentReport
} from '@/services/assessment'

type AnswerSnapshot = {
  no: string
  question: string
  answerParts: string[]
}

type ResultSummaryItem = {
  label: string
  value: string
  icon: string
  tone: 'blue' | 'green'
}

const records = ref<AssessmentRecord[]>([])
const latestRecordDetail = ref<AssessmentReport | null>(null)
const recordLoading = ref(false)
const recordError = ref('')
const latestRecord = computed(() => latestRecordDetail.value || records.value[0] || null)

const padDatePart = (value: number) => String(value).padStart(2, '0')

const formatDisplayDateTime = (value?: string) => {
  const rawValue = `${value || ''}`.trim()
  if (!rawValue) {
    return '--'
  }

  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$/.test(rawValue)) {
    return rawValue
  }

  const date = new Date(rawValue)
  if (Number.isNaN(date.getTime())) {
    return rawValue.replace('T', ' ').replace(/\.\d{3}Z$/, '')
  }

  return `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())} ${padDatePart(date.getHours())}:${padDatePart(date.getMinutes())}:${padDatePart(date.getSeconds())}`
}

const selfTestInfo = computed(() => ({
  startedAt: formatDisplayDateTime(latestRecord.value?.finishedAt)
}))

const normalizeAnswerText = (value?: string | number) => `${value || ''}`.trim()

const formatAnswerParts = (selectedOptionIds: string[] = [], answer = '') => {
  const optionSummary = selectedOptionIds.map(normalizeAnswerText).filter(Boolean).join('、')
  const answerText = normalizeAnswerText(answer)
  return [answerText || optionSummary || '未作答']
}

const answerSnapshots = computed<AnswerSnapshot[]>(() => {
  const answers = (latestRecord.value?.answers || []).slice(0, 3)
  return answers.map((item, index) => ({
    no: String(item.no || index + 1).padStart(2, '0'),
    question: item.question,
    answerParts: formatAnswerParts(item.selectedOptionIds || [], item.answer)
  }))
})

const resultSummary = computed<ResultSummaryItem[]>(() => [
  {
    label: '报告状态',
    value: latestRecord.value
      ? latestRecordDetail.value?.reportStatus === 'PENDING'
        ? '正在生成'
        : latestRecordDetail.value?.reportStatus === 'FAILED'
          ? '生成失败'
          : '报告已生成'
      : '暂无自测记录',
    icon: 'scan',
    tone: 'blue'
  },
  {
    label: '评测结论',
    value: latestRecord.value?.summary || '完成自测后生成个性化评测结论',
    icon: 'bag',
    tone: 'green'
  },
  {
    label: '下一步',
    value: latestRecord.value?.suggestion || '暂无自测结果，请先在首页完成一次自我测评。',
    icon: 'file-text',
    tone: 'blue'
  }
])

const goBack = () => {
  uni.navigateBack({
    delta: 1,
    fail: () => {
      uni.reLaunch({
        url: '/pages/profile'
      })
    }
  })
}

const openReport = () => {
  const id = latestRecord.value?.id
  if (!id) {
    uni.showToast({
      title: '暂无自测报告，请先完成一次自测',
      icon: 'none'
    })
    return
  }
  uni.navigateTo({
    url: `/pages/center/self-test-report?id=${encodeURIComponent(id)}`
  })
}

const startSelfTest = () => {
  uni.navigateTo({
    url: '/pages/practice/self-test-answer'
  })
}

const loadLatestRecord = async () => {
  if (recordLoading.value) {
    return
  }
  if (!requireLogin()) {
    return
  }
  recordLoading.value = true
  recordError.value = ''
  try {
    const result = await fetchAssessmentRecords()
    const nextRecords = Array.isArray(result) ? result : []
    const latestId = nextRecords[0]?.id
    const nextDetail = latestId ? await fetchAssessmentResult(latestId) : null
    records.value = nextRecords
    latestRecordDetail.value = nextDetail
  } catch (error) {
    records.value = []
    latestRecordDetail.value = null
    recordError.value = error instanceof Error ? error.message : '自测记录加载失败，请稍后重试'
  } finally {
    recordLoading.value = false
  }
}

onShow(() => {
  void loadLatestRecord()
})
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #F5F9FF;
}

.self-test-record-page {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  color: #0b345a;
  background: #F5F9FF;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}

.self-test-record-page__bg {
  position: fixed;
  inset: 0;
  background:
    url('@/static/practice-record/contour-top-right.png') right -92rpx top 116rpx / 350rpx auto no-repeat,
    url('@/static/practice-record/contour-bottom-left.png') left -212rpx top 286rpx / 430rpx auto no-repeat,
    url('@/static/practice-record/contour-top-right.png') right -66rpx bottom -8rpx / 370rpx auto no-repeat,
    linear-gradient(rgba(247, 251, 255, 0.74), rgba(247, 251, 255, 0.74)),
    url('@/static/practice-start/paper-texture.jpg') center top / 320rpx 150rpx repeat;
}

.self-test-record-scroll {
  position: relative;
  z-index: 1;
  height: 100vh;
}

.self-test-record-content {
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--app-safe-area-top) 47rpx calc(env(safe-area-inset-bottom) + 72rpx);
}

.self-test-record-nav {
  position: relative;
  height: var(--app-page-header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.self-test-record-nav__back,
.self-test-record-nav__report {
  margin: 0;
  padding: 0;
}

.self-test-record-nav__back::after,
.self-test-record-nav__report::after {
  border: 0;
}

.self-test-record-nav__back {
  width: 54rpx;
  height: var(--app-page-header-height);
  display: flex;
  align-items: center;
  justify-content: flex-start;
  background: transparent;
}

.self-test-record-nav__title {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: block;
  color: #0b345a;
  font-size: 36rpx;
  line-height: 1.2;
  font-weight: 700;
  text-align: center;
  white-space: nowrap;
}

.self-test-record-nav__report {
  height: var(--app-page-header-height);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  border: 0;
  background: transparent;
  color: #0b345a;
  font-size: 26rpx;
  line-height: 1;
  font-weight: 500;
  white-space: nowrap;
}

.self-test-record-nav__report text {
  display: block;
  line-height: 1;
}

.self-test-section {
  position: relative;
  box-sizing: border-box;
  margin-top: 34rpx;
  overflow: hidden;
  border: 1rpx solid rgba(222, 232, 242, 0.56);
  border-radius: 27rpx;
  background:
    linear-gradient(rgba(255, 255, 255, 0.74), rgba(255, 255, 255, 0.74)),
    url('@/static/practice-start/paper-texture.jpg') center / 320rpx 150rpx repeat;
  box-shadow:
    0 8rpx 20rpx rgba(26, 67, 115, 0.13),
    inset 0 1rpx 0 rgba(255, 255, 255, 0.96);
}

.self-test-section + .self-test-section {
  margin-top: 32rpx;
}

.section-heading {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 17rpx;
  min-height: 48rpx;
  transform: translateX(-4rpx);
}

.self-test-hero .section-heading {
  transform: translateX(-6rpx);
}

.section-heading__icon {
  width: 7rpx;
  height: 30rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  overflow: hidden;
  border-radius: 999rpx;
  background: #0868F4;
}

.section-heading__icon :deep(.uv-icon) {
  display: none;
}

.section-heading text {
  display: block;
  color: #0b345a;
  font-size: 34rpx;
  line-height: 1.2;
  font-weight: 700;
}

.self-test-section__hint {
  display: block;
  margin-top: 12rpx;
  color: #88898b;
  font-size: 22rpx;
  line-height: 30rpx;
  font-weight: 400;
}

.self-test-empty {
  box-sizing: border-box;
  min-height: 150rpx;
  margin-top: 22rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 30rpx 24rpx;
  border: 1rpx solid #DCE8F5;
  border-radius: 14rpx;
  background: rgba(255, 255, 255, 0.62);
  color: #88898b;
  font-size: 25rpx;
  line-height: 1.45;
  text-align: center;
  font-weight: 560;
}

.self-test-empty__action {
  margin-top: 18rpx;
  min-width: 220rpx;
  height: 70rpx;
  padding: 0 28rpx;
  border-radius: 999rpx;
  background: #0868F4;
  color: #ffffff;
  font-size: 25rpx;
  line-height: 70rpx;
  font-weight: 820;
}

.self-test-empty__action::after {
  border: 0;
}

.self-test-hero {
  min-height: 207rpx;
  padding: 36rpx 28rpx 32rpx;
}

.self-test-hero__copy {
  position: relative;
  z-index: 1;
  margin-top: 33rpx;
  display: flex;
  align-items: center;
  gap: 14rpx;
}

.self-test-hero__label,
.self-test-hero__time {
  display: block;
}

.self-test-hero__label {
  flex: 0 0 auto;
  color: #0b345a;
  font-size: 25rpx;
  line-height: 34rpx;
  font-weight: 500;
}

.self-test-hero__time {
  min-width: 0;
  color: #0b345a;
  font-size: 25rpx;
  line-height: 34rpx;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.self-test-hero__drone {
  display: none;
}

.snapshot-list {
  display: flex;
  flex-direction: column;
  gap: 17rpx;
  margin-top: 34rpx;
}

.self-test-section:not(.self-test-hero) {
  padding: 42rpx 26rpx 32rpx;
}

.self-test-section:not(.self-test-hero):not(.self-test-summary) {
  min-height: 524rpx;
}

.snapshot-card {
  box-sizing: border-box;
  min-height: 97rpx;
  display: grid;
  grid-template-columns: 48rpx minmax(0, 1.09fr) 1rpx minmax(0, 1fr);
  align-items: center;
  gap: 10rpx;
  padding: 14rpx 8rpx 14rpx 20rpx;
  border: 1rpx solid #DCE8F5;
  border-radius: 14rpx;
  background: rgba(255, 255, 255, 0.22);
}

.snapshot-card__index {
  width: 44rpx;
  height: 44rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0868F4;
  font-size: 30rpx;
  line-height: 1;
  font-weight: 500;
  transform: translateX(-8rpx);
}

.snapshot-card__question,
.snapshot-card__answer {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6rpx;
}

.snapshot-card__question {
  transform: translateX(-4rpx);
}

.snapshot-card__label,
.snapshot-card__text {
  display: block;
}

.snapshot-card__label {
  flex: 0 0 auto;
  color: #0b345a;
  font-size: 20rpx;
  line-height: 28rpx;
  font-weight: 700;
}

.snapshot-card__text {
  min-width: 0;
  color: #0b345a;
  font-size: 20rpx;
  line-height: 28rpx;
  font-weight: 400;
  overflow-wrap: anywhere;
}

.snapshot-card__divider {
  height: 42rpx;
  border-left: 1rpx solid #DCE8F5;
}

.snapshot-card__answer {
  gap: 4rpx;
  padding-left: 8rpx;
}

.answer-pill {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6rpx;
  color: #0b345a;
  font-size: 20rpx;
  line-height: 28rpx;
  font-weight: 400;
}

.answer-pill text {
  display: block;
  min-width: 0;
  line-height: 28rpx;
  overflow-wrap: anywhere;
}

.answer-pill uni-text {
  display: block;
  min-width: 0;
  line-height: 28rpx;
  overflow-wrap: anywhere;
}

.self-test-summary {
  margin-bottom: 2rpx;
  padding-bottom: 31rpx !important;
}

.summary-list {
  margin-top: 20rpx;
  overflow: hidden;
  border: 1rpx solid #DCE8F5;
  border-radius: 14rpx;
}

.summary-row {
  display: grid;
  grid-template-columns: 40rpx 128rpx minmax(0, 1fr);
  align-items: center;
  column-gap: 18rpx;
  min-height: 81rpx;
  padding: 0 22rpx;
}

.summary-row + .summary-row {
  border-top: 1rpx solid #DCE8F5;
}

.summary-row__icon {
  width: 48rpx;
  height: 48rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

.summary-row:first-child .summary-row__icon {
  position: relative;
  box-sizing: border-box;
  width: 33rpx;
  height: 33rpx;
  margin-left: 1rpx;
  border: 3rpx solid #0b345a;
  border-radius: 50%;
}

.summary-row:first-child .summary-row__icon :deep(.uv-icon),
.summary-row:nth-child(2) .summary-row__icon :deep(.uv-icon) {
  display: none;
}

.summary-row:first-child .summary-row__icon::before {
  content: "";
  box-sizing: border-box;
  width: 13rpx;
  height: 13rpx;
  border: 3rpx solid #0b345a;
  border-radius: 50%;
}

.summary-row:first-child .summary-row__icon::after {
  content: "";
  position: absolute;
  width: 15rpx;
  height: 3rpx;
  margin: -18rpx -18rpx 0 0;
  border-radius: 999rpx;
  background: #0b345a;
  transform: rotate(-45deg);
}

.summary-row:nth-child(2) .summary-row__icon {
  position: relative;
  box-sizing: border-box;
  width: 27rpx;
  height: 33rpx;
  margin-left: 4rpx;
  border: 3rpx solid #0b345a;
  border-radius: 4rpx;
}

.summary-row:nth-child(2) .summary-row__icon::before {
  content: "";
  position: absolute;
  left: 50%;
  top: -7rpx;
  width: 13rpx;
  height: 7rpx;
  border: 3rpx solid #0b345a;
  border-bottom: 0;
  border-radius: 5rpx 5rpx 0 0;
  background: #FFFFFF;
  transform: translateX(-50%);
}

.summary-row:nth-child(2) .summary-row__icon::after {
  content: "";
  width: 9rpx;
  height: 5rpx;
  margin-top: -2rpx;
  border-left: 3rpx solid #0b345a;
  border-bottom: 3rpx solid #0b345a;
  transform: rotate(-45deg);
}

.summary-row__label {
  display: block;
  color: #0b345a;
  font-size: 25rpx;
  line-height: 1.2;
  font-weight: 500;
}

.summary-row__value {
  display: flex;
  align-items: center;
  font-size: 25rpx;
  line-height: 1.35;
  font-weight: 500;
}

.summary-row__value text {
  display: block;
}

.summary-row__value--blue {
  color: #0b345a;
}

.summary-row__value--green {
  color: #0b345a;
}

@media (max-width: 360px) {
  .self-test-record-content {
    padding-left: 43rpx;
    padding-right: 43rpx;
  }

  .self-test-record-nav__report {
    font-size: 24rpx;
  }

  .self-test-hero,
  .self-test-section:not(.self-test-hero) {
    padding-left: 24rpx;
    padding-right: 24rpx;
  }

  .self-test-hero__time {
    font-size: 23rpx;
  }

  .snapshot-card {
    grid-template-columns: 44rpx minmax(0, 1.16fr) 1rpx minmax(0, 1fr);
    gap: 10rpx;
    padding-left: 16rpx;
    padding-right: 16rpx;
  }

  .summary-row {
    grid-template-columns: 44rpx 116rpx minmax(0, 1fr);
    column-gap: 14rpx;
    padding-left: 18rpx;
    padding-right: 18rpx;
  }

  .summary-row__value {
    font-size: 23rpx;
  }
}
</style>
