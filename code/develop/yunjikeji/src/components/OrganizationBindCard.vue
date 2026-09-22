<template>
  <view
    class="organization-card"
    :class="{
      'organization-card--current': current,
      [`organization-card--${buttonTone}`]: true
    }"
  >
    <image
      class="organization-card__logo"
      :src="organization.iconUrl"
      mode="aspectFit"
      :aria-label="`${organization.name}标志`"
    />

    <view class="organization-card__content">
      <text class="organization-card__name">{{ organization.name }}</text>
      <view class="organization-card__meta">
        <text>{{ organization.tag }}</text>
        <text class="organization-card__separator">|</text>
        <text class="organization-card__certification">已认证</text>
      </view>
    </view>

    <button
      class="organization-card__action"
      :class="`organization-card__action--${buttonTone}`"
      :disabled="disabled"
      @tap="emit('apply')"
    >
      <uv-icon
        v-if="buttonTone === 'success'"
        name="checkmark-circle-fill"
        color="#005BD8"
        size="36rpx"
      />
      <image
        v-else-if="buttonTone !== 'warning'"
        class="organization-card__apply-icon"
        src="/static/organization-bind/organization-apply.png"
        mode="aspectFit"
      />
      <text class="organization-card__action-text">{{ buttonText }}</text>
    </button>

    <image
      v-if="current"
      class="organization-card__wave"
      src="/static/organization-bind/organization-current-wave.png"
      mode="scaleToFill"
    />
  </view>
</template>

<script setup lang="ts">
import type { OrganizationSummary } from '@/services/organization'

defineProps<{
  organization: OrganizationSummary
  buttonText: string
  buttonTone: string
  disabled: boolean
  current?: boolean
}>()

const emit = defineEmits<{
  (event: 'apply'): void
}>()
</script>

<style lang="scss" scoped>
.organization-card {
  position: relative;
  display: grid;
  grid-template-columns: 132rpx minmax(0, 1fr) 174rpx;
  align-items: center;
  column-gap: 18rpx;
  width: 100%;
  height: 154rpx;
  padding: 0 26rpx 0 7rpx;
  box-sizing: border-box;
  overflow: hidden;
  border-radius: 24rpx;
  background: #fcfcfc;
  box-shadow: 0 8rpx 24rpx rgba(35, 73, 113, 0.08);
}

.organization-card--current {
  grid-template-columns: 132rpx minmax(0, 1fr) 160rpx;
  column-gap: 18rpx;
  height: 232rpx;
  padding: 0 22rpx 0 16rpx;
  border: 2rpx solid #CFE5FB;
  border-radius: 24rpx;
  background: #F2F7FC;
  box-shadow: 0 8rpx 22rpx rgba(89, 169, 255, 0.08);
}

.organization-card__logo,
.organization-card__content,
.organization-card__action {
  position: relative;
  z-index: 1;
}

.organization-card__logo {
  display: block;
  width: 132rpx;
  height: 132rpx;
  transform: translateY(-4rpx);
}

.organization-card--current .organization-card__logo {
  transform: translateY(-10rpx);
}

.organization-card--current .organization-card__content {
  transform: translateY(-6rpx);
}

.organization-card__content {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  gap: 6rpx;
}

.organization-card__name {
  display: block;
  overflow: hidden;
  color: #090909;
  font-size: 26rpx;
  line-height: 42rpx;
  font-weight: 500;
  letter-spacing: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.organization-card--current .organization-card__name {
  font-size: 30rpx;
  line-height: 44rpx;
  font-weight: 500;
  -webkit-text-stroke: 0.4rpx currentColor;
}

.organization-card__meta {
  display: flex;
  align-items: center;
  gap: 12rpx;
  color: #949494;
  font-size: 20rpx;
  line-height: 31rpx;
  font-weight: 400;
  letter-spacing: 0;
  white-space: nowrap;
}

.organization-card__separator {
  color: #aaa8a6;
}

.organization-card__certification {
  color: #10b85a;
}

.organization-card__action {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  width: 174rpx;
  height: 73rpx;
  margin: 0;
  padding: 0 6rpx;
  box-sizing: border-box;
  border-radius: 999rpx;
  color: #005BD8;
  background: #ffffff;
  box-shadow: inset 0 0 0 2rpx #005BD8;
  font-size: 28rpx;
  line-height: 1;
  font-weight: 500;
  letter-spacing: 0;
  white-space: nowrap;
}

.organization-card--current .organization-card__action {
  width: 160rpx;
  height: 66rpx;
  padding: 0 10rpx;
  font-size: 26rpx;
  transform: translateY(-10rpx);
}

.organization-card__action::after {
  border: 0;
}

.organization-card__action[disabled] {
  opacity: 1;
}

.organization-card__action--success[disabled] {
  color: #005BD8;
  background: #ffffff;
}

.organization-card__action--warning {
  padding: 0 8rpx;
  color: #168BF2;
  background: #F2F7FC;
  box-shadow: inset 0 0 0 2rpx rgba(89, 169, 255, 0.62);
  font-size: 23rpx;
}

.organization-card__action--danger {
  color: #dd5d4c;
  box-shadow: inset 0 0 0 2rpx rgba(221, 93, 76, 0.72);
  font-size: 25rpx;
}

.organization-card__apply-icon {
  display: block;
  flex: 0 0 32rpx;
  width: 32rpx;
  height: 32rpx;
}

.organization-card__action-text {
  flex: 0 0 auto;
  line-height: 1;
  white-space: nowrap;
}

.organization-card__wave {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 0;
  display: block;
  width: 100%;
  height: 89rpx;
  pointer-events: none;
}
</style>
