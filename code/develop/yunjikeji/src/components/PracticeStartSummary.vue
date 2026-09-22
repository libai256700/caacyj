<template>
  <view class="practice-start">
    <view class="practice-start__paper">
      <view v-if="showIntro" class="practice-start__intro">
        <text class="practice-start__heading">确认练习信息</text>
        <text class="practice-start__subheading">请确认以下练习范围与规则，准备开始练习</text>
      </view>

      <view class="practice-start-card">
        <view class="practice-start-info">
          <view v-for="item in infoItems" :key="item.label" class="practice-start-info__item">
            <text class="practice-start-info__label">{{ item.label }}</text>
            <text class="practice-start-info__value">{{ item.value }}</text>
          </view>
        </view>

        <view class="practice-start-card__divider"></view>

        <view class="practice-start-rules">
          <view v-for="rule in ruleItems" :key="rule.label" class="practice-start-rules__row">
            <view class="practice-start-rules__copy">
              <text class="practice-start-rules__label">{{ rule.label }}</text>
              <text class="practice-start-rules__value">{{ rule.value }}</text>
            </view>
          </view>
        </view>

        <view aria-hidden="true" class="practice-start-card__diagram">
          <image
            class="practice-start-card__diagram-image"
            src="/static/practice-start/practice-diagrams.jpg"
            mode="widthFix"
          />
        </view>
      </view>

      <view class="practice-start-actions">
        <button class="practice-start-actions__primary" :loading="loading" :disabled="actionsDisabled" @tap="$emit('start')">
          <view class="practice-start-actions__play">
            <uv-icon name="play-right-fill" color="#0868F4" size="29rpx" />
          </view>
          <text>开始练习</text>
        </button>

        <button class="practice-start-actions__secondary" :disabled="actionsDisabled" @tap="$emit('wrong-review')">
          <text>错题复练</text>
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PracticeStartPage } from '@/services/practice'

const props = withDefaults(defineProps<{
  practice: PracticeStartPage
  category?: string
  loading?: boolean
  disabled?: boolean
  showIntro?: boolean
}>(), {
  category: '',
  loading: false,
  disabled: false,
  showIntro: true
})

defineEmits<{
  start: []
  'wrong-review': []
}>()

const actionsDisabled = computed(() => props.loading || props.disabled)

const infoItems = computed(() => [
  {
    label: '题目分类',
    value: props.category || props.practice.category || '综合练习',
    iconUrl: '/static/practice-start-icons/info-category.png',
    watermarkUrl: '/static/practice-start-icons/watermark-category.png'
  }
])

const ruleItems = computed(() => [
  { label: '题量', value: props.loading ? '--' : `${props.practice.questionCount}题`, iconUrl: '/static/practice-start-icons/rule-count.png' },
  { label: '总分', value: props.loading ? '--' : `${props.practice.totalScore}分`, iconUrl: '/static/practice-start-icons/rule-score.png' },
  { label: '答题时间', value: props.loading ? '--' : `${props.practice.timeLimitMinutes}分钟`, iconUrl: '/static/practice-start-icons/rule-time.png' },
  { label: '考试类型', value: props.practice.gradingMode, iconUrl: '/static/practice-start-icons/rule-mode.png' }
])
</script>

<style lang="scss">
.practice-start { position: relative; }

.practice-start__paper {
  position: relative;
  box-sizing: border-box;
  min-height: calc(100vh - var(--app-safe-area-top) - 480rpx);
  padding: 0 21rpx 78rpx;
}

.practice-start__intro {
  padding: 12rpx 8rpx 34rpx;
}

.practice-start__heading,
.practice-start__subheading {
  display: block;
}

.practice-start__heading {
  color: #0b3150;
  font-size: 40rpx;
  line-height: 1.2;
  font-weight: 700;
}

.practice-start__subheading {
  margin-top: 14rpx;
  color: #637890;
  font-size: 25rpx;
  line-height: 1.45;
  font-weight: 600;
}

.practice-start-card {
  position: relative;
  box-sizing: border-box;
  overflow: hidden;
  min-height: 894rpx;
  padding: 0 31rpx 63rpx;
  border: 2rpx solid rgba(255, 255, 255, 0.96);
  border-radius: 23rpx;
  background-color: rgba(248, 251, 255, 0.94);
  box-shadow: 0 5rpx 12rpx rgba(53, 99, 158, 0.17), inset 0 1rpx 0 rgba(255, 255, 255, 0.96);
}

.practice-start-info {
  display: flex;
  flex-direction: column;
}

.practice-start-info__item {
  box-sizing: border-box;
  min-height: 121rpx;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 32rpx;
  padding: 19rpx 18rpx 16rpx;
  border-bottom: 1rpx solid rgba(104, 158, 219, 0.38);
}

.practice-start-info__label,
.practice-start-info__value {
  display: block;
  min-width: 0;
}

.practice-start-info__label {
  color: #0769E7;
  font-size: 31rpx;
  line-height: 1.2;
  font-weight: 700;
}

.practice-start-info__value {
  color: #06183F;
  font-size: 31rpx;
  line-height: 1.25;
  font-weight: 700;
  text-align: right;
  word-break: break-word;
}

.practice-start-card__divider {
  height: 0;
}

.practice-start-rules {
  position: relative;
  display: grid;
  grid-template-columns: 50% 50%;
  border-top: 0;
  border-bottom: 1rpx solid rgba(104, 158, 219, 0.38);
}

.practice-start-rules::before {
  position: absolute;
  z-index: 1;
  top: 33rpx;
  bottom: 25rpx;
  left: 50%;
  width: 1rpx;
  background: rgba(104, 158, 219, 0.38);
  content: '';
}

.practice-start-rules__row {
  box-sizing: border-box;
  min-width: 0;
  min-height: 213rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24rpx 14rpx;
}

.practice-start-rules__row:nth-child(odd) {
  border-right: 0;
}

.practice-start-rules__row:nth-child(-n + 2) {
  border-bottom: 1rpx solid rgba(104, 158, 219, 0.38);
}

.practice-start-rules__copy {
  min-width: 0;
  width: 100%;
  text-align: center;
}

.practice-start-rules__row:nth-child(odd) .practice-start-rules__copy {
  transform: translateX(-1rpx);
}

.practice-start-rules__row:nth-child(even) .practice-start-rules__copy {
  transform: translateX(1rpx);
}

.practice-start-rules__label,
.practice-start-rules__value {
  display: block;
}

.practice-start-rules__label {
  color: #0769E7;
  font-size: 28rpx;
  line-height: 1.25;
  font-weight: 700;
  white-space: nowrap;
}

.practice-start-rules__value {
  margin-top: 31rpx;
  color: #06183F;
  font-size: 40rpx;
  line-height: 1.2;
  font-weight: 700;
  white-space: nowrap;
}

.practice-start-card__diagram {
  width: 100%;
  margin-top: 44rpx;
  opacity: 1;
}

.practice-start-card__diagram-image {
  width: 100%;
  height: auto;
  display: block;
  mix-blend-mode: normal;
}

.practice-start-actions {
  display: flex;
  flex-direction: column;
  gap: 102rpx;
  margin: 0 15rpx;
  padding: 43rpx 0 0;
}

.practice-start-actions__primary,
.practice-start-actions__secondary {
  box-sizing: border-box;
  width: 100%;
  height: 110rpx;
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 31rpx;
  border-radius: 16rpx;
  font-size: 41rpx;
  line-height: 110rpx;
  font-weight: 700;
  letter-spacing: 0;
}

.practice-start-actions__primary::after,
.practice-start-actions__secondary::after {
  border: 0;
}

.practice-start-actions__primary {
  position: relative;
  color: #fff;
  border: 1rpx solid #0769F2;
  background: linear-gradient(90deg, #0875F5 0%, #0367EB 100%);
  box-shadow: 0 10rpx 18rpx rgba(24, 91, 176, 0.24), inset 0 1rpx 0 rgba(255, 255, 255, 0.45);
}

.practice-start-actions__play {
  width: 58rpx;
  height: 58rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #fff;
  transform: translateX(-20rpx);
}


.practice-start-actions__primary > text {
  transform: translateX(-20rpx);
}

.practice-start-actions__secondary {
  color: #167EE8;
  border: 2rpx solid #0878EE;
  background: rgba(247, 251, 255, 0.78);
  font-size: 32rpx;
}

.practice-start-actions__primary[disabled],
.practice-start-actions__secondary[disabled] {
  opacity: 0.58;
}

@media (max-width: 360px) {
  .practice-start__paper {
    padding-right: 21rpx;
    padding-left: 21rpx;
  }

  .practice-start-info__item {
    grid-template-columns: auto minmax(0, 1fr);
    gap: 22rpx;
    padding-right: 18rpx;
    padding-left: 18rpx;
  }

  .practice-start-info__label,
  .practice-start-info__value {
    font-size: 29rpx;
  }

  .practice-start-rules__label {
    font-size: 25rpx;
  }

  .practice-start-rules__value {
    font-size: 28rpx;
  }
}
</style>
