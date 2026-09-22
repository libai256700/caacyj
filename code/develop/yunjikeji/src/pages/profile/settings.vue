<template>
  <view class="profile-info-page" :style="$appSafeAreaStyle">
    <view class="profile-info-page__background" />
    <image
      class="profile-info-page__contour profile-info-page__contour--top"
      src="/static/profile-settings/settings-contours-top.svg"
      mode="scaleToFill"
    />
    <image
      class="profile-info-page__contour profile-info-page__contour--bottom"
      src="/static/profile-settings/settings-contours-bottom.svg"
      mode="scaleToFill"
    />
    <button class="profile-info-page__back" aria-label="返回" @tap="goBack">
      <view class="profile-info-page__back-icon" />
    </button>
    <text class="profile-info-page__title">设置</text>

    <scroll-view class="profile-info-page__scroll" scroll-y>
      <view class="profile-info-page__content">
        <view class="profile-card">
          <view class="profile-card__body">
            <text class="profile-card__name">账号</text>
            <text class="profile-card__phone">{{ maskedPhone }}</text>
          </view>
          <view class="profile-card__arrow" />
        </view>

        <view class="profile-menu">
          <view v-for="item in settingsMenuRows" :key="item.key" class="profile-menu__row" @tap="handleMenu(item)">
            <image class="profile-menu__icon" :src="item.icon" mode="aspectFit" />
            <text class="profile-menu__label">{{ item.label }}</text>
            <view class="profile-menu__arrow" />
          </view>
        </view>

        <button class="profile-info-page__logout" @tap="handleMenu(logoutMenuRow)">
          {{ logoutMenuRow.label }}
        </button>
      </view>
    </scroll-view>
    <ProfileLogoutDialog
      :visible="logoutDialogVisible"
      @close="closeLogoutDialog"
      @confirm="confirmLogoutAndRedirect"
    />
    <HomeProfileTabBar active="profile" />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import HomeProfileTabBar from '@/components/HomeProfileTabBar.vue'
import ProfileLogoutDialog from '@/components/ProfileLogoutDialog.vue'
import { appState, clearUserSession, requireLogin } from '@/stores/appState'
import { fetchCurrentStudentAudit, logoutCompany, logoutCustomer, type StudentAuditStatus } from '@/services/customerAuth'

type MenuKey = 'security' | 'cancel' | 'service' | 'privacy' | 'about' | 'logout'

type MenuRow = {
  key: MenuKey
  label: string
  icon: string
  danger?: boolean
}

const PROFILE_STORAGE_KEY = 'yunjikeji-profile-page-standard'
const currentStudentAudit = ref<StudentAuditStatus | null>(null)
const logoutDialogVisible = ref(false)

const studentAuditStatus = computed(() => resolveStudentAuditStatus(currentStudentAudit.value))

const menuRows: MenuRow[] = [
  { key: 'security', label: '账号安全', icon: '/static/profile-settings/settings-security.svg' },
  { key: 'cancel', label: '注销账号', icon: '/static/profile-settings/settings-cancel-account.svg' },
  { key: 'service', label: '联系客服', icon: '/static/profile-settings/settings-service.svg' },
  { key: 'privacy', label: '隐私协议', icon: '/static/profile-settings/settings-privacy.svg' },
  { key: 'about', label: '关于我们', icon: '/static/profile-settings/settings-about.svg' },
  { key: 'logout', label: '退出登录', icon: '/static/profile-settings/logout.svg', danger: true }
]

const settingsMenuRows = menuRows.filter((item) => !item.danger)
const logoutMenuRow = menuRows.find((item) => item.danger) as MenuRow

const profileInfo = computed(() => {
  const stored = uni.getStorageSync(PROFILE_STORAGE_KEY)
  const source = stored && typeof stored === 'object' ? (stored as Record<string, unknown>) : {}
  const nickname = readString(source, 'nickname', appState.userSession?.name || '企业用户')
  const phone = readString(source, 'phone', appState.userSession?.phone || '13800005678')
  const organizationName =
    studentAuditStatus.value === 'pending' || studentAuditStatus.value === 'rejected'
      ? '审核进度'
      : normalizeOrganizationName(appState.organizationBinding.organizationName || readString(source, 'schoolName', '未绑定组织'))

  return {
    nickname,
    phone,
    organizationName
  }
})

const maskedPhone = computed(() => maskPhone(profileInfo.value.phone))

onShow(() => {
  if (!requireLogin()) {
    return
  }
  void loadCurrentStudentAudit()
})

async function loadCurrentStudentAudit() {
  if (appState.loginIdentity === 'enterprise') {
    currentStudentAudit.value = null
    return
  }

  try {
    currentStudentAudit.value = await fetchCurrentStudentAudit()
  } catch (error) {
    currentStudentAudit.value = null
    console.warn('load student audit failed', error)
  }
}

function goBack() {
  const pages = getCurrentPages()
  if (pages.length > 1) {
    uni.navigateBack()
    return
  }

  uni.reLaunch({
    url: '/pages/profile'
  })
}

function readString(source: Record<string, unknown>, key: string, fallback: string) {
  const value = source[key]
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function normalizeOrganizationName(value: string) {
  const normalized = value.trim()
  if (
    !normalized ||
    normalized === '未填写学校' ||
    normalized === '未填写学校名称' ||
    normalized === '审核进度' ||
    normalized === '待审核' ||
    normalized === '审核中' ||
    normalized === '已通过' ||
    normalized === '已驳回'
  ) {
    return '未绑定组织'
  }
  return normalized
}

function resolveStudentAuditStatus(audit: StudentAuditStatus | null) {
  if (!audit) {
    return appState.organizationBinding.status === 'pending' ? 'pending' : null
  }
  if (audit.auditStatus === 1) {
    return 'pending'
  }
  if (audit.auditStatus === 2) {
    return 'approved'
  }
  if (audit.auditStatus === 3) {
    return 'rejected'
  }
  return null
}

function maskPhone(phone: string) {
  const normalized = (phone || '').replace(/\D/g, '')
  if (normalized.length < 11) {
    return '138****5678'
  }
  return `${normalized.slice(0, 3)}****${normalized.slice(-4)}`
}

function handleMenu(item: MenuRow) {
  if (item.key === 'security') {
    uni.navigateTo({ url: '/pages/profile/phone-bind' })
    return
  }

  if (item.key === 'cancel') {
    uni.showModal({
      title: '注销账号',
      content: '账号注销功能暂未开放，如需处理请先联系客服。',
      confirmText: '联系客服',
      success: ({ confirm }) => {
        if (confirm) {
          contactService()
        }
      }
    })
    return
  }

  if (item.key === 'service') {
    contactService()
    return
  }

  if (item.key === 'privacy') {
    uni.navigateTo({ url: '/pages/auth/agreement?type=privacy' })
    return
  }

  if (item.key === 'about') {
    uni.showModal({
      title: '关于我们',
      content: '小技为学员提供无人机教学、培训、练习与考证服务。',
      showCancel: false,
      confirmText: '知道了'
    })
    return
  }

  confirmLogout()
}

function contactService() {
  if (appState.loginIdentity === 'enterprise') {
    uni.reLaunch({ url: '/pages/service/customer-service' })
    return
  }

  uni.navigateTo({ url: '/pages/service/customer-service-chat?conversationId=default' })
}

function confirmLogout() {
  logoutDialogVisible.value = true
}

function closeLogoutDialog() {
  logoutDialogVisible.value = false
}

function confirmLogoutAndRedirect() {
  closeLogoutDialog()
  logoutAndRedirect()
}

async function logoutAndRedirect() {
  try {
    if (appState.loginIdentity === 'enterprise') {
      await logoutCompany()
    } else {
      await logoutCustomer()
    }
  } catch (error) {
    console.warn('logout failed', error)
  }

  clearUserSession()
  uni.reLaunch({
    url: '/pages/auth/login'
  })
}
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #F5F9FF;
}

button::after {
  border: 0;
}

.profile-info-page {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  color: #063c54;
  background: #F5F9FF;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}

.profile-info-page__background {
  position: fixed;
  inset: 0;
  z-index: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  background:
    linear-gradient(rgba(247, 251, 255, 0.78), rgba(247, 251, 255, 0.78)),
    url('@/static/profile-settings/settings-paper-texture.jpg') center top / 320rpx 188rpx repeat;
}

.profile-info-page__contour {
  position: fixed;
  z-index: 1;
  pointer-events: none;
}

.profile-info-page__contour--top {
  top: 0;
  left: 0;
  width: 330rpx;
  height: 260rpx;
}

.profile-info-page__contour--bottom {
  right: 0;
  bottom: 0;
  width: 750rpx;
  height: 500rpx;
}

.profile-info-page__scroll {
  position: relative;
  z-index: 2;
  height: 100vh;
}

.profile-info-page__back {
  position: fixed;
  z-index: 4;
  left: 32rpx;
  top: var(--app-safe-area-top);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 66rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0;
  background: transparent;
}

.profile-info-page__back-icon {
  display: block;
  box-sizing: border-box;
  width: 27rpx;
  height: 27rpx;
  border-bottom: 5rpx solid #003f5b;
  border-left: 5rpx solid #003f5b;
  border-radius: 2rpx;
  transform: rotate(45deg);
}

.profile-info-page__title {
  position: fixed;
  z-index: 4;
  top: var(--app-safe-area-top);
  right: 0;
  left: 0;
  display: block;
  color: #00374f;
  font-size: 44rpx;
  line-height: var(--app-page-header-height);
  font-weight: 500;
  text-align: center;
  transform: translateX(-1rpx);
  -webkit-text-stroke: 0.3px #00374f;
}

.profile-info-page__content {
  position: relative;
  box-sizing: border-box;
  min-height: 100vh;
  padding: calc(var(--app-safe-area-top) + 121rpx) 44rpx calc(env(safe-area-inset-bottom) + 190rpx);
}

.profile-card__name,
.profile-card__phone,
.profile-menu__label {
  display: block;
}

.profile-card,
.profile-menu {
  box-sizing: border-box;
  border: 1rpx solid rgba(255, 255, 255, 0.92);
  border-radius: 28rpx;
  background:
    linear-gradient(rgba(255, 254, 250, 0.76), rgba(255, 254, 250, 0.76)),
    url('@/static/profile-settings/settings-paper-texture.jpg') center / 320rpx 188rpx repeat;
  box-shadow:
    0 12rpx 27rpx rgba(111, 183, 255, 0.08),
    inset 0 1rpx 0 rgba(255, 255, 255, 0.92);
}

.profile-card {
  position: relative;
  display: flex;
  align-items: center;
  height: 185rpx;
  padding: 0 36rpx;
}

.profile-card__body {
  min-width: 0;
  transform: translateY(2rpx);
}

.profile-card__name {
  color: #063c54;
  font-size: 33rpx;
  line-height: 44rpx;
  font-weight: 500;
  transform: translate(1rpx, -2rpx);
  -webkit-text-stroke: 0.25px #063c54;
}

.profile-card__phone {
  margin-top: 16rpx;
  color: #063c54;
  font-size: 37rpx;
  line-height: 44rpx;
  font-weight: 400;
}

.profile-card__arrow,
.profile-menu__arrow {
  box-sizing: border-box;
  width: 15rpx;
  height: 29rpx;
  background: url('@/static/profile-settings/settings-arrow-right.svg') center / 100% 100% no-repeat;
}

.profile-menu__arrow {
  position: absolute;
  top: 50%;
  right: 3rpx;
  transform: translateY(-50%);
}

.profile-card__arrow {
  position: absolute;
  top: calc(50% + 2rpx);
  right: 38rpx;
  transform: translateY(-50%);
}

.profile-menu {
  overflow: hidden;
  height: 650rpx;
  margin-top: 49rpx;
  padding: 0 34rpx;
}

.profile-menu__row {
  position: relative;
  display: grid;
  box-sizing: border-box;
  grid-template-columns: 64rpx minmax(0, 1fr) 20rpx;
  column-gap: 24rpx;
  align-items: center;
}

.profile-menu__row:nth-child(1) {
  height: 140rpx;
}

.profile-menu__row:nth-child(2) {
  height: 129rpx;
}

.profile-menu__row:nth-child(3) {
  height: 127rpx;
}

.profile-menu__row:nth-child(4) {
  height: 125rpx;
}

.profile-menu__row:nth-child(5) {
  height: 129rpx;
}

.profile-menu__row:nth-child(1) .profile-menu__icon,
.profile-menu__row:nth-child(1) .profile-menu__label {
  position: relative;
  top: 5rpx;
}

.profile-menu__row:nth-child(5) .profile-menu__icon,
.profile-menu__row:nth-child(5) .profile-menu__label {
  position: relative;
  top: -4rpx;
}

.profile-menu__row:nth-child(1) .profile-menu__arrow {
  top: calc(50% + 5rpx);
}

.profile-menu__row:nth-child(3) .profile-menu__arrow {
  top: calc(50% + 2rpx);
}

.profile-menu__row:nth-child(5) .profile-menu__arrow {
  top: calc(50% - 2rpx);
}

.profile-menu__row + .profile-menu__row {
  border-top: 1rpx solid rgba(210, 222, 235, 0.24);
}

.profile-menu__icon {
  width: 60rpx;
  height: 64rpx;
  transform: translateX(-4rpx);
}

.profile-menu__row:nth-child(1) .profile-menu__icon {
  height: 62rpx;
}

.profile-menu__row:nth-child(2) .profile-menu__icon {
  width: 56rpx;
  height: 66rpx;
  transform: translateX(-2rpx);
}

.profile-menu__row:nth-child(3) .profile-menu__icon {
  width: 64rpx;
  height: 66rpx;
  transform: translateX(-6rpx);
}

.profile-menu__row:nth-child(4) .profile-menu__icon {
  width: 60rpx;
  height: 56rpx;
  transform: translateX(-4rpx);
}

.profile-menu__row:nth-child(5) .profile-menu__icon {
  width: 64rpx;
  height: 66rpx;
  transform: translateX(-6rpx);
}

.profile-menu__label {
  min-width: 0;
  color: #063c54;
  font-size: 33rpx;
  line-height: 44rpx;
  font-weight: 500;
  white-space: nowrap;
  -webkit-text-stroke: 0.35px #063c54;
}

.profile-menu__row:nth-child(4) .profile-menu__label {
  -webkit-text-stroke-width: 0.25px;
}

.profile-menu__row:nth-child(5) .profile-menu__label {
  -webkit-text-stroke-width: 0.4px;
}

.profile-info-page__logout {
  position: absolute;
  right: 43rpx;
  bottom: calc(env(safe-area-inset-bottom) + 124rpx);
  left: 43rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  height: 102rpx;
  margin: 0;
  padding: 0;
  border: 1rpx solid rgba(255, 255, 255, 0.94);
  border-radius: 27rpx;
  background:
    linear-gradient(90deg, rgba(255, 0, 0, 0) 0%, rgba(255, 0, 0, 0.045) 100%),
    linear-gradient(180deg, #168BF2 0%, #0868F4 100%);
  box-shadow: 0 14rpx 27rpx rgba(0, 91, 216, 0.08);
  color: #fff;
  font-size: 35rpx;
  line-height: 1;
  font-weight: 600;
}

@media (max-height: 700px) {
  .profile-info-page__content {
    min-height: 1620rpx;
  }
}
</style>
