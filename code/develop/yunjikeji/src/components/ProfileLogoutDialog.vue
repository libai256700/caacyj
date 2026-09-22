<template>
  <view v-if="visible" class="profile-logout-dialog" @touchmove.stop.prevent>
    <view class="profile-logout-dialog__mask" />

    <view
      class="profile-logout-dialog__panel"
      role="dialog"
      aria-modal="true"
      aria-label="退出登录"
      @tap.stop
    >
      <button class="profile-logout-dialog__close" aria-label="关闭" @tap="close">
        <view class="profile-logout-dialog__close-icon">
          <uv-icon name="close" size="24rpx" color="#7e8082" />
        </view>
      </button>

      <view class="profile-logout-dialog__hero">
        <image
          class="profile-logout-dialog__hero-icon"
          src="/static/profile-settings/logout.svg?v=uniform-menu-icons-1"
          mode="aspectFit"
          aria-hidden="true"
        />
      </view>

      <text class="profile-logout-dialog__title">退出登录</text>
      <text class="profile-logout-dialog__description">确认退出当前账号并返回登录页吗？</text>

      <view class="profile-logout-dialog__notice">
        <image src="/static/profile-settings/settings-security.svg" mode="aspectFit" />
        <text>退出后，再次使用小技需要重新登录。</text>
      </view>

      <view class="profile-logout-dialog__actions">
        <button class="profile-logout-dialog__cancel" @tap="close">
          <text>取消</text>
        </button>
        <button class="profile-logout-dialog__confirm" @tap="confirm">
          <image src="/static/profile-settings/logout.svg" mode="aspectFit" />
          <text>退出登录</text>
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
  confirm: []
}>()

function close() {
  emit('close')
}

function confirm() {
  emit('confirm')
}
</script>

<style scoped lang="scss">
.profile-logout-dialog {
  position: fixed;
  z-index: 1400;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  padding: 32rpx;
}

.profile-logout-dialog__mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.56);
}

.profile-logout-dialog__panel {
  position: relative;
  box-sizing: border-box;
  width: min(504rpx, calc(100vw - 64rpx));
  padding: 27rpx;
  border-radius: 18rpx;
  background: #F5F9FF;
  box-shadow: 0 4rpx 12rpx rgba(0, 0, 0, 0.12);
}

.profile-logout-dialog__close,
.profile-logout-dialog__cancel,
.profile-logout-dialog__confirm {
  margin: 0;
  padding: 0;
}

.profile-logout-dialog__close::after,
.profile-logout-dialog__cancel::after,
.profile-logout-dialog__confirm::after {
  border: 0;
}

.profile-logout-dialog__close {
  position: absolute;
  top: 25rpx;
  right: 21rpx;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 42rpx;
  height: 42rpx;
  border: 1rpx solid #E2EBF4;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.48);
  box-shadow: 0 2rpx 7rpx rgba(15, 36, 64, 0.05);
  line-height: 1;
}

.profile-logout-dialog__close-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  transform: translateY(2rpx);
}

.profile-logout-dialog__hero {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 112rpx;
  height: 112rpx;
  margin: 0 auto;
  border-radius: 50%;
  background: #EAF4FF;
  transform: translate(-6rpx, 2rpx);
}

.profile-logout-dialog__hero-icon {
  display: block;
  width: 68rpx;
  height: 78rpx;
  transform: translate(-2rpx, -1rpx) scale(0.97, 1.07);
}

.profile-logout-dialog__title,
.profile-logout-dialog__description,
.profile-logout-dialog__notice text,
.profile-logout-dialog__confirm text {
  display: block;
}

.profile-logout-dialog__title {
  margin-top: 14rpx;
  color: #111923;
  font-size: 32rpx;
  line-height: 48rpx;
  font-weight: 500;
  text-align: center;
  transform: translate(-4rpx, -4rpx) scale(0.985, 0.96);
  -webkit-text-stroke: 0.35px #111923;
}

.profile-logout-dialog__description {
  margin-top: 10rpx;
  color: #292b2f;
  font-size: 22.5rpx;
  line-height: 40rpx;
  font-weight: 400;
  text-align: center;
  transform: translate(5rpx, 4rpx) scaleY(0.96);
  white-space: nowrap;
}

.profile-logout-dialog__notice {
  display: grid;
  grid-template-columns: 42rpx minmax(0, 1fr);
  column-gap: 14rpx;
  align-items: center;
  box-sizing: border-box;
  height: 73rpx;
  margin-top: 27rpx;
  padding: 0 26rpx;
  border-radius: 12rpx;
  background: #EDF5FD;
}

.profile-logout-dialog__notice image {
  display: block;
  width: 42rpx;
  height: 46rpx;
  filter: saturate(1) brightness(0.9);
  transform: scaleX(1.1);
}

.profile-logout-dialog__notice text {
  color: #303030;
  font-size: 20rpx;
  line-height: 32rpx;
  font-weight: 400;
  transform: translateY(1rpx) scaleX(1.018);
  transform-origin: left center;
  white-space: nowrap;
}

.profile-logout-dialog__actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.21fr);
  gap: 28rpx;
  margin-top: 29rpx;
}

.profile-logout-dialog__cancel,
.profile-logout-dialog__confirm {
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  height: 70rpx;
  border-radius: 12rpx;
  font-size: 24rpx;
  line-height: 70rpx;
  font-weight: 500;
}

.profile-logout-dialog__cancel {
  border: 1rpx solid #E2EBF4;
  background: #F5F9FF;
  color: #111827;
}

.profile-logout-dialog__cancel text {
  display: block;
  line-height: 1;
  transform: translate(2rpx, -2rpx);
}

.profile-logout-dialog__confirm {
  gap: 20rpx;
  border: 0;
  background: #167EE8;
  color: #ffffff;
  box-shadow: 0 7rpx 16rpx rgba(22, 126, 232, 0.16);
}

.profile-logout-dialog__confirm image {
  display: block;
  width: 38rpx;
  height: 43rpx;
  filter: brightness(0) invert(1);
  transform: translateX(-4rpx) scaleY(1.1);
}

.profile-logout-dialog__confirm text {
  line-height: 1;
  transform: translateX(-4rpx);
  white-space: nowrap;
}
</style>
