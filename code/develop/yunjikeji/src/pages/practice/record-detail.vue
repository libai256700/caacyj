<template>
  <view class="record-detail-page" :style="$appSafeAreaStyle">
    <view class="record-detail-page__bg"></view>

    <scroll-view class="record-detail-scroll" scroll-y>
      <view class="record-detail-content">
        <view class="record-detail-nav">
          <button class="record-detail-nav__back" aria-label="返回首页" @tap="goHome">
            <uv-icon name="arrow-left" color="#06224A" size="50rpx" />
          </button>
          <text class="record-detail-nav__title">答题详情</text>
          <view class="record-detail-nav__spacer"></view>
        </view>

        <view v-if="loading" class="record-detail-loading">
          <text>正在加载练习详情</text>
        </view>

        <view v-else-if="!recordId" class="record-detail-empty-shell">
          <AppStateView
            class="record-detail-state"
            status="empty"
            title="无数据"
            message="未找到记录参数，暂无可展示的答题详情。"
          />
          <button class="record-detail-action" @tap="goHome">返回首页</button>
        </view>

        <AppStateView
          v-else-if="errorMessage"
          class="record-detail-state"
          status="error"
          title="答题详情加载失败"
          :message="errorMessage"
          action-text="重新加载"
          @retry="loadRecordDetail"
        />

        <template v-else-if="record">
          <view class="record-detail-section record-detail-summary">
            <view class="record-detail-section__heading">
              <view class="record-detail-section__icon">
                <uv-icon name="file-text" color="#FFFFFF" size="36rpx" />
              </view>
              <text>概述</text>
            </view>

            <view class="record-detail-summary__grid">
              <view class="record-detail-summary__row record-detail-summary__row--top">
                <view v-for="item in summaryTopItems" :key="item.label" class="record-detail-summary__cell">
                  <text class="record-detail-summary__label">{{ item.label }}</text>
                  <text class="record-detail-summary__value" :class="item.emphasis ? 'record-detail-summary__value--accent' : ''">
                    {{ item.value }}
                  </text>
                </view>
              </view>
              <view class="record-detail-summary__row record-detail-summary__row--bottom">
                <view v-for="item in summaryBottomItems" :key="item.label" class="record-detail-summary__cell">
                  <text class="record-detail-summary__label">{{ item.label }}</text>
                  <text class="record-detail-summary__value" :class="item.emphasis ? 'record-detail-summary__value--accent' : ''">
                    {{ item.value }}
                  </text>
                </view>
              </view>
            </view>
          </view>

          <button class="record-detail-action" @tap="goHome">返回首页</button>
        </template>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import AppStateView from '@/components/AppStateView.vue'
import { fetchPracticeRecordDetail, type PracticeRecordDetail } from '@/services/practice'
import { requireLogin } from '@/stores/appState'

type SummaryItem = {
  label: string
  value: string
  emphasis?: boolean
}

const recordId = ref('')
const loading = ref(false)
const errorMessage = ref('')
const record = ref<PracticeRecordDetail | null>(null)

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
  return `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())} ${padDatePart(date.getHours())}:${padDatePart(date.getMinutes())}`
}

const summaryItems = computed<SummaryItem[]>(() => {
  const detail = record.value
  return [
    { label: '满分', value: `${detail?.totalScore ?? 0}` },
    { label: '实际得分', value: `${detail?.score ?? 0}`, emphasis: true },
    { label: '正确数', value: `${detail?.correctCount ?? 0}` },
    { label: '错误数', value: `${detail?.wrongCount ?? 0}` },
    { label: '练习时间', value: formatDisplayDateTime(detail?.practicedAt) }
  ]
})

const summaryTopItems = computed(() => summaryItems.value.slice(0, 3))
const summaryBottomItems = computed(() => summaryItems.value.slice(3))

const readQueryValue = (value: unknown) => {
  if (typeof value !== 'string') {
    return ''
  }
  try {
    return decodeURIComponent(value).trim()
  } catch {
    return value.trim()
  }
}

const loadRecordDetail = async () => {
  if (!recordId.value) {
    record.value = null
    errorMessage.value = ''
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    record.value = await fetchPracticeRecordDetail(recordId.value)
  } catch (error) {
    record.value = null
    errorMessage.value = error instanceof Error ? error.message : '练习详情加载失败'
  } finally {
    loading.value = false
  }
}

const goHome = () => {
  uni.reLaunch({ url: '/pages/home' })
}

onLoad((query) => {
  if (!requireLogin()) {
    return
  }
  recordId.value = readQueryValue(query?.recordId)
  void loadRecordDetail()
})
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #eef7ff;
}

.record-detail-page {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  color: #0a2146;
  background: #eef7ff;
}

.record-detail-page__bg {
  position: fixed;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0, rgba(239, 248, 255, 0.96) 220rpx, rgba(246, 251, 255, 0.98) 100%),
    url('@/static/backgrounds/focus-atmosphere.png') center top / cover no-repeat;
}

.record-detail-scroll {
  position: relative;
  z-index: 1;
  height: 100vh;
}

.record-detail-content {
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--app-safe-area-top) 28rpx calc(env(safe-area-inset-bottom) + 48rpx);
}

.record-detail-nav {
  height: var(--app-page-header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.record-detail-nav__back,
.record-detail-nav__spacer {
  width: 72rpx;
  height: var(--app-page-header-height);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.record-detail-nav__back {
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
}

.record-detail-nav__back::after {
  border: 0;
}

.record-detail-nav__title {
  color: #06224a;
  font-size: 40rpx;
  line-height: 1.2;
  font-weight: 700;
}

.record-detail-loading {
  margin-top: 140rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0a2146;
  font-size: 28rpx;
  font-weight: 600;
}

.record-detail-state {
  margin-top: 48rpx;
}

.record-detail-section {
  margin-top: 34rpx;
  padding: 28rpx 30rpx 32rpx;
  border: 1rpx solid rgba(222, 232, 242, 0.5);
  border-radius: 27rpx;
  background:
    linear-gradient(rgba(255, 255, 255, 0.76), rgba(255, 255, 255, 0.76)),
    url('@/static/practice-start/paper-texture.jpg') center / 320rpx 150rpx repeat;
  box-shadow:
    0 8rpx 20rpx rgba(26, 67, 115, 0.13),
    inset 0 1rpx 0 rgba(255, 255, 255, 0.92);
}

.record-detail-section__heading {
  display: flex;
  align-items: center;
  gap: 14rpx;
  color: #0a2146;
  font-size: 30rpx;
  line-height: 1.2;
  font-weight: 700;
}

.record-detail-section__icon {
  width: 48rpx;
  height: 48rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(180deg, #0b73ed 0%, #0552b5 100%);
}

.record-detail-summary__grid {
  margin-top: 24rpx;
  display: flex;
  flex-direction: column;
  border-radius: 20rpx;
  overflow: hidden;
  background: #ffffff;
  border: 1rpx solid rgba(229, 230, 230, 0.95);
}

.record-detail-summary__row {
  display: grid;
  align-items: stretch;
}

.record-detail-summary__row--top {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.record-detail-summary__row--bottom {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: 1rpx solid rgba(229, 230, 230, 0.95);
}

.record-detail-summary__cell {
  box-sizing: border-box;
  min-height: 134rpx;
  padding: 22rpx 16rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.record-detail-summary__row--top .record-detail-summary__cell + .record-detail-summary__cell,
.record-detail-summary__row--bottom .record-detail-summary__cell + .record-detail-summary__cell {
  border-left: 1rpx solid rgba(229, 230, 230, 0.95);
}

.record-detail-summary__row--bottom .record-detail-summary__cell {
  min-height: 124rpx;
}

.record-detail-summary__label {
  color: #0a2146;
  font-size: 24rpx;
  line-height: 32rpx;
  font-weight: 500;
}

.record-detail-summary__value {
  margin-top: 10rpx;
  color: #0a2146;
  font-size: 40rpx;
  line-height: 1.1;
  font-weight: 700;
}

.record-detail-summary__value--accent {
  color: #0878EE;
}

.record-detail-action {
  margin-top: 30rpx;
  height: 86rpx;
  border-radius: 43rpx;
  background: linear-gradient(180deg, #59A9FF 0%, #0868F4 100%);
  color: #ffffff;
  font-size: 30rpx;
  font-weight: 700;
}

.record-detail-action::after {
  border: 0;
}
</style>
