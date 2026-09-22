<template>
  <view class="organization-bind-page" :style="$appSafeAreaStyle">
    <image
      class="organization-bind-page__header-decoration"
      src="/static/organization-bind/organization-header-route.png"
      mode="scaleToFill"
    />

    <view class="organization-bind-page__content">
      <view class="organization-bind-page__header">
        <button
          class="organization-bind-page__back"
          aria-label="返回我的页面"
          @tap="returnToProfile"
        >
          <uv-icon name="arrow-left" color="#07192d" size="50rpx" />
        </button>
        <text class="organization-bind-page__title">选择所属组织</text>
      </view>

      <view class="organization-bind-page__search">
        <uv-icon name="search" color="#005BD8" size="58rpx" />
        <input
          v-model="keyword"
          class="organization-bind-page__search-input"
          maxlength="40"
          placeholder="搜索企业名称"
          placeholder-class="organization-bind-page__search-placeholder"
        />
      </view>

      <view v-if="visibleStatusMessage" class="organization-bind-page__status-tip">
        <text class="organization-bind-page__status-title">{{ visibleStatusMessage.title }}</text>
        <text class="organization-bind-page__status-text">{{ visibleStatusMessage.message }}</text>
      </view>

      <view class="organization-bind-page__list">
        <app-state-view
          v-if="!loading && filteredOrganizations.length === 0"
          status="empty"
          title="没有找到匹配组织"
          message="可以换个关键词搜索，或先跳过组织绑定继续使用小技。"
          :show-mark="false"
        />

        <template v-else>
          <view class="organization-bind-page__panel">
            <view
              v-for="item in currentOrganizations"
              :key="`current-${item.id}`"
              class="organization-section organization-section--current"
            >
              <view class="organization-section__title">
                <view class="organization-section__accent" />
                <text>当前组织</text>
              </view>
              <view class="organization-section__current-card">
                <organization-bind-card
                  :organization="item"
                  :button-text="submittingOrganizationId === item.id ? '提交中...' : resolveButtonText(item)"
                  :button-tone="resolveButtonTone(item.id)"
                  :disabled="isOrganizationActionDisabled(item.id)"
                  current
                  @apply="handleApply(item)"
                />
              </view>
            </view>

            <view
              v-if="availableOrganizations.length > 0"
              class="organization-section organization-section--available"
              :class="{ 'organization-section--available-only': currentOrganizations.length === 0 }"
            >
              <view class="organization-section__title">
                <view class="organization-section__accent" />
                <text>可申请加入的组织</text>
              </view>
              <view class="organization-section__cards">
                <organization-bind-card
                  v-for="item in availableOrganizations"
                  :key="item.id"
                  :organization="item"
                  :button-text="submittingOrganizationId === item.id ? '提交中...' : resolveButtonText(item)"
                  :button-tone="resolveButtonTone(item.id)"
                  :disabled="isOrganizationActionDisabled(item.id)"
                  @apply="handleApply(item)"
                />
              </view>
            </view>
          </view>
        </template>
      </view>

      <button class="organization-bind-page__footer-button" @tap="handleFooterAction">
        {{ footerButtonText }}
      </button>
    </view>

    <image
      class="organization-bind-page__footer-decoration"
      src="/static/organization-bind/organization-footer-route.png"
      mode="scaleToFill"
    />

    <SelfTestLoadingOverlay
      :show="loading"
      title="组织列表加载中"
      message="正在同步可用企业组织，请稍候。"
    />

    <organization-join-application-dialog
      :visible="Boolean(pendingApplication)"
      :organization="pendingApplication?.organization || null"
      :title="pendingApplication?.title || '申请加入组织'"
      :confirmation-text="pendingApplication?.confirmationText || ''"
      @close="closeApplicationDialog"
      @confirm="confirmApplicationDialog"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import AppStateView from '@/components/AppStateView.vue'
import OrganizationBindCard from '@/components/OrganizationBindCard.vue'
import OrganizationJoinApplicationDialog from '@/components/OrganizationJoinApplicationDialog.vue'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import { fetchCurrentStudentAudit, saveCustomerInfo, submitStudentAudit, type CustomerInfoSavePayload, type StudentAuditStatus } from '@/services/customerAuth'
import { listApprovedOrganizations, type OrganizationApplyMode, type OrganizationSummary } from '@/services/organization'
import {
  appState,
  requireLogin,
  setOrganizationBinding,
  skipOrganizationBinding,
  type OrganizationBindingEntry
} from '@/stores/appState'

const organizations = ref<OrganizationSummary[]>([])
const loading = ref(false)
const keyword = ref('')
const entrySource = ref<OrganizationBindingEntry>('direct')
const submittingOrganizationId = ref('')
const currentStudentAudit = ref<StudentAuditStatus | null>(null)
const pendingApplication = ref<{
  organization: OrganizationSummary
  title: string
  confirmationText: string
} | null>(null)

const filteredOrganizations = computed(() => {
  const normalizedKeyword = keyword.value.trim().toLowerCase()
  if (!normalizedKeyword) {
    return organizations.value
  }

  return organizations.value.filter((item) =>
    item.name.toLowerCase().includes(normalizedKeyword) ||
    item.tag.toLowerCase().includes(normalizedKeyword)
  )
})

const statusMessage = computed(() => {
  const audit = currentStudentAudit.value
  const auditStatus = resolveAuditStatus(audit)
  const auditOrganizationName = resolveAuditOrganizationName(audit)
  if (auditStatus === 'pending' && auditOrganizationName) {
    return {
      title: '申请状态',
      message: `你已向“${auditOrganizationName}”提交申请，审核通过后会自动完成组织绑定。`
    }
  }
  if (auditStatus === 'approved' && auditOrganizationName) {
    return {
      title: '当前组织',
      message: `你当前已绑定“${auditOrganizationName}”，如需更换，可继续发起新的组织申请。`
    }
  }
  if (auditStatus === 'rejected' && auditOrganizationName) {
    return {
      title: '申请已驳回',
      message: currentStudentAudit.value?.auditReason
        ? `你向“${auditOrganizationName}”提交的申请未通过：${currentStudentAudit.value.auditReason}`
        : `你向“${auditOrganizationName}”提交的申请未通过，可以重新提交。`
    }
  }

  const binding = appState.organizationBinding
  if (binding.status === 'pending' && binding.organizationName) {
    return {
      title: '申请状态',
      message: `你已向“${binding.organizationName}”提交申请，审核通过后会自动完成组织绑定。`
    }
  }
  if (binding.status === 'approved' && binding.organizationName) {
    return {
      title: '当前组织',
      message: `你当前已绑定“${binding.organizationName}”，如需更换，可继续发起新的组织申请。`
    }
  }
  if (binding.status === 'skipped') {
    return {
      title: '当前未绑定组织',
      message: '你可以先继续使用小技，后续也可以在“我的”页面重新绑定组织。'
    }
  }
  return null
})

const visibleStatusMessage = computed(() => {
  const message = statusMessage.value
  if (message?.title === '申请状态' || message?.title === '申请已驳回') {
    return message
  }
  return null
})

const currentOrganizationId = computed(() =>
  filteredOrganizations.value.find((item) => resolveBindingStatus(item.id) === 'approved')?.id || ''
)

const currentOrganizations = computed(() =>
  filteredOrganizations.value.filter((item) => item.id === currentOrganizationId.value)
)

const availableOrganizations = computed(() =>
  filteredOrganizations.value.filter((item) => item.id !== currentOrganizationId.value)
)

const footerButtonText = computed(() => {
  const auditStatus = resolveAuditStatus(currentStudentAudit.value)
  if (auditStatus === 'pending' || auditStatus === 'approved') {
    return entrySource.value === 'rebind' ? '返回我的页面' : '继续使用小技'
  }

  const binding = appState.organizationBinding
  if (binding.status === 'pending' || binding.status === 'approved') {
    return entrySource.value === 'rebind' ? '返回我的页面' : '继续使用小技'
  }
  return entrySource.value === 'rebind' ? '暂不重新绑定组织' : '暂不绑定组织'
})

onLoad((options) => {
  const entry = typeof options?.entry === 'string' ? options.entry : ''
  if (entry === 'login' || entry === 'rebind' || entry === 'direct') {
    entrySource.value = entry
  }
})

onShow(() => {
  if (!requireLogin()) {
    return
  }
  void loadOrganizations()
})

async function loadOrganizations() {
  loading.value = true
  try {
    const [organizationList, audit] = await Promise.all([
      listApprovedOrganizations(),
      fetchCurrentStudentAudit().catch(() => null)
    ])
    organizations.value = organizationList
    currentStudentAudit.value = audit
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '组织列表加载失败',
      icon: 'none'
    })
    organizations.value = []
  } finally {
    loading.value = false
  }
}

function resolveAuditOrganizationId(audit: StudentAuditStatus | null) {
  const organizationId = audit?.companyId || audit?.tenantId
  return organizationId ? String(organizationId) : ''
}

function resolveAuditStatus(audit: StudentAuditStatus | null) {
  if (!audit) {
    return null
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

function resolveAuditOrganizationName(audit: StudentAuditStatus | null) {
  const organizationId = resolveAuditOrganizationId(audit)
  if (!organizationId) {
    return ''
  }
  const organization = organizations.value.find((item) => item.id === organizationId)
  return organization?.name || appState.organizationBinding.organizationName || ''
}

function resolveBindingStatus(organizationId: string): 'pending' | 'approved' | 'rejected' | null {
  const audit = currentStudentAudit.value
  if (resolveAuditOrganizationId(audit) === organizationId) {
    return resolveAuditStatus(audit)
  }

  const binding = appState.organizationBinding
  if (binding.organizationId !== organizationId) {
    return null
  }
  if (binding.status === 'pending' || binding.status === 'approved') {
    return binding.status
  }
  return null
}

function resolveButtonText(organization: OrganizationSummary) {
  const status = resolveBindingStatus(organization.id)
  if (status === 'pending') {
    return '申请已提交'
  }
  if (status === 'approved') {
    return '已绑定'
  }
  if (status === 'rejected') {
    return '重新申请'
  }
  return organization.applyMode === 'bind' ? '申请绑定' : '申请加入'
}

function resolveButtonTone(organizationId: string) {
  const status = resolveBindingStatus(organizationId)
  if (status === 'pending') {
    return 'warning'
  }
  if (status === 'approved') {
    return 'success'
  }
  if (status === 'rejected') {
    return 'danger'
  }
  return 'outline'
}

function isOrganizationActionDisabled(organizationId: string) {
  const status = resolveBindingStatus(organizationId)
  return status === 'pending' || status === 'approved' || submittingOrganizationId.value === organizationId
}

function handleApply(organization: OrganizationSummary) {
  const binding = appState.organizationBinding
  const status = resolveBindingStatus(organization.id)

  if (status === 'pending') {
    uni.showToast({
      title: '该组织申请已提交，请等待审核',
      icon: 'none'
    })
    return
  }

  if (status === 'approved') {
    uni.showToast({
      title: '你已绑定当前组织',
      icon: 'none'
    })
    return
  }

  const actionText = status === 'rejected'
    ? '重新申请'
    : organization.applyMode === 'bind' ? '申请绑定' : '申请加入'
  const confirmationText =
    binding.status === 'pending' && binding.organizationName
      ? `当前你已申请“${binding.organizationName}”，确认改为向“${organization.name}”${actionText}吗？`
      : `确认${actionText}“${organization.name}”吗？`

  pendingApplication.value = {
    organization,
    title: actionText === '申请加入'
      ? '申请加入组织'
      : actionText === '申请绑定' ? '申请绑定组织' : '重新申请组织',
    confirmationText
  }
}

function closeApplicationDialog() {
  pendingApplication.value = null
}

function confirmApplicationDialog(payload: Pick<CustomerInfoSavePayload, 'realName' | 'idCard' | 'sex'>) {
  const application = pendingApplication.value
  if (!application) {
    return
  }

  pendingApplication.value = null
  void submitApplication(application.organization, payload)
}

async function submitApplication(
  organization: OrganizationSummary,
  customerInfo: Pick<CustomerInfoSavePayload, 'realName' | 'idCard' | 'sex'>
) {
  if (submittingOrganizationId.value) {
    return
  }

  const customerAccountId = appState.userSession?.userId
  if (!customerAccountId) {
    uni.showToast({ title: '请先登录学员账号', icon: 'none' })
    return
  }

  submittingOrganizationId.value = organization.id
  try {
    const saved = await saveCustomerInfo(customerInfo)
    if (saved === false) {
      throw new Error('学员信息保存失败')
    }
    await submitStudentAudit({
      tenantId: organization.tenantId,
      customerAccountId
    })

    setOrganizationBinding({
      organizationId: organization.id,
      organizationName: organization.name,
      applyMode: organization.applyMode as OrganizationApplyMode,
      entry: entrySource.value
    })

    uni.showToast({
      title: '申请已提交',
      icon: 'success'
    })
    currentStudentAudit.value = {
      id: 0,
      tenantId: organization.tenantId,
      companyId: organization.tenantId,
      customerAccountId,
      auditStatus: 1,
      auditReason: '',
      auditTime: ''
    }
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '提交组织申请失败',
      icon: 'none'
    })
  } finally {
    submittingOrganizationId.value = ''
  }
}

function handleFooterAction() {
  const auditStatus = resolveAuditStatus(currentStudentAudit.value)
  if (auditStatus === 'pending' || auditStatus === 'approved') {
    continueFlow()
    return
  }

  const binding = appState.organizationBinding
  if (binding.status === 'pending' || binding.status === 'approved') {
    continueFlow()
    return
  }

  skipOrganizationBinding(entrySource.value)
  continueFlow()
}

function continueFlow() {
  if (entrySource.value === 'rebind') {
    returnToProfile()
    return
  }

  if (appState.loginIdentity === 'enterprise') {
    uni.reLaunch({
      url: '/pages/service/customer-service'
    })
    return
  }

  uni.reLaunch({
    url: '/pages/center'
  })
}

function returnToProfile() {
  const pages = getCurrentPages()
  const previousPage = pages[pages.length - 2]
  const previousRoute = previousPage?.route?.replace(/^\//, '')

  if (previousRoute === 'pages/profile') {
    uni.navigateBack()
    return
  }

  uni.reLaunch({
    url: '/pages/profile'
  })
}
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #F5F9FF;
}

.organization-bind-page {
  position: relative;
  min-height: 100vh;
  padding: var(--app-safe-area-top) 28rpx calc(env(safe-area-inset-bottom) + 122rpx);
  box-sizing: border-box;
  overflow-x: hidden;
  color: #07192d;
  background:
    radial-gradient(circle at 88% 5%, rgba(255, 255, 255, 0.96) 0, rgba(255, 255, 255, 0) 34%),
    linear-gradient(180deg, #F5F9FF 0%, #FFFFFF 56%, #F5F9FF 100%);
  font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  letter-spacing: 0;
}

.organization-bind-page__content {
  position: relative;
  z-index: 2;
  min-height: calc(100vh - var(--app-safe-area-top) - env(safe-area-inset-bottom) - 178rpx);
  box-sizing: border-box;
}

.organization-bind-page__header {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--app-page-header-height);
}

.organization-bind-page__title,
.organization-bind-page__status-title,
.organization-bind-page__status-text {
  display: block;
}

.organization-bind-page__title {
  position: relative;
  z-index: 2;
  color: #06182b;
  font-size: 35rpx;
  line-height: var(--app-page-header-height);
  font-weight: 500;
  letter-spacing: 0;
  -webkit-text-stroke: 0.4rpx currentColor;
  transform: translateX(-8rpx);
}

.organization-bind-page__back {
  position: absolute;
  top: 0;
  left: -10rpx;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  line-height: 1;
}

.organization-bind-page__back::after {
  border: 0;
}

.organization-bind-page__header-decoration {
  position: absolute;
  top: 14rpx;
  right: 0;
  z-index: 0;
  display: block;
  width: 326rpx;
  height: 168rpx;
  pointer-events: none;
}

.organization-bind-page__search {
  display: flex;
  align-items: center;
  gap: 12rpx;
  height: 94rpx;
  margin: 72rpx 7rpx 0;
  padding: 0 30rpx 0 19rpx;
  box-sizing: border-box;
  border: 1rpx solid rgba(207, 229, 251, 0.76);
  border-radius: 32rpx;
  background: #fcfcfc;
  box-shadow:
    0 12rpx 26rpx rgba(58, 108, 168, 0.12),
    0 4rpx 8rpx rgba(89, 169, 255, 0.08),
    inset 0 0 0 1rpx rgba(255, 255, 255, 0.88);
}

.organization-bind-page__search-input {
  flex: 1;
  min-width: 0;
  height: 100%;
  color: #141414;
  font-size: 29rpx;
  font-weight: 500;
  letter-spacing: 0;
}

.organization-bind-page__search-placeholder {
  color: #989898;
}

.organization-bind-page__status-tip {
  margin-top: 28rpx;
  padding: 20rpx 24rpx;
  border-radius: 18rpx;
  background: rgba(244, 249, 255, 0.94);
  box-shadow: inset 0 0 0 1rpx rgba(89, 169, 255, 0.56);
}

.organization-bind-page__status-title {
  color: #0A67DA;
  font-size: 24rpx;
  line-height: 1.2;
  font-weight: 700;
}

.organization-bind-page__status-text {
  margin-top: 10rpx;
  color: #6f8098;
  font-size: 24rpx;
  line-height: 1.5;
}

.organization-bind-page__list {
  margin-top: 57rpx;
}

.organization-bind-page__status-tip + .organization-bind-page__list {
  margin-top: 24rpx;
}

.organization-bind-page__panel {
  margin-right: 6rpx;
  padding: 22rpx 0 18rpx;
  overflow: hidden;
  border-radius: 24rpx;
  background: #F7FAFE;
  box-shadow: 0 8rpx 26rpx rgba(27, 74, 124, 0.05);
}

.organization-section__title {
  display: flex;
  align-items: center;
  gap: 14rpx;
  height: 40rpx;
  margin: 0 20rpx;
  color: #06182b;
  font-size: 28rpx;
  line-height: 40rpx;
  font-weight: 500;
  letter-spacing: 0;
  -webkit-text-stroke: 0.4rpx currentColor;
  transform: translateY(-4rpx);
}

.organization-section__accent {
  flex: 0 0 6rpx;
  width: 6rpx;
  height: 34rpx;
  border-radius: 999rpx;
  background: #005BD8;
}

.organization-section__current-card,
.organization-section__cards {
  margin-right: 15rpx;
  margin-left: 18rpx;
}

.organization-section__current-card {
  margin-top: 17rpx;
}

.organization-section--available {
  margin-top: 55rpx;
}

.organization-section--available-only {
  margin-top: 0;
}

.organization-section__cards {
  display: flex;
  flex-direction: column;
  gap: 22rpx;
  margin-top: 20rpx;
}

.organization-bind-page__footer-button {
  position: fixed;
  left: calc(50% - 1rpx);
  bottom: calc(env(safe-area-inset-bottom) + 24rpx);
  z-index: 10;
  width: 692rpx;
  height: 76rpx;
  margin: 0;
  border-radius: 999rpx;
  color: #ffffff;
  background: linear-gradient(90deg, #168BF2 0%, #0868F4 100%);
  box-shadow:
    0 8rpx 18rpx rgba(0, 91, 216, 0.22),
    inset 0 0 0 1rpx rgba(255, 255, 255, 0.36);
  font-size: 36rpx;
  line-height: 76rpx;
  font-weight: 500;
  letter-spacing: 0;
  transform: translateX(-50%);
}

.organization-bind-page__footer-button::after {
  border: none;
}

.organization-bind-page__footer-decoration {
  position: fixed;
  right: 0;
  bottom: calc(env(safe-area-inset-bottom) + 80rpx);
  left: 0;
  z-index: 1;
  display: block;
  width: 750rpx;
  height: 94rpx;
  pointer-events: none;
}
</style>
