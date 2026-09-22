<template>
  <view class="service-center-page" :class="{ 'service-center-page--enterprise': isEnterprise }" :style="$appSafeAreaStyle">
    <view class="service-center-bg"></view>

    <view class="service-center-header">
      <button class="back-button" @tap="goBack" aria-label="返回">
        <text class="back-icon">‹</text>
      </button>
      <text class="service-center-title">客服中心</text>
    </view>

    <view v-if="isEnterprise" class="enterprise-message-list">
      <view
        v-if="!enterpriseLoading && enterpriseLoadError && !enterpriseConversations.length"
        class="enterprise-state enterprise-state--error"
        @tap="retryEnterpriseStudents"
      >
        <text>{{ enterpriseLoadError }}</text>
      </view>

      <view v-else-if="!enterpriseLoading && !enterpriseConversations.length" class="enterprise-state">
        <text>暂无绑定学员</text>
      </view>

      <template v-else-if="!enterpriseLoading">
        <view
          v-for="item in enterpriseConversations"
          :key="`${item.studentId}-${item.conversationId || 'new'}`"
          class="enterprise-message-card"
          @tap="openEnterpriseConversation(item)"
        >
          <view class="enterprise-avatar enterprise-avatar--student">
            <view class="teacher-portrait">
              <view class="teacher-portrait__hair"></view>
              <view class="teacher-portrait__face"></view>
              <view class="teacher-portrait__shirt"></view>
            </view>
          </view>
          <view class="enterprise-message-main">
            <text class="enterprise-message-title">{{ item.studentName }}</text>
            <text class="enterprise-message-preview">{{ item.lastMessageContent }}</text>
          </view>
          <view class="enterprise-message-meta">
            <text class="enterprise-message-time">{{ formatDisplayTime(item.lastMessageTime) }}</text>
            <text v-if="item.unreadCount" class="enterprise-unread">{{ item.unreadCount }}</text>
          </view>
          <text class="enterprise-chevron">›</text>
        </view>

        <view v-if="enterpriseLoadError" class="enterprise-page-error" @tap="retryEnterpriseStudents">
          <text>{{ enterpriseLoadError }}</text>
        </view>

        <view class="enterprise-pagination" aria-label="学员列表分页">
          <button
            class="enterprise-page-button"
            :disabled="!canGoPreviousEnterprisePage"
            aria-label="上一页"
            @tap="goToPreviousEnterprisePage"
          >
            上一页
          </button>
          <text class="enterprise-page-status">第 {{ enterprisePageNo }} 页</text>
          <button
            class="enterprise-page-button"
            :disabled="!canGoNextEnterprisePage"
            aria-label="下一页"
            @tap="goToNextEnterprisePage"
          >
            下一页
          </button>
        </view>
      </template>
    </view>

    <view v-else class="service-center-content">
      <view class="conversation-card" @tap="openChat">
        <view class="service-avatar">
          <image class="service-avatar__image" src="/static/settings/setting-contact.png" mode="aspectFit" />
          <view class="online-dot"></view>
        </view>
        <view class="conversation-main">
          <view class="conversation-row">
            <text class="conversation-title">小技客服</text>
            <text class="conversation-time">{{ latestTime }}</text>
          </view>
          <view class="conversation-row conversation-row--bottom">
            <text class="conversation-preview">{{ latestPreview }}</text>
            <text v-if="unreadCount" class="unread-count">{{ unreadCount }}</text>
          </view>
        </view>
      </view>
      <view v-if="loadError" class="service-load-error" @tap="loadCustomerSession">
        <text>{{ loadError }}</text>
      </view>
    </view>
    <HomeProfileTabBar :active="isEnterprise ? 'center' : 'home'" />
    <SelfTestLoadingOverlay
      :show="enterpriseLoading"
      title="学员列表加载中"
      message="正在同步学员会话列表，请稍候。"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import HomeProfileTabBar from '@/components/HomeProfileTabBar.vue'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import { appState, requireLogin } from '@/stores/appState'
import {
  fetchCustomerServiceSession,
  fetchEnterpriseStudentConversations,
  type CustomerServiceSession,
  type EnterpriseStudentConversation
} from '@/services/customerService'

const ENTERPRISE_PAGE_SIZE = 50

const customerSession = ref<CustomerServiceSession | null>(null)
const loadError = ref('')
const enterpriseConversations = ref<EnterpriseStudentConversation[]>([])
const enterpriseLoading = ref(false)
const enterpriseLoadError = ref('')
const enterprisePageNo = ref(1)
const enterpriseRetryPageNo = ref(1)
const enterpriseHasNextPage = ref(false)

const latestPreview = computed(() => customerSession.value?.lastMessageContent || '您好，欢迎咨询小技')
const latestTime = computed(() => formatDisplayTime(customerSession.value?.lastMessageTime))
const unreadCount = computed(() => customerSession.value?.unreadCount || 0)
const isEnterprise = computed(() => appState.loginIdentity === 'enterprise')
const enterpriseTenantId = computed(() => Number(appState.userSession?.tenantId || 0))
const canViewEnterpriseServiceData = computed(() =>
  appState.userSession?.hasWtPost === true && [0, 1].includes(enterpriseTenantId.value)
)
const canGoPreviousEnterprisePage = computed(() => enterprisePageNo.value > 1 && !enterpriseLoading.value)
const canGoNextEnterprisePage = computed(() => enterpriseHasNextPage.value && !enterpriseLoading.value)

onShow(() => {
  if (requireLogin()) {
    if (isEnterprise.value) {
      loadEnterpriseStudents(1)
    } else {
      loadCustomerSession()
    }
  }
})

async function loadCustomerSession() {
  loadError.value = ''
  try {
    customerSession.value = await fetchCustomerServiceSession()
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '客服会话加载失败，点击重试'
  }
}

async function loadEnterpriseStudents(targetPageNo: number) {
  if (enterpriseLoading.value || targetPageNo < 1) {
    return
  }

  if (!canViewEnterpriseServiceData.value) {
    resetEnterpriseConversations()
    return
  }

  enterpriseLoadError.value = ''
  enterpriseRetryPageNo.value = targetPageNo
  enterpriseLoading.value = true
  try {
    const conversations = await fetchEnterpriseStudentConversations(targetPageNo, ENTERPRISE_PAGE_SIZE)
    if (!conversations.length && targetPageNo > enterprisePageNo.value) {
      enterpriseHasNextPage.value = false
      return
    }
    enterpriseConversations.value = conversations
    enterprisePageNo.value = targetPageNo
    enterpriseHasNextPage.value = conversations.length === ENTERPRISE_PAGE_SIZE
  } catch (error) {
    enterpriseLoadError.value = error instanceof Error ? error.message : '学员列表加载失败，点击重试'
  } finally {
    enterpriseLoading.value = false
  }
}

function resetEnterpriseConversations() {
  enterpriseConversations.value = []
  enterpriseLoadError.value = ''
  enterprisePageNo.value = 1
  enterpriseRetryPageNo.value = 1
  enterpriseHasNextPage.value = false
}

function retryEnterpriseStudents() {
  loadEnterpriseStudents(enterpriseRetryPageNo.value)
}

function goToPreviousEnterprisePage() {
  if (!canGoPreviousEnterprisePage.value) return
  loadEnterpriseStudents(enterprisePageNo.value - 1)
}

function goToNextEnterprisePage() {
  if (!canGoNextEnterprisePage.value) return
  loadEnterpriseStudents(enterprisePageNo.value + 1)
}

function openChat() {
  uni.navigateTo({ url: '/pages/service/customer-service-chat?conversationId=default' })
}

function openEnterpriseConversation(item: EnterpriseStudentConversation) {
  const query = [
    `studentId=${encodeURIComponent(`${item.studentId}`)}`,
    `studentName=${encodeURIComponent(item.studentName)}`
  ]
  if (item.conversationId) {
    query.unshift(`conversationId=${encodeURIComponent(item.conversationId)}`)
  }
  uni.navigateTo({ url: `/pages/service/customer-service-chat?${query.join('&')}` })
}

function goBack() {
  const pages = getCurrentPages()
  if (pages.length > 1) {
    uni.navigateBack()
    return
  }
  uni.reLaunch({ url: '/pages/profile' })
}

function formatDisplayTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const hour = `${date.getHours()}`.padStart(2, '0')
  const minute = `${date.getMinutes()}`.padStart(2, '0')
  return `${hour}:${minute}`
}
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #eef7ff;
}

button::after {
  border: 0;
}

.service-center-page {
  min-height: 100vh;
  color: #071b3c;
  background:
    linear-gradient(180deg, rgba(238, 248, 255, 0.18) 0%, rgba(247, 251, 255, 0.92) 68%, #f4f9ff 100%),
    url('@/static/backgrounds/focus-atmosphere.png') center top / cover no-repeat;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.service-center-page--enterprise {
  background:
    linear-gradient(180deg, rgba(239, 248, 255, 0.16) 0%, rgba(247, 251, 255, 0.94) 70%, #f5fbff 100%),
    url('@/static/backgrounds/focus-atmosphere.png') center top / cover no-repeat;
}

.service-center-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.28) 0%, rgba(246, 251, 255, 0.86) 100%);
}

.service-center-header {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 76rpx minmax(0, 1fr) 76rpx;
  align-items: center;
  min-height: calc(var(--app-safe-area-top) + var(--app-page-header-height));
  padding: var(--app-safe-area-top) 28rpx 0;
}

.service-center-page--enterprise .service-center-header {
  min-height: calc(var(--app-safe-area-top) + var(--app-page-header-height));
  padding: var(--app-safe-area-top) 32rpx 0;
  border-bottom: 1rpx solid rgba(42, 119, 234, 0.24);
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.9) 0%, rgba(235, 248, 255, 0.78) 56%, rgba(211, 236, 252, 0.72) 100%);
}

.back-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.62);
  color: #071b3c;
}

.service-center-page--enterprise .back-button {
  background: transparent;
  color: #0b63e5;
}

.back-icon {
  display: block;
  margin-top: -6rpx;
  font-size: 66rpx;
  line-height: 1;
  font-weight: 300;
}

.service-center-title {
  display: block;
  overflow: hidden;
  color: #061936;
  font-size: 34rpx;
  line-height: 1.15;
  font-weight: 900;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.service-center-page--enterprise .service-center-title {
  color: #075ee0;
  font-size: 38rpx;
  letter-spacing: 0;
}

.enterprise-message-list {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  padding: 116rpx 28rpx calc(env(safe-area-inset-bottom) + 124rpx);
}

.enterprise-message-card {
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 122rpx minmax(0, 1fr) 130rpx 34rpx;
  column-gap: 22rpx;
  align-items: center;
  min-height: 142rpx;
  margin-bottom: 24rpx;
  padding: 28rpx 26rpx;
  border: 1rpx solid rgba(223, 237, 251, 0.88);
  border-radius: 18rpx;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 16rpx 42rpx rgba(43, 98, 152, 0.1);
}

.enterprise-state {
  box-sizing: border-box;
  margin-top: 24rpx;
  padding: 34rpx 28rpx;
  border: 1rpx solid rgba(223, 237, 251, 0.88);
  border-radius: 18rpx;
  background: rgba(255, 255, 255, 0.94);
  color: #6d7f99;
  font-size: 26rpx;
  line-height: 1.45;
  font-weight: 680;
  text-align: center;
  box-shadow: 0 16rpx 42rpx rgba(43, 98, 152, 0.08);
}

.enterprise-state--error {
  color: #d64545;
}

.enterprise-page-error {
  box-sizing: border-box;
  min-height: 52rpx;
  margin: 4rpx 0 18rpx;
  color: #d64545;
  font-size: 22rpx;
  line-height: 1.45;
  font-weight: 600;
  text-align: center;
}

.enterprise-pagination {
  box-sizing: border-box;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 132rpx minmax(0, 1fr);
  gap: 16rpx;
  align-items: center;
  min-height: 72rpx;
  margin-top: 8rpx;
}

.enterprise-page-button {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 72rpx;
  margin: 0;
  padding: 0 18rpx;
  border: 1rpx solid rgba(10, 102, 226, 0.24);
  border-radius: 12rpx;
  background: rgba(255, 255, 255, 0.94);
  color: #075ee0;
  font-size: 25rpx;
  line-height: 1;
  font-weight: 720;
}

.enterprise-page-button[disabled] {
  border-color: rgba(125, 143, 168, 0.18);
  background: rgba(245, 249, 252, 0.9);
  color: #9aa8ba;
  opacity: 1;
}

.enterprise-page-status {
  display: block;
  overflow: hidden;
  color: #5f718b;
  font-size: 23rpx;
  line-height: 1.2;
  font-weight: 650;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.enterprise-avatar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96rpx;
  height: 96rpx;
  overflow: hidden;
  border-radius: 50%;
  background: linear-gradient(145deg, #e8f5ff 0%, #f7fbff 100%);
}

.enterprise-avatar__icon {
  display: block;
  width: 62rpx;
  height: 62rpx;
}

.enterprise-avatar--service,
.enterprise-avatar--system {
  background: linear-gradient(145deg, #78c2ff 0%, #126af2 100%);
  box-shadow: 0 10rpx 24rpx rgba(15, 105, 235, 0.22);
}

.enterprise-avatar--service .enterprise-avatar__icon,
.enterprise-avatar--system .enterprise-avatar__icon {
  width: 70rpx;
  height: 70rpx;
  filter: brightness(0) invert(1);
}

.teacher-portrait {
  position: relative;
  width: 96rpx;
  height: 96rpx;
  overflow: hidden;
  border-radius: 50%;
  background: linear-gradient(180deg, #d9ebfa 0%, #f7fbff 100%);
}

.teacher-portrait__face {
  position: absolute;
  top: 22rpx;
  left: 31rpx;
  width: 34rpx;
  height: 42rpx;
  border-radius: 46% 46% 48% 48%;
  background: #D8EAFF;
  box-shadow: inset 0 -3rpx 0 rgba(89, 169, 255, 0.2);
}

.teacher-portrait__hair {
  position: absolute;
  top: 15rpx;
  left: 25rpx;
  z-index: 1;
  width: 46rpx;
  height: 30rpx;
  border-radius: 48% 48% 35% 35%;
  background: #1b2538;
}

.teacher-portrait__shirt {
  position: absolute;
  right: 17rpx;
  bottom: -10rpx;
  left: 17rpx;
  height: 46rpx;
  border-radius: 22rpx 22rpx 0 0;
  background: #9ed0fb;
}

.enterprise-avatar--female .teacher-portrait__hair {
  top: 13rpx;
  left: 22rpx;
  width: 52rpx;
  height: 40rpx;
  border-radius: 50% 50% 42% 42%;
  background: #172033;
}

.enterprise-avatar--female .teacher-portrait__shirt {
  background: #a8d8ff;
}

.enterprise-avatar--glasses .teacher-portrait__hair {
  background: #252b34;
}

.enterprise-avatar--glasses .teacher-portrait::before,
.enterprise-avatar--glasses .teacher-portrait::after {
  position: absolute;
  top: 38rpx;
  z-index: 2;
  width: 14rpx;
  height: 10rpx;
  content: "";
  border: 2rpx solid #263348;
  border-radius: 50%;
}

.enterprise-avatar--glasses .teacher-portrait::before {
  left: 29rpx;
}

.enterprise-avatar--glasses .teacher-portrait::after {
  right: 29rpx;
}

.enterprise-message-main {
  min-width: 0;
}

.enterprise-message-title,
.enterprise-message-preview,
.enterprise-message-time,
.enterprise-unread,
.enterprise-chevron {
  display: block;
}

.enterprise-message-title {
  overflow: hidden;
  color: #071b3c;
  font-size: 31rpx;
  line-height: 1.2;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.enterprise-message-preview {
  margin-top: 20rpx;
  overflow: hidden;
  color: #7b8ca4;
  font-size: 23rpx;
  line-height: 1.24;
  font-weight: 540;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.enterprise-message-meta {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 0;
}

.enterprise-message-time {
  color: #7d8fa8;
  font-size: 24rpx;
  line-height: 1.2;
  font-weight: 540;
  white-space: nowrap;
}

.enterprise-unread {
  min-width: 38rpx;
  height: 38rpx;
  margin-top: 16rpx;
  padding: 0 8rpx;
  border-radius: 999rpx;
  background: linear-gradient(180deg, #0d75ff 0%, #045ddd 100%);
  color: #ffffff;
  font-size: 22rpx;
  line-height: 38rpx;
  font-weight: 760;
  text-align: center;
  box-shadow: 0 8rpx 18rpx rgba(0, 96, 226, 0.2);
}

.enterprise-chevron {
  color: #9ba7b6;
  font-size: 56rpx;
  line-height: 1;
  font-weight: 260;
  text-align: right;
}

.service-center-content {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  padding: 20rpx 28rpx calc(env(safe-area-inset-bottom) + 124rpx);
}

.conversation-card {
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 96rpx minmax(0, 1fr);
  column-gap: 22rpx;
  align-items: center;
  min-height: 134rpx;
  padding: 22rpx 24rpx;
  border: 1rpx solid rgba(199, 222, 246, 0.82);
  border-radius: 18rpx;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 18rpx 50rpx rgba(50, 105, 160, 0.12);
}

.service-avatar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 88rpx;
  height: 88rpx;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 10rpx 28rpx rgba(33, 104, 178, 0.12);
}

.service-avatar__image {
  width: 56rpx;
  height: 56rpx;
}

.online-dot {
  position: absolute;
  right: 7rpx;
  bottom: 8rpx;
  width: 18rpx;
  height: 18rpx;
  border: 4rpx solid #ffffff;
  border-radius: 50%;
  background: #17c46e;
}

.conversation-main {
  min-width: 0;
}

.conversation-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18rpx;
  min-width: 0;
}

.conversation-row--bottom {
  margin-top: 18rpx;
}

.conversation-title,
.conversation-preview,
.conversation-time,
.unread-count {
  display: block;
}

.conversation-title {
  overflow: hidden;
  color: #071b3c;
  font-size: 28rpx;
  line-height: 1.18;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-time {
  flex: 0 0 auto;
  color: #8092ac;
  font-size: 20rpx;
  line-height: 1.2;
  font-weight: 560;
}

.conversation-preview {
  min-width: 0;
  overflow: hidden;
  color: #6a7d99;
  font-size: 23rpx;
  line-height: 1.2;
  font-weight: 540;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.unread-count {
  flex: 0 0 auto;
  min-width: 32rpx;
  height: 32rpx;
  padding: 0 8rpx;
  border-radius: 999rpx;
  background: #f0524e;
  color: #ffffff;
  font-size: 18rpx;
  line-height: 32rpx;
  font-weight: 780;
  text-align: center;
}

.service-load-error {
  margin-top: 18rpx;
  color: #d64545;
  font-size: 23rpx;
  line-height: 1.4;
  font-weight: 560;
}
</style>
