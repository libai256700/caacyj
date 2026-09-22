<template>
  <view class="phone-bind-page" :style="$appSafeAreaStyle">
    <image
      class="phone-bind-page__background"
      src="/static/phone-bind/hero-drone-reference-390.png"
      mode="aspectFill"
    />

    <scroll-view class="phone-bind-page__scroll" scroll-y>
      <view class="phone-bind-page__content">
        <view class="phone-bind-nav">
          <button class="phone-bind-nav__back" aria-label="返回" @tap="goBack">
            <text class="phone-bind-nav__chevron" />
          </button>
          <text class="phone-bind-nav__title">绑定手机号</text>
          <view class="phone-bind-nav__ghost" />
        </view>

        <view class="bind-panel">
          <view class="bind-panel__heading">
            <text class="bind-panel__title">绑定手机号</text>
            <view class="bind-panel__mark" />
          </view>

          <view class="bind-form">
            <view class="bind-field">
              <view class="bind-field__icon-wrap">
                <image
                  class="bind-field__icon bind-field__icon--phone"
                  src="/static/phone-bind/phone-reference.png"
                  mode="aspectFit"
                />
              </view>
              <input
                v-model="phone"
                class="bind-field__input"
                type="number"
                maxlength="11"
                placeholder="请输入手机号"
                placeholder-class="bind-field__placeholder"
                :disabled="binding"
              />
            </view>

            <view class="bind-field bind-field--code">
              <view class="bind-field__icon-wrap">
                <image class="bind-field__icon bind-field__icon--shield" src="/static/phone-bind/code-shield-plus.svg" mode="aspectFit" />
              </view>
              <input
                v-model="verifyCode"
                class="bind-field__input"
                type="number"
                maxlength="6"
                placeholder="请输入验证码"
                placeholder-class="bind-field__placeholder"
                :disabled="binding"
              />
              <button class="bind-field__code-button" :disabled="!canRequestCode" @tap="requestCode">
                {{ codeButtonText }}
              </button>
            </view>

            <button class="bind-submit" :loading="binding" :disabled="binding" @tap="confirmBind">
              {{ binding ? '绑定中...' : '确认绑定' }}
            </button>
          </view>
        </view>

        <view class="bind-tip">
          <image class="bind-tip__icon" src="/static/phone-bind/info-reference.png" mode="aspectFit" />
          <text class="bind-tip__text">绑定成功后将使用该手机号作为登录账号和身份校验依据。</text>
        </view>

        <image
          class="phone-bind-training"
          src="/static/phone-bind/training-scene-reference-390.png"
          mode="widthFix"
        />
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { bindCustomerMobile, sendLoginSmsCode } from '@/services/customerAuth'
import {
  appState,
  clearUserSession,
  shouldPromptOrganizationBinding,
  updateUserPhoneBinding
} from '@/stores/appState'

const phone = ref('')
const verifyCode = ref('')
const binding = ref(false)
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

const normalizedPhone = computed(() => phone.value.replace(/\D/g, '').slice(0, 11))
const normalizedCode = computed(() => verifyCode.value.replace(/\D/g, '').slice(0, 6))
const canRequestCode = computed(() => !binding.value && countdown.value === 0)
const codeButtonText = computed(() => (countdown.value > 0 ? `${countdown.value}s后重试` : '获取验证码'))

onLoad(() => {
  if (appState.userSession?.phone) {
    phone.value = appState.userSession.phone
  }
})

onUnmounted(() => {
  stopCountdown()
})

function goBack() {
  if (!appState.userSession?.phone) {
    clearUserSession()
  }

  uni.reLaunch({
    url: '/pages/auth/login'
  })
}

async function requestCode() {
  phone.value = normalizedPhone.value

  if (!validatePhone()) {
    return
  }

  try {
    await sendLoginSmsCode(phone.value)
    uni.showToast({
      title: '验证码已发送',
      icon: 'success'
    })
    startCountdown()
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '验证码发送失败，请稍后重试',
      icon: 'none'
    })
  }
}

async function confirmBind() {
  phone.value = normalizedPhone.value
  verifyCode.value = normalizedCode.value

  if (!validatePhone()) {
    return
  }

  if (!/^\d{6}$/.test(verifyCode.value)) {
    uni.showToast({
      title: '请输入 6 位验证码',
      icon: 'none'
    })
    return
  }

  if (binding.value) {
    return
  }

  binding.value = true
  try {
    await bindCustomerMobile(phone.value, verifyCode.value)
    updateUserPhoneBinding(phone.value)

    uni.showToast({
      title: '绑定成功',
      icon: 'success'
    })

    setTimeout(() => {
      redirectAfterBinding()
    }, 520)
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '手机号绑定失败，请稍后重试',
      icon: 'none'
    })
  } finally {
    binding.value = false
  }
}

function validatePhone() {
  if (!/^1\d{10}$/.test(phone.value)) {
    uni.showToast({
      title: '请输入正确的手机号',
      icon: 'none'
    })
    return false
  }

  return true
}

function startCountdown() {
  countdown.value = 60
  stopCountdown()
  countdownTimer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) {
      countdown.value = 0
      stopCountdown()
    }
  }, 1000)
}

function stopCountdown() {
  if (!countdownTimer) {
    return
  }

  clearInterval(countdownTimer)
  countdownTimer = null
}

function redirectAfterBinding() {
  if (shouldPromptOrganizationBinding()) {
    uni.reLaunch({
      url: '/pages/enterprise/organization-bind?entry=login'
    })
    return
  }

  uni.reLaunch({
    url: appState.loginIdentity === 'enterprise' ? '/pages/service/customer-service' : '/pages/home'
  })
}
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #F3F8FD;
}

button::after {
  border: 0;
}

.phone-bind-page {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  color: #071322;
  font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
  background:
    radial-gradient(circle at 91% 18%, rgba(183, 220, 255, 0.16) 0, rgba(183, 220, 255, 0) 310rpx),
    radial-gradient(circle at 8% 80%, rgba(207, 232, 255, 0.2) 0, rgba(207, 232, 255, 0) 360rpx),
    linear-gradient(180deg, #F7FAFE 0%, #F5F9FF 46%, #F2F7FC 100%);
}

.phone-bind-page button,
.phone-bind-page input {
  font-family: inherit;
}

.phone-bind-page__background {
  position: absolute;
  z-index: 0;
  top: 0;
  left: 50%;
  width: 100%;
  height: 475rpx;
  transform: translateX(-50%);
  pointer-events: none;
}

.phone-bind-page__scroll {
  position: relative;
  z-index: 1;
  height: 100vh;
}

.phone-bind-page__content {
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--app-safe-area-top) 48rpx calc(env(safe-area-inset-bottom) + 46rpx);
}

.phone-bind-nav {
  display: grid;
  grid-template-columns: 56rpx minmax(0, 1fr) 56rpx;
  align-items: center;
  min-height: var(--app-page-header-height);
}

.phone-bind-nav__back {
  position: relative;
  width: 72rpx;
  height: var(--app-page-header-height);
  margin: 0 0 0 -16rpx;
  padding: 0;
  background: transparent;
}

.phone-bind-nav__chevron {
  position: absolute;
  left: 16rpx;
  top: 14rpx;
  width: 23rpx;
  height: 23rpx;
  border-left: 5rpx solid #0b1117;
  border-bottom: 5rpx solid #0b1117;
  transform: rotate(45deg);
}

.phone-bind-nav__title {
  display: block;
  color: #071322;
  font-size: 35rpx;
  line-height: 42rpx;
  font-weight: 600;
  text-align: center;
  transform: translateX(4rpx) scaleX(1.025);
}

.phone-bind-nav__ghost {
  width: 56rpx;
  height: var(--app-page-header-height);
}

.bind-panel {
  box-sizing: border-box;
  border: 3rpx solid rgba(255, 255, 255, 0.92);
  background: #F5F9FF;
  box-shadow:
    0 10rpx 24rpx rgba(38, 92, 149, 0.035),
    inset 0 2rpx 0 rgba(255, 255, 255, 0.98);
}

.bind-panel__title,
.bind-tip__text {
  display: block;
}

.bind-panel {
  width: calc(100% - 10rpx);
  margin-top: 164rpx;
  padding: 52rpx 40rpx 36rpx 42rpx;
  border-radius: 44rpx;
}

.bind-panel__heading {
  margin-bottom: 31rpx;
  margin-left: 2rpx;
}

.bind-panel__title {
  color: #000000;
  font-size: 33rpx;
  line-height: 40rpx;
  font-weight: 500;
  -webkit-text-stroke: 0.4px #000000;
  transform: translate(-2rpx, -2rpx) scaleX(1.075);
  transform-origin: left center;
}

.bind-panel__mark {
  width: 56rpx;
  height: 7rpx;
  margin-top: 14rpx;
  border-radius: 999rpx;
  background: linear-gradient(90deg, #168BF2 0%, #004FC4 100%);
  transform: translateY(2rpx);
}

.bind-field {
  display: flex;
  align-items: center;
  box-sizing: border-box;
  width: 100%;
  height: 100rpx;
  border: 1.5rpx solid rgba(210, 222, 235, 0.94);
  border-radius: 20rpx;
  background: rgba(253, 248, 246, 0.55);
  box-shadow:
    0 10rpx 25rpx rgba(48, 100, 154, 0.04),
    inset 0 1rpx 10rpx rgba(255, 255, 255, 0.78);
}

.bind-field--code {
  margin-top: 36rpx;
}

.bind-field__icon-wrap {
  display: flex;
  flex: 0 0 90rpx;
  align-items: center;
  justify-content: center;
  height: 100rpx;
}

.bind-field__icon {
  display: block;
}

.bind-field__icon--phone {
  width: 40rpx;
  height: 46rpx;
  transform: translate(1.5rpx, 1rpx);
}

.bind-field__icon--shield {
  width: 40rpx;
  height: 44rpx;
  transform: translate(2rpx, 2rpx) scaleY(1.05);
}

.bind-field__input {
  flex: 1;
  min-width: 0;
  height: 100rpx;
  color: #24272b;
  font-size: 24.5rpx;
  line-height: 100rpx;
  font-weight: 500;
  transform: translate(2rpx, 0) scaleX(0.985);
  transform-origin: left center;
}

.bind-field__placeholder {
  color: #929294;
  font-size: 24.5rpx;
  font-weight: 400;
}

.bind-field__code-button {
  flex: 0 0 160rpx;
  height: 60rpx;
  margin: 0 16rpx 0 12rpx;
  padding: 0;
  border-width: 2rpx;
  border-style: solid;
  border-color:
    rgba(8, 104, 244, 0.11)
    rgba(8, 104, 244, 0.58)
    rgba(8, 104, 244, 0.5)
    rgba(8, 104, 244, 0.68);
  border-radius: 15rpx;
  background: rgba(255, 255, 255, 0.92);
  color: #0868F4;
  font-size: 23rpx;
  line-height: 57rpx;
  font-weight: 600;
  text-indent: 4rpx;
  transform: translateY(2rpx);
}

.bind-field__code-button[disabled] {
  border-color: #C8D9EA;
  color: #8ea4ba;
  background: rgba(244, 248, 252, 0.9);
}

.bind-submit {
  width: calc(100% + 2rpx);
  height: 94rpx;
  margin-top: 44rpx;
  margin-left: -2rpx;
  padding: 0;
  border-radius: 26rpx;
  background: linear-gradient(
    180deg,
    #168BF2 0%,
    #0878EE 30%,
    #0868F4 48%,
    #0868F4 65%,
    #005BD8 82%,
    #004FC4 100%
  );
  color: #ffffff;
  font-size: 32rpx;
  line-height: 94rpx;
  font-weight: 400;
  letter-spacing: 0;
  text-indent: 2rpx;
  box-shadow:
    0 10rpx 18rpx rgba(8, 104, 244, 0.16),
    inset 0 2rpx 0 rgba(255, 255, 255, 0.2);
}

.bind-submit[disabled] {
  opacity: 0.74;
}

.bind-tip {
  display: flex;
  align-items: flex-start;
  margin: 29rpx 34rpx 0;
}

.bind-tip__icon {
  display: block;
  flex: 0 0 34rpx;
  width: 34rpx;
  height: 34rpx;
  margin-top: 0;
  margin-right: 4rpx;
  transform: translate(1.5rpx, 2rpx) scaleY(1.05);
}

.bind-tip__text {
  flex: 1;
  min-width: 0;
  margin-left: 4rpx;
  color: #24272b;
  font-size: 20.4rpx;
  line-height: 29rpx;
  font-weight: 300;
  -webkit-text-stroke: 0.1px currentColor;
  transform: translateY(6rpx) scale(0.99, 0.84);
  transform-origin: left center;
}

.phone-bind-training {
  display: block;
  width: 619.2308rpx;
  height: auto;
  margin: 27rpx auto 0;
}

@media screen and (min-width: 768px) {
  .phone-bind-page__background {
    width: 750px;
    height: 475px;
  }

  .phone-bind-page__content {
    max-width: 750px;
    margin-right: auto;
    margin-left: auto;
  }
}

@media (max-width: 360px) {
  .phone-bind-page__content {
    padding-right: 42rpx;
    padding-left: 42rpx;
  }

  .bind-panel {
    padding-right: 38rpx;
    padding-left: 38rpx;
  }

  .bind-field__icon-wrap {
    flex-basis: 88rpx;
  }

  .bind-field__code-button {
    flex-basis: 150rpx;
    font-size: 22rpx;
  }
}
</style>
