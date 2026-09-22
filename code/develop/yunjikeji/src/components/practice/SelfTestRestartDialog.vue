<template>
  <view v-if="visible" class="self-test-restart-dialog" @touchmove.stop.prevent>
    <view class="self-test-restart-dialog__mask" @tap="handleMaskTap" />

    <view
      class="self-test-restart-dialog__panel"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      @tap.stop
    >
      <view class="self-test-restart-dialog__heading">
        <view class="self-test-restart-dialog__heading-mark" aria-hidden="true" />
        <text class="self-test-restart-dialog__title">{{ title }}</text>
      </view>

      <text class="self-test-restart-dialog__description">{{ description }}</text>

      <view
        class="self-test-restart-dialog__actions"
        :class="{ 'self-test-restart-dialog__actions--confirm-only': !showCancel }"
      >
        <button v-if="showCancel" class="self-test-restart-dialog__cancel" @tap="cancel">
          <text>取消</text>
        </button>
        <button class="self-test-restart-dialog__confirm" @tap="confirm">
          <text>{{ confirmText }}</text>
          <uv-icon name="reload" color="#ffffff" size="38rpx" />
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  visible: boolean
  title?: string
  description?: string
  confirmText?: string
  showCancel?: boolean
  closeOnMask?: boolean
}>(), {
  title: '重新测评',
  description: '已有测评记录，是否重新测评？',
  confirmText: '重新测评',
  showCancel: true,
  closeOnMask: false
})

const emit = defineEmits<{
  cancel: []
  confirm: []
}>()

function cancel() {
  emit('cancel')
}

function handleMaskTap() {
  if (props.closeOnMask) {
    cancel()
  }
}

function confirm() {
  emit('confirm')
}
</script>

<style scoped lang="scss">
.self-test-restart-dialog {
  position: fixed;
  z-index: 1500;
  inset: 0;
  display: flex;
  box-sizing: border-box;
  padding: var(--app-safe-area-top) 32rpx env(safe-area-inset-bottom);
  align-items: center;
  justify-content: center;
}

.self-test-restart-dialog__mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.56);
}

.self-test-restart-dialog__panel {
  position: relative;
  box-sizing: border-box;
  width: min(528rpx, calc(100vw - 64rpx));
  padding: 40rpx 34rpx 34rpx;
  border: 1rpx solid #6FB7FF;
  border-radius: 24rpx;
  background: #F1F7FD;
  box-shadow: 0 10rpx 26rpx rgba(15, 57, 105, 0.2);
}

.self-test-restart-dialog__cancel,
.self-test-restart-dialog__confirm {
  margin: 0;
  padding: 0;
}

.self-test-restart-dialog__cancel::after,
.self-test-restart-dialog__confirm::after {
  border: 0;
}

.self-test-restart-dialog__heading {
  display: flex;
  height: 44rpx;
  align-items: center;
  gap: 18rpx;
}

.self-test-restart-dialog__heading-mark {
  width: 10rpx;
  height: 40rpx;
  flex: 0 0 auto;
  border-radius: 5rpx;
  background: #0A67DA;
}

.self-test-restart-dialog__title,
.self-test-restart-dialog__description,
.self-test-restart-dialog__cancel text,
.self-test-restart-dialog__confirm text {
  display: block;
  letter-spacing: 0;
}

.self-test-restart-dialog__title {
  color: #09244a;
  font-size: 34rpx;
  line-height: 44rpx;
  font-weight: 700;
  white-space: nowrap;
}

.self-test-restart-dialog__description {
  margin-top: 22rpx;
  color: #0a254b;
  font-size: 30rpx;
  line-height: 44rpx;
  font-weight: 400;
  text-align: center;
  white-space: nowrap;
}

.self-test-restart-dialog__actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.12fr);
  gap: 20rpx;
  margin-top: 28rpx;
}

.self-test-restart-dialog__actions--confirm-only {
  grid-template-columns: minmax(0, 1fr);
}

.self-test-restart-dialog__cancel,
.self-test-restart-dialog__confirm {
  display: flex;
  height: 74rpx;
  box-sizing: border-box;
  align-items: center;
  justify-content: center;
  border-radius: 15rpx;
  font-size: 30rpx;
  line-height: 74rpx;
  font-weight: 500;
}

.self-test-restart-dialog__cancel {
  border: 2rpx solid #167EE8;
  background: #F1F7FD;
  color: #09244a;
}

.self-test-restart-dialog__confirm {
  gap: 12rpx;
  border: 0;
  background: #167EE8;
  color: #ffffff;
  box-shadow: 0 6rpx 12rpx rgba(22, 126, 232, 0.16);
}

.self-test-restart-dialog__cancel text,
.self-test-restart-dialog__confirm text {
  line-height: 1;
  white-space: nowrap;
}

.self-test-restart-dialog__confirm :deep(.uv-icon) {
  flex: 0 0 auto;
}
</style>
