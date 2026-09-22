<template>
  <view class="practice-record-card">
    <text class="practice-record-card__title">{{ record.title }}</text>

    <view class="practice-record-card__metrics practice-record-card__metrics--top">
      <view class="practice-record-card__metric">
        <text class="practice-record-card__label">满分</text>
        <text class="practice-record-card__value">{{ record.totalScore }}</text>
      </view>
      <view class="practice-record-card__metric">
        <text class="practice-record-card__label practice-record-card__label--primary">实际得分</text>
        <text class="practice-record-card__value practice-record-card__value--primary">{{ record.score }}</text>
      </view>
      <view class="practice-record-card__metric">
        <text class="practice-record-card__label">正确数</text>
        <text class="practice-record-card__value">{{ record.correctCount }}</text>
      </view>
    </view>

    <view class="practice-record-card__divider"></view>

    <view class="practice-record-card__metrics practice-record-card__metrics--bottom">
      <view class="practice-record-card__metric practice-record-card__metric--wrong">
        <text class="practice-record-card__label">错误数</text>
        <text class="practice-record-card__value practice-record-card__value--small">{{ record.wrongCount }}</text>
      </view>
      <view class="practice-record-card__metric practice-record-card__metric--time">
        <text class="practice-record-card__label">练习时间</text>
        <text class="practice-record-card__time">{{ record.practicedAt }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import type { PracticeRecord } from '@/services/practice'

defineProps<{
  record: PracticeRecord
}>()
</script>

<style lang="scss">
.practice-record-card {
  box-sizing: border-box;
  overflow: hidden;
  min-height: 360rpx;
  border-radius: 27rpx;
  padding: 32rpx 34rpx 25rpx;
  background:
    linear-gradient(rgba(255, 255, 255, 0.74), rgba(255, 255, 255, 0.74)),
    url('@/static/practice-start/paper-texture.jpg') center / 320rpx 150rpx repeat;
  border: 1rpx solid rgba(222, 232, 242, 0.5);
  box-shadow:
    0 8rpx 20rpx rgba(26, 67, 115, 0.13),
    inset 0 1rpx 0 rgba(255, 255, 255, 0.92);
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}

.practice-record-card__title,
.practice-record-card__label,
.practice-record-card__value,
.practice-record-card__time {
  display: block;
}

.practice-record-card__title {
  color: #0a2146;
  font-size: 32rpx;
  line-height: 44rpx;
  font-weight: 700;
}

.practice-record-card__metrics {
  display: grid;
  align-items: stretch;
}

.practice-record-card__metrics--top {
  grid-template-columns: 185rpx 220rpx minmax(0, 1fr);
  margin-top: 34rpx;
}

.practice-record-card__metrics--bottom {
  grid-template-columns: 196rpx minmax(0, 1fr);
}

.practice-record-card__metric {
  position: relative;
  box-sizing: border-box;
  min-width: 0;
  min-height: 92rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  text-align: center;
}

.practice-record-card__metrics--top .practice-record-card__metric + .practice-record-card__metric::before,
.practice-record-card__metrics--bottom .practice-record-card__metric + .practice-record-card__metric::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 8rpx;
  width: 1rpx;
  border-radius: 999rpx;
  background: #e5e6e6;
}

.practice-record-card__metrics--bottom .practice-record-card__metric + .practice-record-card__metric::before {
  top: 0;
  bottom: 0;
}

.practice-record-card__label {
  color: #0a2146;
  font-size: 22rpx;
  line-height: 32rpx;
  font-weight: 400;
}

.practice-record-card__metrics--top .practice-record-card__label {
  line-height: 28rpx;
}

.practice-record-card__label--primary {
  color: #0a2146;
}

.practice-record-card__value {
  margin-top: 10rpx;
  color: #0a2146;
  font-size: 42rpx;
  line-height: 48rpx;
  font-weight: 600;
}

.practice-record-card__value--primary {
  margin-top: 10rpx;
  color: #0878EE;
  font-size: 42rpx;
}

.practice-record-card__value--small {
  margin-top: 8rpx;
  font-size: 34rpx;
  line-height: 38rpx;
}

.practice-record-card__divider {
  height: 1rpx;
  margin: 27rpx 0 24rpx;
  background: #e5e6e6;
}

.practice-record-card__time {
  max-width: 100%;
  margin-top: 8rpx;
  color: #0a2146;
  font-size: 26rpx;
  line-height: 38rpx;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.practice-record-card__metrics--top .practice-record-card__metric:first-child {
  padding-right: 32rpx;
}

.practice-record-card__metrics--top .practice-record-card__metric:last-child {
  padding-left: 26rpx;
}

.practice-record-card__metric--wrong {
  padding-right: 32rpx;
}

.practice-record-card__metric--time .practice-record-card__label {
  align-self: flex-start;
  margin-left: 64rpx;
}

@media (max-width: 360px) {
  .practice-record-card {
    padding-left: 30rpx;
    padding-right: 30rpx;
  }

  .practice-record-card__title {
    font-size: 31rpx;
  }

  .practice-record-card__value {
    font-size: 41rpx;
  }

  .practice-record-card__value--primary {
    font-size: 41rpx;
  }

  .practice-record-card__time {
    font-size: 26rpx;
  }
}
</style>
