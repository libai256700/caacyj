<template>
  <view v-if="visible" class="about-dialog" @touchmove.stop.prevent>
    <view class="about-dialog__mask" @tap="close" />
    <view class="about-dialog__panel" role="dialog" :aria-label="title" @tap.stop>
      <button class="about-dialog__close" aria-label="关闭" @tap="close">
        <uv-icon name="close" :size="28" color="#68717d" />
      </button>

      <view class="about-dialog__mascot">
        <view class="about-dialog__mascot-ring">
          <image src="/static/brand/ai-assistant-logo.png" mode="aspectFit" />
        </view>
      </view>

      <text class="about-dialog__title">{{ title }}</text>
      <text class="about-dialog__subtitle">{{ subtitle }}</text>
      <text class="about-dialog__description">{{ description }}</text>

      <view class="about-dialog__features">
        <view v-for="feature in features" :key="feature.label" class="about-dialog__feature">
          <uv-icon :name="feature.icon" :size="34" color="#168BF2" />
          <text>{{ feature.label }}</text>
        </view>
      </view>

      <view class="about-dialog__slogan">
        <view />
        <text>{{ slogan }}</text>
        <view />
      </view>

      <button class="about-dialog__confirm" @tap="close">{{ confirmText }}</button>
    </view>
  </view>
</template>

<script setup lang="ts">
type Feature = {
  label: string
  icon: string
}

withDefaults(defineProps<{
  visible: boolean
  title?: string
  subtitle?: string
  description?: string
  slogan?: string
  confirmText?: string
  features?: Feature[]
}>(), {
  title: '关于小技',
  subtitle: '无人机学习与职业成长助手',
  description: '小技致力于为无人机学习者提供系统化的题库训练、知识答疑、自我测评与学习记录服务，帮助用户更高效地掌握飞行理论与实操知识。',
  slogan: '让每一次学习更有方向',
  confirmText: '知道了',
  features: () => [
    { label: '题库训练', icon: 'file-text' },
    { label: 'AI 答疑', icon: 'chat' },
    { label: '自我测评', icon: 'checkbox-mark' }
  ]
})

const emit = defineEmits<{
  close: []
}>()

function close() {
  emit('close')
}
</script>

<style scoped lang="scss">
.about-dialog {
  position: fixed;
  z-index: 1000;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28rpx;
}

.about-dialog__mask {
  position: absolute;
  inset: 0;
  background: rgba(8, 24, 39, 0.52);
}

.about-dialog__panel {
  position: relative;
  box-sizing: border-box;
  width: min(540rpx, calc(100vw - 56rpx));
  padding: 48rpx 38rpx 34rpx;
  border-radius: 10rpx;
  background: #FFFFFF;
  box-shadow: 0 24rpx 68rpx rgba(13, 25, 36, 0.28);
}

.about-dialog__close {
  position: absolute;
  top: 20rpx;
  right: 18rpx;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 58rpx;
  height: 58rpx;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
}

.about-dialog__close::after,
.about-dialog__confirm::after {
  border: 0;
}

.about-dialog__mascot {
  display: flex;
  justify-content: center;
}

.about-dialog__mascot-ring {
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 104rpx;
  height: 104rpx;
  overflow: hidden;
  border: 2rpx solid #168BF2;
  border-radius: 50%;
  background: #fff;
}

.about-dialog__mascot-ring image {
  width: 96rpx;
  height: 96rpx;
}

.about-dialog__title,
.about-dialog__subtitle,
.about-dialog__description,
.about-dialog__feature text,
.about-dialog__slogan text {
  display: block;
}

.about-dialog__title {
  margin-top: 22rpx;
  color: #0b2336;
  font-size: 38rpx;
  line-height: 52rpx;
  font-weight: 700;
  text-align: center;
}

.about-dialog__subtitle {
  margin-top: 4rpx;
  color: #314152;
  font-size: 23rpx;
  line-height: 34rpx;
  text-align: center;
}

.about-dialog__description {
  margin-top: 28rpx;
  color: #334250;
  font-size: 22rpx;
  line-height: 35rpx;
  text-align: left;
}

.about-dialog__features {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 28rpx;
}

.about-dialog__feature {
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 10rpx;
  min-width: 0;
  padding: 0 10rpx;
}

.about-dialog__feature + .about-dialog__feature {
  border-left: 1rpx solid #DDE8F2;
}

.about-dialog__feature text {
  overflow: hidden;
  max-width: 100%;
  color: #15293a;
  font-size: 21rpx;
  line-height: 30rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.about-dialog__slogan {
  display: grid;
  grid-template-columns: 44rpx auto 44rpx;
  gap: 14rpx;
  align-items: center;
  justify-content: center;
  margin-top: 30rpx;
}

.about-dialog__slogan view {
  height: 2rpx;
  background: #59A9FF;
}

.about-dialog__slogan text {
  color: #243746;
  font-size: 21rpx;
  line-height: 30rpx;
  white-space: nowrap;
}

.about-dialog__confirm {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 68rpx;
  margin-top: 28rpx;
  padding: 0;
  border: 0;
  border-radius: 8rpx;
  background: #168BF2;
  color: #fff;
  font-size: 29rpx;
  line-height: 68rpx;
  font-weight: 700;
}
</style>
