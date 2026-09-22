<template>
  <view class="enterprise-review-page" :style="$appSafeAreaStyle">
    <view class="review-sky" />

    <view class="enterprise-review-page__content">
      <view class="review-header">
        <button
          v-if="currentStatus === 'approved'"
          class="review-back"
          aria-label="返回首页"
          @tap="goHome"
        >
          <text class="review-back__icon">‹</text>
        </button>
        <text class="review-header__title">审核进度</text>
      </view>

      <view class="review-status-card">
        <view class="review-status-badge" :class="`review-status-badge--${statusTone}`">
          <text class="review-status-badge__text">{{ statusLabel }}</text>
        </view>
      </view>

      <view class="review-progress-card">
        <view
          class="review-steps"
          :class="{ 'review-steps--reviewing': currentStatus === 'reviewing' }"
        >
          <view v-for="(step, index) in steps" :key="step.key" class="review-step">
            <view
              v-if="index > 0"
              class="review-step__track"
              :class="{ 'review-step__track--active': index <= activeStepIndex }"
            />
            <view
              class="review-step__circle"
              :class="{
                'review-step__circle--active': index === activeStepIndex,
                'review-step__circle--done': index < activeStepIndex,
                'review-step__circle--approved': currentStatus === 'approved' && index === activeStepIndex,
                'review-step__circle--rejected': currentStatus === 'rejected' && index === activeStepIndex
              }"
            >
              <view
                v-if="index < activeStepIndex || (currentStatus === 'approved' && index === activeStepIndex)"
                class="review-step__check"
              />
              <view
                v-else-if="currentStatus === 'rejected' && index === activeStepIndex"
                class="review-step__cross"
              />
            </view>
            <text
              class="review-step__label"
              :class="{
                'review-step__label--active': index === activeStepIndex,
                'review-step__label--done': index < activeStepIndex
              }"
            >
              {{ step.label }}
            </text>
          </view>
        </view>

        <view
          class="review-result"
          :class="[`review-result--${statusTone}`, `review-result--state-${currentStatus}`]"
        >
          <view class="review-result__content">
            <text class="review-result__title">{{ resultTitle }}</text>
            <text class="review-result__message">{{ resultMessage }}</text>
          </view>
        </view>

        <button
          v-if="currentStatus === 'rejected'"
          class="review-submit"
          @tap="resubmit"
        >
          重新提交
        </button>
        <button
          v-else-if="currentStatus === 'approved'"
          class="review-submit"
          @tap="enterHome"
        >
          进入平台
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { fetchCurrentCompany } from '@/services/customerAuth'
import {
  appState,
  setEnterpriseReviewStatus,
  updateUserAuditStatus,
  type EnterpriseReviewStatus
} from '@/stores/appState'

const statusFromQuery = ref<EnterpriseReviewStatus | ''>('')

const steps = [
  { key: 'submit', label: '提交资料' },
  { key: 'review', label: '审核中' },
  { key: 'result', label: '审核结果' }
]

onLoad((options) => {
  const status = typeof options?.status === 'string' ? options.status : ''
  if (isEnterpriseReviewStatus(status)) {
    statusFromQuery.value = status
  } else if (!appState.enterpriseRegistration) {
    setEnterpriseReviewStatus('rejected')
  }
})

onShow(() => {
  void refreshEnterpriseReviewStatus()
})

const currentStatus = computed<EnterpriseReviewStatus>(() => {
  const sessionStatus = mapAuditStatus(appState.userSession?.auditStatus)
  if (sessionStatus) {
    return sessionStatus
  }
  if (statusFromQuery.value && statusFromQuery.value !== 'approved') {
    return statusFromQuery.value
  }
  return appState.enterpriseRegistration?.status || 'rejected'
})

const activeStepIndex = computed(() => {
  if (currentStatus.value === 'pending') {
    return 0
  }
  if (currentStatus.value === 'reviewing') {
    return 1
  }
  return 2
})

const statusTone = computed(() => {
  if (currentStatus.value === 'approved') {
    return 'approved'
  }
  if (currentStatus.value === 'rejected') {
    return 'rejected'
  }
  return 'reviewing'
})

const statusLabel = computed(() => {
  const labels: Record<EnterpriseReviewStatus, string> = {
    pending: '待审核',
    reviewing: '审核中',
    approved: '已通过',
    rejected: '已驳回'
  }
  return labels[currentStatus.value]
})

const resultTitle = computed(() => {
  const titles: Record<EnterpriseReviewStatus, string> = {
    pending: '资料已提交',
    reviewing: '审核进行中',
    approved: '审核已通过',
    rejected: '驳回原因'
  }
  return titles[currentStatus.value]
})

const resultMessage = computed(() => {
  if (currentStatus.value === 'rejected') {
    return appState.enterpriseRegistration?.rejectReason || '提交的资料不符合要求，请补充完整后重新提交。'
  }
  if (currentStatus.value === 'approved') {
    return '企业资质审核已通过，可使用企业账号进入平台。'
  }
  if (currentStatus.value === 'pending') {
    return '资料已进入审核队列，请等待平台工作人员处理。'
  }
  return '平台正在核验企业基础信息与营业执照等资质材料。'
})

function isEnterpriseReviewStatus(value: string): value is EnterpriseReviewStatus {
  return value === 'pending' || value === 'reviewing' || value === 'approved' || value === 'rejected'
}

const resubmit = () => {
  uni.redirectTo({
    url: '/pages/enterprise/register'
  })
}

const goHome = () => {
  uni.reLaunch({
    url: '/pages/enterprise/students',
    fail: () => {}
  })
}

const enterHome = () => {
  uni.reLaunch({
    url: '/pages/enterprise/students',
    fail: () => {}
  })
}

async function refreshEnterpriseReviewStatus() {
  if (appState.loginIdentity !== 'enterprise') {
    return
  }

  try {
    const company = await fetchCurrentCompany()
    const status = mapAuditStatus(company.auditStatus)
    updateUserAuditStatus(company.auditStatus)
    if (status) {
      setEnterpriseReviewStatus(status)
    }
  } catch (error) {
    console.warn('refresh enterprise review status failed', error)
  }
}

function mapAuditStatus(auditStatus?: number): EnterpriseReviewStatus | '' {
  const status = Number(auditStatus ?? 0)
  if (status === 1) {
    return 'reviewing'
  }
  if (status === 2) {
    return 'approved'
  }
  if (status === 3) {
    return 'rejected'
  }
  return ''
}
</script>

<style lang="scss">
/* Enterprise audit reference layout. Business state and actions remain unchanged. */
page {
  min-height: 100%;
  background: #F8FBFF;
}

button::after {
  border: 0;
}

.enterprise-review-page {
  position: relative;
  min-height: calc(max(100vh, 1649rpx) + var(--app-safe-area-top-extra));
  overflow: hidden;
  background: #F8FBFF;
  color: #0a315d;
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
  letter-spacing: 0;
}

.enterprise-review-page::before,
.enterprise-review-page::after {
  content: none;
}

.review-sky {
  position: absolute;
  z-index: 0;
  left: 50%;
  top: calc(879rpx + var(--app-safe-area-top-extra));
  width: 750rpx;
  height: 770rpx;
  background: url('../../static/enterprise-review/review-reference-line-art.png') center / 100% 100% no-repeat;
  transform: translateX(-50%);
  pointer-events: none;
}

.enterprise-review-page__content {
  position: relative;
  top: var(--app-safe-area-top-extra);
  z-index: 1;
  box-sizing: border-box;
  width: 750rpx;
  min-height: 1649rpx;
  margin: 0 auto;
  padding: 0;
}

.review-header {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  left: 0;
  top: 45rpx;
  width: 750rpx;
  height: 58rpx;
  margin: 0;
}

.review-header::before {
  content: none;
}

.review-header::after {
  content: none;
}

.review-header__title {
  display: block;
  color: #0a315d;
  font-size: 40rpx;
  line-height: 58rpx;
  font-weight: 700;
  letter-spacing: 0;
  text-align: center;
  transform: none;
}

.review-back {
  position: absolute;
  left: 37rpx;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 58rpx;
  height: 58rpx;
  margin: 0;
  padding: 0;
  border-radius: 50%;
  background: transparent;
  color: #0a315d;
}

.review-back__icon {
  display: block;
  margin-top: -6rpx;
  font-size: 66rpx;
  line-height: 1;
  font-weight: 300;
}

.review-status-card {
  position: absolute;
  box-sizing: border-box;
  left: 72rpx;
  top: 198rpx;
  width: 610rpx;
  height: 102rpx;
  overflow: visible;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.review-status-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  width: 88rpx;
  height: 105rpx;
  background: url('../../static/enterprise-review/review-reference-status-icon.png') center / 100% 100% no-repeat;
}

.review-status-card::after {
  content: '';
  position: absolute;
  left: 116rpx;
  top: 10rpx;
  width: 2rpx;
  height: 85rpx;
  background: #E1EAF3;
}

.review-status-badge {
  position: absolute;
  left: 154rpx;
  top: 0;
  display: block;
  width: 310rpx;
  height: 104rpx;
  box-sizing: border-box;
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: #0a315d;
  box-shadow: none;
}

.review-status-badge::before {
  content: '当前状态';
  position: absolute;
  left: 0;
  top: 0;
  color: #0a315d;
  font-size: 27rpx;
  line-height: 38rpx;
  font-weight: 400;
}

.review-status-badge__text,
.review-status-badge--reviewing .review-status-badge__text {
  position: absolute;
  display: block;
  left: 0;
  top: 44rpx;
  color: #0a315d;
  font-size: 40rpx;
  line-height: 52rpx;
  font-weight: 700;
  letter-spacing: 0;
  white-space: nowrap;
  transform: none;
}

.review-progress-card {
  position: absolute;
  left: 0;
  top: 397rpx;
  width: 750rpx;
  margin: 0;
}

.review-steps {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, 250rpx);
  align-items: start;
  box-sizing: border-box;
  width: 750rpx;
  height: 151rpx;
  padding: 0;
  overflow: visible;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.review-step__track {
  position: absolute;
  z-index: 0;
  left: -50%;
  top: 33rpx;
  width: 100%;
  height: 4rpx;
  background: #d9d9d8;
}

.review-step__track--active {
  background: #0868F4;
}

.review-step__circle,
.review-steps--reviewing .review-step__circle {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 70rpx;
  height: 70rpx;
  border: 3rpx solid #d8d7d6;
  border-radius: 50%;
  background: #F8FBFF;
  color: #9b9a98;
  opacity: 1;
  box-shadow: none;
}

.review-steps--reviewing .review-step__track {
  opacity: 1;
}

.review-step {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 0;
}

.review-step__circle--active,
.review-steps--reviewing .review-step__circle--active {
  border-color: #0868F4;
  background: #0868F4;
  color: #ffffff;
  box-shadow: none;
}

.review-step__circle--done,
.review-steps--reviewing .review-step__circle--done {
  border: 4rpx solid #0868F4;
  background: #0868F4;
  color: #ffffff;
  box-shadow: inset 0 0 0 6rpx #F8FBFF;
}

.review-step__circle--approved {
  border-color: #0868F4;
  background: #0868F4;
}

.review-step__circle--rejected {
  border-color: #df5543;
  background: #df5543;
}

.review-step:nth-of-type(1) .review-step__circle:not(.review-step__circle--done)::after {
  content: '1';
}

.review-step:nth-of-type(2) .review-step__circle:not(.review-step__circle--done)::after {
  content: '2';
}

.review-step:nth-of-type(3) .review-step__circle:not(.review-step__circle--done):not(.review-step__circle--approved):not(.review-step__circle--rejected)::after {
  content: '3';
}

.review-step__circle::after {
  font-size: 35rpx;
  line-height: 1;
  font-weight: 500;
}

.review-step__check {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  width: 26rpx;
  height: 15rpx;
  margin-top: -5rpx;
  border-left-style: solid;
  border-left-color: currentColor;
  border-left-width: 5rpx;
  border-bottom-style: solid;
  border-bottom-color: currentColor;
  border-bottom-width: 5rpx;
  border-radius: 2rpx;
  transform: rotate(-45deg);
}

.review-step__cross::before,
.review-step__cross::after {
  content: '';
  position: absolute;
  left: 31rpx;
  top: 18rpx;
  width: 6rpx;
  height: 32rpx;
  border-radius: 999rpx;
  background: currentColor;
}

.review-step__cross::before {
  transform: rotate(45deg);
}

.review-step__cross::after {
  transform: rotate(-45deg);
}

.review-step__label,
.review-steps--reviewing .review-step__label {
  display: block;
  margin-top: 23rpx;
  color: #0a315d;
  font-size: 28rpx;
  line-height: 39rpx;
  font-weight: 500;
  letter-spacing: 0;
  text-align: center;
  white-space: nowrap;
  transform: none;
}

.review-step__label--active,
.review-step__label--done,
.review-steps--reviewing .review-step__label--active,
.review-steps--reviewing .review-step__label--done {
  color: #0a315d;
  font-weight: 500;
}

.review-result {
  display: block;
  box-sizing: border-box;
  width: 750rpx;
  min-height: 160rpx;
  margin-top: 46rpx;
  padding: 0 68rpx;
  overflow: visible;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.review-result__content {
  position: relative;
  z-index: 1;
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  margin: 0;
}

.review-result__title,
.review-result--state-reviewing .review-result__title {
  display: block;
  box-sizing: border-box;
  width: 100%;
  padding-left: 18rpx;
  border-left: 10rpx solid #0868F4;
  color: #0a315d;
  font-size: 34rpx;
  line-height: 44rpx;
  font-weight: 600;
  text-align: left;
  transform: none;
}

.review-result__message,
.review-result--state-reviewing .review-result__message {
  display: block;
  max-width: 614rpx;
  margin-top: 25rpx;
  color: #0a315d;
  font-size: 26rpx;
  line-height: 40rpx;
  font-weight: 400;
  text-align: left;
  overflow-wrap: anywhere;
  transform: none;
}

.review-submit {
  display: block;
  box-sizing: border-box;
  width: 614rpx;
  height: 82rpx;
  margin: 42rpx auto 0;
  padding: 0;
  border-radius: 12rpx;
  background: #0868F4;
  color: #ffffff;
  font-size: 28rpx;
  line-height: 82rpx;
  font-weight: 700;
  letter-spacing: 0;
  text-align: center;
  box-shadow: 0 10rpx 20rpx rgba(22, 126, 232, 0.18);
}

.review-result--approved + .review-submit {
  background: #68b949;
  box-shadow: 0 10rpx 20rpx rgba(80, 155, 51, 0.16);
}

</style>
