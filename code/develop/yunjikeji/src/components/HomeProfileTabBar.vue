<template>
  <view
    class="bottom-nav"
    :class="{ 'bottom-nav--brand-ringless': props.hideBrandRing }"
  >
    <view class="bottom-nav__surface" aria-hidden="true" />
    <view
      class="nav-item"
      :class="{ 'nav-item--active': props.active === 'home' }"
      aria-label="首页"
      :aria-current="props.active === 'home' ? 'page' : undefined"
      role="button"
      @tap="openTab('home')"
    >
      <view class="nav-item__icon" aria-hidden="true">
        <uv-icon
          :name="props.active === 'home' ? 'home-fill' : 'home'"
          :color="props.active === 'home' ? '#0878EE' : '#0B2446'"
          size="22px"
          :bold="props.active === 'home'"
        />
      </view>
      <text class="nav-item__label">首页</text>
      <view
        v-if="props.active === 'home'"
        class="nav-item__indicator"
        :style="{ backgroundColor: props.indicatorColor }"
        aria-hidden="true"
      />
    </view>
    <view
      class="nav-item nav-item--center"
      :class="{ 'nav-item--active': props.active === 'center' }"
      :aria-label="isEnterprise ? '我的客服' : 'AI助手'"
      :aria-current="props.active === 'center' ? 'page' : undefined"
      role="button"
      @tap="openTab('center')"
    >
      <view
        class="nav-item__brand"
        :class="{ 'nav-item__brand--active': props.active === 'center' }"
        aria-hidden="true"
      >
        <image
          class="nav-item__brand-image"
          :src="props.brandImageSrc"
          mode="aspectFit"
        />
      </view>
      <view class="nav-item__label-spacer" aria-hidden="true" />
    </view>
    <view
      class="nav-item"
      :class="{ 'nav-item--active': props.active === 'profile' }"
      aria-label="我的"
      :aria-current="props.active === 'profile' ? 'page' : undefined"
      role="button"
      @tap="openTab('profile')"
    >
      <view class="nav-item__icon" aria-hidden="true">
        <uv-icon
          :name="props.active === 'profile' ? 'account-fill' : 'account'"
          :color="props.active === 'profile' ? '#0878EE' : '#0B2446'"
          size="22px"
          :bold="props.active === 'profile'"
        />
      </view>
      <text class="nav-item__label">我的</text>
      <view
        v-if="props.active === 'profile'"
        class="nav-item__indicator"
        :style="{ backgroundColor: props.indicatorColor }"
        aria-hidden="true"
      />
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { appState } from '@/stores/appState'

type TabTarget = 'home' | 'center' | 'profile'

const props = withDefaults(defineProps<{
  active?: TabTarget
  brandImageSrc?: string
  indicatorColor?: string
  hideBrandRing?: boolean
}>(), {
  active: 'home',
  brandImageSrc: '/static/home/bottom-nav-mascot-reference.png',
  indicatorColor: '#ff9709',
  hideBrandRing: false
})

const isEnterprise = computed(() => appState.loginIdentity === 'enterprise')

const routes: Record<TabTarget, string> = {
  home: '/pages/home',
  center: '/pages/center',
  profile: '/pages/profile'
}

function openTab(target: TabTarget) {
  if (props.active === target) return

  let url = routes[target]
  if (isEnterprise.value && target === 'home') {
    url = '/pages/enterprise/students'
  } else if (isEnterprise.value && target === 'center') {
    url = '/pages/service/customer-service'
  }

  if (target === 'profile') {
    uni.navigateTo({
      url,
      animationType: 'none',
      animationDuration: 0,
      fail: () => uni.reLaunch({ url })
    })
    return
  }

  if (props.active === 'profile') {
    uni.reLaunch({ url })
    return
  }

  uni.redirectTo({
    url,
    fail: () => uni.reLaunch({ url })
  })
}
</script>

<style scoped lang="scss">
.bottom-nav {
  position: fixed !important;
  z-index: 100;
  top: auto !important;
  right: 0 !important;
  bottom: 0 !important;
  left: 0 !important;
  width: 100%;
  max-width: 430px;
  height: 104rpx;
  max-height: 60px;
  margin: 0 auto;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: stretch;
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  transform: none !important;
  isolation: isolate;
  pointer-events: none;
}

.bottom-nav__surface {
  position: absolute;
  z-index: 0;
  right: 20rpx;
  bottom: 2rpx;
  left: 20rpx;
  height: 100rpx;
  max-height: 58px;
  border: 1px solid rgba(10, 54, 103, 0.06);
  border-radius: 36rpx;
  background: #ffffff;
  box-shadow: 0 5rpx 18rpx rgba(27, 67, 112, 0.15);
  pointer-events: none;
}

.nav-item {
  position: relative;
  z-index: 2;
  box-sizing: border-box;
  align-self: end;
  display: flex;
  width: 100%;
  height: 104rpx;
  max-height: 60px;
  padding: 6rpx 0 12rpx;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rpx;
  color: #0b2446;
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
  pointer-events: auto;
  -webkit-tap-highlight-color: transparent;
}

.nav-item--active {
  color: #0878ee;
}

.nav-item__icon {
  display: flex;
  width: 44rpx;
  max-width: 24px;
  height: 44rpx;
  max-height: 24px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
}

.nav-item__label {
  display: block;
  flex: 0 0 auto;
  color: inherit;
  font-size: clamp(10px, 22rpx, 12px);
  font-weight: 500;
  line-height: clamp(13px, 26rpx, 15px);
  letter-spacing: 0;
  white-space: nowrap;
}

.nav-item--active .nav-item__label {
  font-weight: 600;
}

.nav-item__indicator {
  position: absolute;
  bottom: 4rpx;
  left: 50%;
  width: 52rpx;
  max-width: 30px;
  height: 6rpx;
  max-height: 3px;
  border-radius: 999px;
  background: #ff9709;
  transform: translateX(-50%);
  pointer-events: none;
}

.nav-item--center {
  padding: 0;
}

.nav-item__brand {
  position: absolute;
  top: -25rpx;
  left: 50%;
  box-sizing: border-box;
  display: flex;
  width: 120rpx;
  max-width: 68px;
  height: 120rpx;
  max-height: 68px;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 0;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 3rpx 10rpx rgba(20, 91, 170, 0.14);
  transform: translateX(-50%);
  pointer-events: none;
}

.nav-item__brand--active {
  box-shadow: 0 3rpx 12rpx rgba(8, 120, 238, 0.24);
}

.bottom-nav--brand-ringless .nav-item__brand,
.bottom-nav--brand-ringless .nav-item__brand--active {
  background: transparent;
  box-shadow: none;
}

.nav-item__brand-image {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 50%;
}

.nav-item__label-spacer {
  width: 1px;
  height: clamp(13px, 26rpx, 15px);
  flex: 0 0 auto;
}
</style>
