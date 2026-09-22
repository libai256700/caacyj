<template>
  <uv-overlay
    :show="props.visible"
    :duration="180"
    :opacity="0.7"
    :z-index="110"
  >
    <view class="submitted-dialog-layer" @tap.stop @touchmove.stop.prevent>
      <view
        class="submitted-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="报告正在生成"
      >
        <view class="submitted-dialog__hero" aria-hidden="true">
          <view class="submitted-dialog__document">
            <view class="submitted-dialog__document-fold"></view>
            <view class="submitted-dialog__chart">
              <view class="submitted-dialog__chart-bar submitted-dialog__chart-bar--short"></view>
              <view class="submitted-dialog__chart-bar submitted-dialog__chart-bar--tall"></view>
              <view class="submitted-dialog__chart-bar submitted-dialog__chart-bar--medium"></view>
            </view>
          </view>
        </view>

        <text class="submitted-dialog__eyebrow">已提交</text>
        <text class="submitted-dialog__title">报告正在生成</text>
        <text class="submitted-dialog__message">{{ props.message }}</text>

        <view class="submitted-dialog__notice">
          <view class="submitted-dialog__notice-icon" aria-hidden="true">
            <view class="submitted-dialog__notice-document"></view>
            <view class="submitted-dialog__notice-check"></view>
          </view>
          <text>{{ props.noticeText }}</text>
        </view>

        <button class="submitted-dialog__home" @tap="returnHome">
          <uv-icon name="home-fill" color="#ffffff" size="36rpx" />
          <text>返回首页</text>
        </button>
      </view>
    </view>
  </uv-overlay>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  visible: boolean
  message?: string
  noticeText?: string
}>(), {
  message: '自测报告正在生成中，请稍后在首页“自测结果”中查看。',
  noticeText: '生成完成后即可查看完整评测结果。'
})

const emit = defineEmits<{
  home: []
}>()

function returnHome() {
  emit('home')
}
</script>

<style scoped lang="scss">
.submitted-dialog-layer {
  box-sizing: border-box;
  display: flex;
  width: 100%;
  height: 100%;
  padding: var(--app-safe-area-top) 32rpx env(safe-area-inset-bottom);
  align-items: center;
  justify-content: center;
}

.submitted-dialog {
  box-sizing: border-box;
  display: flex;
  width: min(480rpx, calc(100vw - 64rpx));
  min-height: 580rpx;
  padding: 32rpx 35rpx 31rpx;
  align-items: center;
  flex-direction: column;
  border: 1rpx solid rgba(255, 255, 255, 0.9);
  border-radius: 19rpx;
  background: #FFFFFF;
  box-shadow: 0 18rpx 38rpx rgba(0, 0, 0, 0.18);
  transform: translateY(38rpx);
}

.submitted-dialog__hero {
  position: relative;
  display: flex;
  width: 126rpx;
  height: 126rpx;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: conic-gradient(
    from -6deg,
    #0868F4 0 15%,
    #EAF4FF 15% 20%,
    #99C9F2 20% 42%,
    #EAF4FF 42% 47%,
    #0868F4 47% 69%,
    #EAF4FF 69% 74%,
    #6FB7FF 74% 95%,
    #EAF4FF 95% 100%
  );
}

.submitted-dialog__hero::before {
  position: absolute;
  inset: 8rpx;
  border-radius: 50%;
  background: #FFFFFF;
  content: '';
}

.submitted-dialog__document {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  width: 45rpx;
  height: 58rpx;
  border: 4rpx solid #0868F4;
  border-radius: 4rpx;
}

.submitted-dialog__document-fold {
  position: absolute;
  top: -4rpx;
  right: -4rpx;
  box-sizing: border-box;
  width: 19rpx;
  height: 19rpx;
  border-left: 4rpx solid #0868F4;
  border-bottom: 4rpx solid #0868F4;
  background: #FFFFFF;
}

.submitted-dialog__document-fold::before {
  position: absolute;
  top: -3rpx;
  left: -2rpx;
  width: 21rpx;
  height: 4rpx;
  background: #0868F4;
  content: '';
  transform: rotate(45deg);
  transform-origin: left center;
}

.submitted-dialog__chart {
  position: absolute;
  right: 7rpx;
  bottom: 8rpx;
  left: 7rpx;
  display: flex;
  height: 25rpx;
  align-items: flex-end;
  gap: 4rpx;
}

.submitted-dialog__chart-bar {
  flex: 1;
  border-radius: 1rpx 1rpx 0 0;
  background: #0868F4;
}

.submitted-dialog__chart-bar--short { height: 12rpx; }
.submitted-dialog__chart-bar--tall { height: 25rpx; }
.submitted-dialog__chart-bar--medium { height: 18rpx; }

.submitted-dialog__eyebrow,
.submitted-dialog__title,
.submitted-dialog__message,
.submitted-dialog__notice text,
.submitted-dialog__home text {
  display: block;
  letter-spacing: 0;
}

.submitted-dialog__eyebrow {
  margin-top: 18rpx;
  color: #42454a;
  font-size: 25rpx;
  line-height: 36rpx;
  font-weight: 400;
  text-align: center;
}

.submitted-dialog__title {
  margin-top: 20rpx;
  color: #09284f;
  font-size: 34rpx;
  line-height: 46rpx;
  font-weight: 700;
  text-align: center;
}

.submitted-dialog__message {
  max-width: 414rpx;
  margin-top: 14rpx;
  color: #172b46;
  font-size: 23rpx;
  line-height: 34rpx;
  font-weight: 400;
  text-align: center;
}

.submitted-dialog__notice {
  display: grid;
  grid-template-columns: 43rpx minmax(0, 1fr);
  column-gap: 12rpx;
  align-items: center;
  box-sizing: border-box;
  width: 410rpx;
  max-width: 100%;
  height: 72rpx;
  margin-top: 27rpx;
  padding: 0 24rpx;
  border-radius: 11rpx;
  background: #E7F2FF;
}

.submitted-dialog__notice-icon {
  position: relative;
  width: 40rpx;
  height: 46rpx;
}

.submitted-dialog__notice-document {
  position: absolute;
  left: 2rpx;
  top: 1rpx;
  box-sizing: border-box;
  width: 28rpx;
  height: 38rpx;
  border: 3rpx solid #0868F4;
  border-radius: 3rpx;
}

.submitted-dialog__notice-document::before {
  position: absolute;
  right: -3rpx;
  top: -3rpx;
  box-sizing: border-box;
  width: 11rpx;
  height: 11rpx;
  border-left: 3rpx solid #0868F4;
  border-bottom: 3rpx solid #0868F4;
  background: #E7F2FF;
  content: '';
}

.submitted-dialog__notice-check {
  position: absolute;
  right: 0;
  bottom: 0;
  box-sizing: border-box;
  width: 21rpx;
  height: 21rpx;
  border: 2rpx solid #0868F4;
  border-radius: 50%;
  background: #E7F2FF;
}

.submitted-dialog__notice-check::before {
  position: absolute;
  left: 5rpx;
  top: 5rpx;
  box-sizing: border-box;
  width: 9rpx;
  height: 5rpx;
  border-left: 2rpx solid #0868F4;
  border-bottom: 2rpx solid #0868F4;
  content: '';
  transform: rotate(-45deg);
}

.submitted-dialog__notice text {
  color: #36393e;
  font-size: 20rpx;
  line-height: 30rpx;
  font-weight: 400;
  white-space: nowrap;
}

.submitted-dialog__home {
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 410rpx;
  max-width: 100%;
  height: 65rpx;
  margin: 31rpx 0 0;
  padding: 0;
  gap: 18rpx;
  border-radius: 8rpx;
  background: linear-gradient(90deg, #005BD8 0%, #168BF2 100%);
  color: #ffffff;
  box-shadow: 0 8rpx 18rpx rgba(8, 104, 244, 0.2);
}

.submitted-dialog__home::after {
  border: 0;
}

.submitted-dialog__home text {
  font-size: 27rpx;
  line-height: 65rpx;
  font-weight: 500;
  white-space: nowrap;
}
</style>
