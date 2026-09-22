<template>
  <uv-overlay
    :show="props.show"
    :duration="180"
    :opacity="0.68"
    :z-index="90"
  >
    <view class="self-test-loading-layer" @tap="emit('close')">
      <view class="self-test-loading-dialog" role="status" aria-live="polite" @tap.stop>
        <view class="self-test-loading-indicator" aria-hidden="true">
          <image
            class="self-test-loading-drone"
            src="/static/practice-record/self-test-loading-drone-reference.png"
            mode="aspectFit"
          />
        </view>

        <text class="self-test-loading-dialog__title">{{ props.title }}</text>
        <text class="self-test-loading-dialog__message">{{ props.message }}</text>

        <view class="self-test-loading-dots" aria-hidden="true">
          <view class="self-test-loading-dot"></view>
          <view class="self-test-loading-dot"></view>
          <view class="self-test-loading-dot"></view>
        </view>
      </view>
    </view>
  </uv-overlay>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  show: boolean
  title?: string
  message?: string
}>(), {
  title: '正在加载自测题目',
  message: '请稍候,系统正在同步自测题目。'
})

const emit = defineEmits<{
  close: []
}>()
</script>

<style scoped lang="scss">
.self-test-loading-layer {
  box-sizing: border-box;
  display: flex;
  width: 100%;
  height: 100%;
  padding: var(--app-safe-area-top) 40rpx env(safe-area-inset-bottom);
  align-items: center;
  justify-content: center;
}

.self-test-loading-dialog {
  box-sizing: border-box;
  display: flex;
  width: 396rpx;
  max-width: calc(100vw - 80rpx);
  min-height: 366rpx;
  padding: 38rpx 26rpx 32rpx;
  align-items: center;
  flex-direction: column;
  border: 1rpx solid rgba(255, 255, 255, 0.82);
  border-radius: 20rpx;
  background: linear-gradient(145deg, #F8FBFF 0%, #f3f8fd 58%, #F8FBFF 100%);
  box-shadow: 0 4rpx 12rpx rgba(19, 24, 31, 0.12);
  transform: translateY(13rpx);
}

.self-test-loading-indicator {
  position: relative;
  display: flex;
  width: 124rpx;
  height: 124rpx;
  align-items: center;
  justify-content: center;
}

.self-test-loading-indicator::before,
.self-test-loading-indicator::after {
  position: absolute;
  border-radius: 50%;
  content: '';
}

.self-test-loading-indicator::before {
  inset: 0;
  background: conic-gradient(
    from -12deg,
    #0868F4 0 16%,
    transparent 16% 21%,
    #99C9F2 21% 43%,
    transparent 43% 48%,
    #0868F4 48% 72%,
    transparent 72% 77%,
    #6FB7FF 77% 96%,
    transparent 96% 100%
  );
  animation: self-test-loading-spin 1.65s linear infinite;
}

.self-test-loading-indicator::after {
  inset: 7rpx;
  background: #F8FBFF;
}

.self-test-loading-drone {
  z-index: 1;
  display: block;
  width: 65rpx;
  height: 58rpx;
  transform: translateY(3rpx);
}

.self-test-loading-dialog__title,
.self-test-loading-dialog__message {
  display: block;
  text-align: center;
  letter-spacing: 0;
}

.self-test-loading-dialog__title {
  margin-top: 23rpx;
  color: #09264b;
  font-size: 29rpx;
  line-height: 41rpx;
  font-weight: 750;
}

.self-test-loading-dialog__message {
  margin-top: 13rpx;
  color: #172b46;
  font-size: 21rpx;
  line-height: 34rpx;
  font-weight: 400;
  white-space: nowrap;
}

.self-test-loading-dots {
  display: flex;
  height: 17rpx;
  margin-top: 33rpx;
  align-items: center;
  justify-content: center;
  gap: 13rpx;
}

.self-test-loading-dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  background: #7DB9EE;
  animation: self-test-loading-pulse 1.2s ease-in-out infinite;
}

.self-test-loading-dot:nth-child(1) {
  background: #0A67DA;
  animation-delay: 0s;
}

.self-test-loading-dot:nth-child(2) { animation-delay: 0.16s; }

.self-test-loading-dot:nth-child(3) {
  background: #B7D9FA;
  animation-delay: 0.32s;
}

@keyframes self-test-loading-spin {
  to { transform: rotate(360deg); }
}

@keyframes self-test-loading-pulse {
  0%, 60%, 100% { transform: scale(0.88); opacity: 0.7; }
  30% { transform: scale(1); opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .self-test-loading-indicator::before,
  .self-test-loading-dot {
    animation: none;
  }
}
</style>
