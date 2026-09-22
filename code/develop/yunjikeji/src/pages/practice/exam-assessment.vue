<template>
  <view class="assessment-page" :style="$appSafeAreaStyle">
    <scroll-view class="assessment-scroll" scroll-y :show-scrollbar="false">
      <view class="assessment-content">
        <view class="assessment-nav">
          <view class="assessment-nav__action" @tap="goBack">
            <uv-icon name="arrow-left" color="#06224a" size="38rpx" />
          </view>
          <text class="assessment-nav__title">{{ resolvedTopicTitle }}</text>
          <view class="assessment-nav__action"></view>
        </view>

        <view class="assessment-backdrop" aria-hidden="true"></view>

        <template v-if="pageStatus === 'ready' && summary && batchDetail">
          <PracticeStartSummary
            :practice="summary"
            :category="resolvedTopicTitle"
            :loading="actionBusy"
            :disabled="actionBusy"
            :show-intro="false"
            @start="handleStart"
            @wrong-review="handleHiddenAction"
          />
        </template>

        <AppStateView
          v-else-if="pageStatus !== 'loading'"
          class="assessment-state"
          :status="pageStatus"
          :title="stateTitle"
          :message="stateMessage"
          :action-text="pageStatus === 'error' ? '重新加载' : ''"
          @retry="loadBatchDetail"
        />
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import AppStateView from '@/components/AppStateView.vue'
import PracticeStartSummary from '@/components/PracticeStartSummary.vue'
import {
  fetchCatalogBatchDetail,
  type PracticeCatalogBatchDetail,
  type PracticeStartMode,
  type PracticeStartPage
} from '@/services/practice'
import { type AppAsyncStatus, requireLogin } from '@/stores/appState'

const practiceId = ref('')
const catalogBatchId = ref('')
const recordId = ref('')
const sessionId = ref('')
const topicId = ref('')
const topicTitle = ref('')
const mode = ref<PracticeStartMode>('practice')
const batchDetail = ref<PracticeCatalogBatchDetail | null>(null)
const pageStatus = ref<AppAsyncStatus>('loading')
const errorMessage = ref('')
const actionBusy = ref(false)

const modeLabel = computed(() => {
  switch (mode.value) {
    case 'chapter-test':
      return '章节测试'
    case 'theory-exam':
      return '综合考试'
    case 'comprehensive-exam':
      return '理论考试'
    case 'instructor-exam':
      return '教员考试'
    default:
      return '逐题练习'
  }
})
const resolvedTopicTitle = computed(() => {
  if (mode.value === 'theory-exam' || mode.value === 'comprehensive-exam' || mode.value === 'instructor-exam') {
    return modeLabel.value
  }
  return batchDetail.value?.categoryName || topicTitle.value || '题库训练'
})
const summary = computed<PracticeStartPage | null>(() => {
  if (!batchDetail.value) {
    return null
  }
  return {
    id: batchDetail.value.practiceId,
    subject: '无人机驾驶员理论',
    category: resolvedTopicTitle.value,
    paperNo: batchDetail.value.catalogId || '--',
    title: resolvedTopicTitle.value,
    questionCount: batchDetail.value.total,
    totalScore: batchDetail.value.totalScore ?? 0,
    timeLimitMinutes: batchDetail.value.timeLimitMinutes ?? 0,
    gradingMode: mode.value === 'theory-exam' || mode.value === 'comprehensive-exam' || mode.value === 'instructor-exam'
      ? modeLabel.value
      : batchDetail.value.gradingMode || modeLabel.value,
    wrongQuestionCount: 0
  }
})

const stateTitle = computed(() => pageStatus.value === 'loading' ? '正在加载批次信息' : pageStatus.value === 'empty' ? '当前批次暂无可练习题目' : '无法打开练习批次')
const stateMessage = computed(() => errorMessage.value || (pageStatus.value === 'empty' ? '该批次当前没有可用考题。' : '请稍候，正在同步批次详情。'))

const readQueryValue = (value: unknown) => {
  if (typeof value !== 'string') return ''
  try {
    return decodeURIComponent(value).trim()
  } catch {
    return ''
  }
}

const readMode = (value: unknown): PracticeStartMode => {
  if (value === 'chapter-test') return 'chapter-test'
  if (value === 'theory-exam') return 'theory-exam'
  if (value === 'comprehensive-exam') return 'comprehensive-exam'
  if (value === 'instructor-exam') return 'instructor-exam'
  if (value === 'wrongReview') return 'wrongReview'
  return 'practice'
}

const loadBatchDetail = async () => {
  if (!catalogBatchId.value) {
    batchDetail.value = null
    errorMessage.value = '缺少批次参数，请返回重新选择题型。'
    pageStatus.value = 'error'
    return
  }

  pageStatus.value = 'loading'
  errorMessage.value = ''
  batchDetail.value = null
  try {
    const result = await fetchCatalogBatchDetail(catalogBatchId.value)
    if (!result.practiceId || !result.sessionId || !result.recordId) {
      errorMessage.value = '批次详情缺少必要字段，请稍后重试。'
      pageStatus.value = 'error'
      return
    }
    practiceId.value = result.practiceId
    sessionId.value = result.sessionId
    recordId.value = result.recordId
    topicTitle.value = topicTitle.value || result.categoryName
    batchDetail.value = result
    pageStatus.value = result.total > 0 ? 'ready' : 'empty'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批次详情加载失败'
    pageStatus.value = 'error'
  }
}

const goBack = () => {
  const fallbackUrl = mode.value === 'chapter-test' || mode.value === 'practice'
    ? `/pages/practice/exam-topics?mode=${encodeURIComponent(mode.value === 'chapter-test' ? 'chapter-test' : 'practice')}`
    : '/pages/practice/exam-modes'
  uni.navigateBack({ delta: 1, fail: () => uni.reLaunch({ url: fallbackUrl }) })
}

const handleStart = () => {
  if (!batchDetail.value || actionBusy.value) return
  actionBusy.value = true
  try {
    uni.navigateTo({
      url:
        `${batchDetail.value.nextPage}?id=${encodeURIComponent(practiceId.value)}` +
        `&sessionId=${encodeURIComponent(sessionId.value)}` +
        `&recordId=${encodeURIComponent(recordId.value)}` +
        `&catalogBatchId=${encodeURIComponent(catalogBatchId.value)}` +
        `&mode=${encodeURIComponent(mode.value)}` +
        `&remainingSeconds=${encodeURIComponent(String(batchDetail.value.remainingSeconds ?? 0))}` +
        `&topicId=${encodeURIComponent(topicId.value)}` +
        `&topicTitle=${encodeURIComponent(resolvedTopicTitle.value)}`
    })
  } finally {
    actionBusy.value = false
  }
}

const handleHiddenAction = () => {
  uni.showToast({ title: '当前批次不支持在此页重新发起其他练习', icon: 'none' })
}

onLoad((query) => {
  practiceId.value = readQueryValue(query?.practiceId)
  catalogBatchId.value = readQueryValue(query?.catalogBatchId)
  recordId.value = readQueryValue(query?.recordId)
  sessionId.value = readQueryValue(query?.sessionId)
  topicId.value = readQueryValue(query?.topicId)
  topicTitle.value = readQueryValue(query?.topicTitle)
  mode.value = readMode(readQueryValue(query?.mode))
  if (requireLogin()) void loadBatchDetail()
})
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #f8fbff;
}

.assessment-page {
  position: relative;
  height: 100vh;
  overflow: hidden;
  background-color: #f8fbff;
}

.assessment-backdrop {
  position: relative;
  width: auto;
  height: 304rpx;
  margin-right: -34rpx;
  margin-left: -34rpx;
  background: url('@/static/practice-start/overview-desk.jpg') center top / 100% auto no-repeat;
}

.assessment-scroll {
  position: relative;
  z-index: 1;
  height: 100vh;
}

.assessment-content {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  width: 100%;
  max-width: 750px;
  min-height: 100vh;
  margin: 0 auto;
  padding: var(--app-safe-area-top) 34rpx calc(env(safe-area-inset-bottom) + 40rpx);
}

.assessment-nav {
  position: relative;
  height: var(--app-page-header-height);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: -34rpx;
  margin-left: -34rpx;
  padding: 0 34rpx;
  background-color: #f8fbff;
  box-shadow: 0 1rpx 0 rgba(72, 101, 132, 0.24);
}

.assessment-nav__action {
  position: absolute;
  top: 0;
  width: 72rpx;
  height: var(--app-page-header-height);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 0;
}

.assessment-nav__action:first-child {
  left: 12rpx;
  transform: none;
}

.assessment-nav__action:last-child {
  right: 12rpx;
}

.assessment-nav__action:first-child .uv-icon__icon {
  font-size: 46rpx !important;
}

.assessment-nav__title {
  min-width: 0;
  overflow: hidden;
  color: #0b3150;
  font-size: 33rpx;
  line-height: 1.2;
  font-weight: 600;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: 0;
  transform: translateX(-2rpx);
}

.assessment-content > .practice-start {
  margin-top: 0;
  margin-right: -34rpx;
  margin-left: -34rpx;
}

.assessment-page :deep(.practice-start-actions__secondary) {
  display: none;
}

.assessment-state {
  margin-top: 0;
}

.assessment-page .practice-start__paper {
  padding-right: 63rpx;
  padding-left: 59rpx;
}

.assessment-page .practice-start-info__item {
  padding-right: 34rpx;
}

.assessment-page .practice-start-info__item:first-child {
  min-height: 131rpx;
}

.assessment-page .practice-start-info__label,
.assessment-page .practice-start-info__value {
  color: #0a3158;
  font-size: 28rpx;
  font-weight: 600;
}

.assessment-page .practice-start-info__label {
  color: #0868F4;
  font-size: 27.8rpx;
}

.assessment-page .practice-start-info__item:first-child .practice-start-info__label {
  transform: translate(2rpx, 3.25rpx);
}

.assessment-page .practice-start-info__item:first-child .practice-start-info__value {
  transform: translateY(3.5rpx);
}

.assessment-page .practice-start-rules {
  grid-template-columns: 49% 51%;
}

.assessment-page .practice-start-rules__row {
  min-height: 180rpx;
}

.assessment-page .practice-start-rules__label {
  color: #0868F4;
  font-size: 26rpx;
  font-weight: 600;
}

.assessment-page .practice-start-rules__value {
  color: #0a3158;
}

.assessment-page .practice-start-rules__row:nth-child(1) .practice-start-rules__copy {
  transform: translateX(-14rpx);
}

.assessment-page .practice-start-rules__row:nth-child(2) .practice-start-rules__copy {
  transform: translateX(-4rpx);
}

.assessment-page .practice-start-rules__row:nth-child(3) .practice-start-rules__copy {
  transform: translateX(-8.5rpx);
}

.assessment-page .practice-start-rules__row:nth-child(4) .practice-start-rules__copy {
  transform: translateX(-3rpx);
}

.assessment-page .practice-start-rules__row:nth-child(-n + 2) .practice-start-rules__label {
  transform: translateY(-3.5rpx);
}

.assessment-page .practice-start-rules__row:nth-child(n + 3) .practice-start-rules__label {
  transform: translateY(-2rpx);
}

.assessment-page .practice-start-rules__row:nth-child(1) .practice-start-rules__value {
  transform: translate(1rpx, 1rpx);
}

.assessment-page .practice-start-rules__row:nth-child(2) .practice-start-rules__value {
  font-size: 33rpx;
  transform: translate(3rpx, 1rpx);
}

.assessment-page .practice-start-rules__row:nth-child(3) .practice-start-rules__value {
  font-size: 30rpx;
  transform: translateY(-3rpx);
}

.assessment-page .practice-start-rules__row:nth-child(4) .practice-start-rules__value {
  font-size: 28rpx;
  transform: translate(1.5rpx, -3rpx);
}

.assessment-page .practice-start-card__diagram {
  width: calc(100% + 3.25rpx);
  margin-top: 24rpx;
  margin-left: 1rpx;
  opacity: 1;
}

.assessment-page .practice-start-card__diagram-image {
  mix-blend-mode: normal;
}

.assessment-page .practice-start-actions {
  width: calc(100% - 1rpx);
  gap: 18.5rpx;
  margin-left: 1rpx;
  padding-top: 23rpx;
}

.assessment-page .practice-start-actions__primary,
.assessment-page .practice-start-actions__secondary {
  height: 82rpx;
  line-height: 82rpx;
}

.assessment-page .practice-start-actions__primary {
  gap: 24rpx;
  background: #167EE8;
}

.assessment-page .practice-start-actions__primary .practice-start-actions__play {
  transform: translateX(-15rpx);
}

.assessment-page .practice-start-actions__primary > :last-child {
  transform: translateX(-17rpx);
}

.assessment-page .practice-start-actions__play {
  width: 44rpx;
  height: 44rpx;
}

.assessment-page .practice-start-actions__play .uv-icon__icon {
  font-size: 26rpx !important;
}

.assessment-page .practice-start-actions__secondary {
  color: #0868F4;
  border-color: #0868F4;
}

@media (max-width: 360px) {
  .assessment-content {
    padding-right: 28rpx;
    padding-left: 28rpx;
  }

  .assessment-nav {
    margin-right: -28rpx;
    margin-left: -28rpx;
    padding-right: 28rpx;
    padding-left: 28rpx;
  }

  .assessment-nav__title {
    font-size: 31rpx;
  }

  .assessment-backdrop {
    margin-right: -28rpx;
    margin-left: -28rpx;
  }

  .assessment-content > .practice-start {
    margin-right: -28rpx;
    margin-left: -28rpx;
  }

}
</style>
