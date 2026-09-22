<template>
  <view v-if="visible" class="binding-required-dialog" @touchmove.stop.prevent>
    <view class="binding-required-dialog__mask" @tap="close" />
    <view class="binding-required-dialog__panel" role="dialog" :aria-label="title" @tap.stop>
      <button class="binding-required-dialog__close" aria-label="关闭" @tap="close">
        <uv-icon name="close" :size="25" color="#747b83" />
      </button>

      <view class="binding-required-dialog__hero">
        <image src="/static/profile-settings/profile-organization.svg" mode="aspectFit" />
      </view>

      <text class="binding-required-dialog__title">{{ title }}</text>
      <text class="binding-required-dialog__description">{{ description }}</text>

      <view class="binding-required-dialog__notice">
        <image src="/static/profile-settings/settings-security.svg" mode="aspectFit" />
        <text>{{ notice }}</text>
      </view>

      <view class="binding-required-dialog__actions">
        <button class="binding-required-dialog__service" @tap="contactService">{{ serviceText }}</button>
        <button class="binding-required-dialog__confirm" @tap="bind">
          <image src="/static/profile-settings/profile-organization.svg" mode="aspectFit" />
          <text>{{ confirmText }}</text>
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  visible: boolean
  title?: string
  description?: string
  notice?: string
  serviceText?: string
  confirmText?: string
}>(), {
  title: '题库训练暂不可用',
  description: '请先绑定企业，绑定成功后即可进入题库训练。',
  notice: '绑定后可使用所属企业提供的题库训练内容。',
  serviceText: '联系客服',
  confirmText: '去绑定'
})

const emit = defineEmits<{
  close: []
  service: []
  bind: []
}>()

function close() {
  emit('close')
}

function contactService() {
  emit('service')
}

function bind() {
  emit('bind')
}
</script>

<style scoped lang="scss">
.binding-required-dialog {
  position: fixed;
  z-index: 1200;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 30rpx;
}

.binding-required-dialog__mask {
  position: absolute;
  inset: 0;
  background: rgba(11, 24, 35, 0.54);
}

.binding-required-dialog__panel {
  position: relative;
  box-sizing: border-box;
  width: min(500rpx, calc(100vw - 74rpx));
  padding: 32rpx 28rpx 24rpx;
  border-radius: 22rpx;
  background: #FFFFFF;
  box-shadow: 0 22rpx 62rpx rgba(0, 0, 0, 0.24);
}

.binding-required-dialog__close,
.binding-required-dialog__service,
.binding-required-dialog__confirm {
  margin: 0;
  padding: 0;
}

.binding-required-dialog__close::after,
.binding-required-dialog__service::after,
.binding-required-dialog__confirm::after {
  border: 0;
}

.binding-required-dialog__close {
  position: absolute;
  top: 22rpx;
  right: 20rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56rpx;
  height: 56rpx;
  border: 1rpx solid #e4e2df;
  border-radius: 50%;
  background: #FFFFFF;
}

.binding-required-dialog__hero {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 112rpx;
  height: 112rpx;
  margin: 0 auto;
  border-radius: 50%;
  background: #EAF4FF;
}

.binding-required-dialog__hero image {
  width: 72rpx;
  height: 82rpx;
}

.binding-required-dialog__title,
.binding-required-dialog__description,
.binding-required-dialog__notice text,
.binding-required-dialog__confirm text {
  display: block;
}

.binding-required-dialog__title {
  margin-top: 20rpx;
  color: #0a2539;
  font-size: 36rpx;
  line-height: 50rpx;
  font-weight: 700;
  text-align: center;
}

.binding-required-dialog__description {
  margin: 13rpx auto 0;
  color: #1c2a37;
  font-size: 25rpx;
  line-height: 38rpx;
  text-align: center;
}

.binding-required-dialog__notice {
  display: grid;
  grid-template-columns: 54rpx minmax(0, 1fr);
  column-gap: 14rpx;
  align-items: center;
  min-height: 94rpx;
  margin-top: 22rpx;
  padding: 12rpx 18rpx;
  border-radius: 14rpx;
  background: #EDF5FD;
}

.binding-required-dialog__notice image {
  width: 48rpx;
  height: 54rpx;
}

.binding-required-dialog__notice text {
  color: #25323c;
  font-size: 22rpx;
  line-height: 32rpx;
}

.binding-required-dialog__actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.12fr);
  gap: 18rpx;
  margin-top: 24rpx;
}

.binding-required-dialog__service,
.binding-required-dialog__confirm {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 70rpx;
  border-radius: 13rpx;
  font-size: 29rpx;
  line-height: 70rpx;
  font-weight: 500;
}

.binding-required-dialog__service {
  border: 1rpx solid #D8E4F0;
  background: #FFFFFF;
  color: #182532;
}

.binding-required-dialog__confirm {
  gap: 10rpx;
  border: 0;
  background: #0868F4;
  color: #fff;
}

.binding-required-dialog__confirm image {
  width: 38rpx;
  height: 44rpx;
  filter: brightness(0) invert(1);
}
</style>
