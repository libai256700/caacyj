<template>
  <view v-if="visible" class="account-cancellation-dialog" @touchmove.stop.prevent>
    <view class="account-cancellation-dialog__mask" @tap="close" />
    <view class="account-cancellation-dialog__panel" role="dialog" aria-label="注销账号" @tap.stop>
      <button class="account-cancellation-dialog__close" aria-label="关闭" @tap="close">
        <uv-icon name="close" :size="25" color="#73777c" />
      </button>

      <view class="account-cancellation-dialog__hero">
        <view class="account-cancellation-dialog__hero-user">
          <image src="/static/profile-settings/settings-cancel-account.svg" mode="aspectFit" />
        </view>
        <view class="account-cancellation-dialog__hero-security">
          <image src="/static/profile-settings/settings-security.svg" mode="aspectFit" />
        </view>
      </view>

      <text class="account-cancellation-dialog__title">注销账号</text>
      <text class="account-cancellation-dialog__description">
        当前暂不支持自助注销。如需处理，<br />请联系客服协助核验账号信息。
      </text>

      <view class="account-cancellation-dialog__notice">
        <image src="/static/profile-settings/settings-security.svg" mode="aspectFit" />
        <text>为保障账号与学习数据安全，<br />客服确认后将告知后续处理流程。</text>
      </view>

      <view class="account-cancellation-dialog__actions">
        <button class="account-cancellation-dialog__cancel" @tap="close">取消</button>
        <button class="account-cancellation-dialog__service" @tap="contactService">
          <image src="/static/profile-settings/settings-service.svg" mode="aspectFit" />
          <text>联系客服</text>
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  service: []
}>()

function close() {
  emit('close')
}

function contactService() {
  emit('service')
}
</script>

<style scoped lang="scss">
.account-cancellation-dialog {
  position: fixed;
  z-index: 1200;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32rpx;
}

.account-cancellation-dialog__mask {
  position: absolute;
  inset: 0;
  background: rgba(18, 18, 18, 0.54);
  backdrop-filter: blur(1rpx);
}

.account-cancellation-dialog__panel {
  position: relative;
  box-sizing: border-box;
  width: min(528rpx, calc(100vw - 72rpx));
  padding: 26rpx 28rpx 22rpx;
  border-radius: 26rpx;
  background: #FFFFFF;
  box-shadow: 0 22rpx 58rpx rgba(0, 0, 0, 0.22);
}

.account-cancellation-dialog__close,
.account-cancellation-dialog__cancel,
.account-cancellation-dialog__service {
  margin: 0;
  padding: 0;
}

.account-cancellation-dialog__close::after,
.account-cancellation-dialog__cancel::after,
.account-cancellation-dialog__service::after {
  border: 0;
}

.account-cancellation-dialog__close {
  position: absolute;
  top: 22rpx;
  right: 18rpx;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 58rpx;
  height: 58rpx;
  border: 1rpx solid #dfe9f3;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.72);
}

.account-cancellation-dialog__hero {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 112rpx;
  height: 112rpx;
  margin: 0 auto;
  border-radius: 50%;
  background: #EAF4FF;
}

.account-cancellation-dialog__hero-user {
  width: 70rpx;
  height: 80rpx;
  transform: translateX(-10rpx);
}

.account-cancellation-dialog__hero-security {
  position: absolute;
  right: 13rpx;
  bottom: 12rpx;
  width: 45rpx;
  height: 49rpx;
  padding: 3rpx;
  border-radius: 14rpx;
  background: #EAF4FF;
}

.account-cancellation-dialog__hero image,
.account-cancellation-dialog__notice image,
.account-cancellation-dialog__service image {
  display: block;
  width: 100%;
  height: 100%;
}

.account-cancellation-dialog__title,
.account-cancellation-dialog__description,
.account-cancellation-dialog__notice text,
.account-cancellation-dialog__service text {
  display: block;
}

.account-cancellation-dialog__title {
  margin-top: 14rpx;
  color: #0a2337;
  font-size: 38rpx;
  line-height: 52rpx;
  font-weight: 700;
  text-align: center;
}

.account-cancellation-dialog__description {
  margin-top: 12rpx;
  color: #192633;
  font-size: 26rpx;
  line-height: 36rpx;
  font-weight: 400;
  text-align: center;
}

.account-cancellation-dialog__notice {
  display: grid;
  grid-template-columns: 58rpx minmax(0, 1fr);
  column-gap: 16rpx;
  align-items: center;
  box-sizing: border-box;
  min-height: 88rpx;
  margin-top: 18rpx;
  padding: 12rpx 20rpx;
  border-radius: 14rpx;
  background: #EDF5FD;
}

.account-cancellation-dialog__notice image {
  width: 58rpx;
  height: 64rpx;
}

.account-cancellation-dialog__notice text {
  color: #1d2a37;
  font-size: 22rpx;
  line-height: 33rpx;
  font-weight: 400;
}

.account-cancellation-dialog__actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.22fr);
  gap: 20rpx;
  margin-top: 24rpx;
}

.account-cancellation-dialog__cancel,
.account-cancellation-dialog__service {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 72rpx;
  border-radius: 14rpx;
  font-size: 28rpx;
  line-height: 72rpx;
  font-weight: 500;
}

.account-cancellation-dialog__cancel {
  border: 1rpx solid #D8E4F0;
  background: #FFFFFF;
  color: #182433;
}

.account-cancellation-dialog__service {
  gap: 12rpx;
  border: 0;
  background: #005BD8;
  color: #ffffff;
}

.account-cancellation-dialog__service image {
  width: 40rpx;
  height: 46rpx;
  filter: brightness(0) invert(1);
}

.account-cancellation-dialog__service text {
  line-height: 1;
}
</style>
