<template>
  <view v-if="visible" class="assessment-choice-dialog" @touchmove.stop.prevent>
    <view class="assessment-choice-dialog__mask" @tap="close" />
    <view class="assessment-choice-dialog__panel" role="dialog" aria-modal="true" :aria-label="title" @tap.stop>
      <view class="assessment-choice-dialog__heading">
        <view class="assessment-choice-dialog__mark" aria-hidden="true" />
        <text class="assessment-choice-dialog__title">{{ title }}</text>
      </view>
      <text v-if="description" class="assessment-choice-dialog__description">{{ description }}</text>
      <view class="assessment-choice-dialog__actions">
        <button
          v-for="option in options"
          :key="option.value"
          class="assessment-choice-dialog__action"
          :class="{ 'assessment-choice-dialog__action--primary': option.primary }"
          @tap="select(option.value)"
        >{{ option.label }}</button>
      </view>
      <button class="assessment-choice-dialog__cancel" @tap="close">取消</button>
    </view>
  </view>
</template>

<script setup lang="ts">
export type AssessmentChoice = {
  value: string
  label: string
  primary?: boolean
}

defineProps<{
  visible: boolean
  title: string
  description?: string
  options: AssessmentChoice[]
}>()

const emit = defineEmits<{
  close: []
  select: [value: string]
}>()

const close = () => emit('close')
const select = (value: string) => emit('select', value)
</script>

<style scoped lang="scss">
.assessment-choice-dialog {
  position: fixed;
  z-index: 1500;
  inset: 0;
  display: flex;
  box-sizing: border-box;
  padding: var(--app-safe-area-top) 32rpx env(safe-area-inset-bottom);
  align-items: center;
  justify-content: center;
}

.assessment-choice-dialog__mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, .56);
}

.assessment-choice-dialog__panel {
  position: relative;
  box-sizing: border-box;
  width: min(544rpx, calc(100vw - 64rpx));
  padding: 40rpx 34rpx 30rpx;
  border: 1rpx solid #dce8f5;
  border-radius: 24rpx;
  background: #ffffff;
  box-shadow: 0 10rpx 26rpx rgba(7, 27, 60, .2);
}

.assessment-choice-dialog__heading {
  display: flex;
  align-items: center;
  gap: 18rpx;
}

.assessment-choice-dialog__mark {
  width: 10rpx;
  height: 40rpx;
  border-radius: 5rpx;
  background: #0868f4;
}

.assessment-choice-dialog__title {
  color: #071b3c;
  font-size: 34rpx;
  line-height: 44rpx;
  font-weight: 700;
}

.assessment-choice-dialog__description {
  display: block;
  margin: 22rpx 0 0;
  color: #0b345a;
  font-size: 28rpx;
  line-height: 42rpx;
}

.assessment-choice-dialog__actions {
  display: grid;
  gap: 18rpx;
  margin-top: 30rpx;
}

.assessment-choice-dialog__action,
.assessment-choice-dialog__cancel {
  box-sizing: border-box;
  height: 80rpx;
  margin: 0;
  padding: 0;
  border: 2rpx solid #0868f4;
  border-radius: 15rpx;
  background: #ffffff;
  color: #071b3c;
  font-size: 30rpx;
  line-height: 76rpx;
  font-weight: 500;
}

.assessment-choice-dialog__action::after,
.assessment-choice-dialog__cancel::after {
  border: 0;
}

.assessment-choice-dialog__action--primary {
  border-color: #0868f4;
  background: #0868f4;
  color: #fff;
}

.assessment-choice-dialog__cancel {
  height: 62rpx;
  margin-top: 12rpx;
  border: 0;
  background: transparent;
  color: #6f8098;
  font-size: 27rpx;
  line-height: 62rpx;
}
</style>
