<template>
  <view class="profile-page" :style="$appSafeAreaStyle">
    <scroll-view class="profile-page__scroll" scroll-y :show-scrollbar="false">
      <view class="profile-content">
      <text class="student-profile-title">我的</text>

      <view class="student-profile-card" @tap="handleProfileCardTap">
        <UserProfileAvatar
          class="avatar student-profile-card__avatar"
          :avatar-id="profileState.avatarId"
        />
        <button
          id="profile-edit-avatar"
          v-if="!isEnterpriseProfile"
          class="student-profile-card__avatar-action"
          hover-class="student-profile-card__avatar-action--pressed"
          @tap.stop="openProfileEditor"
        >
          更换头像
        </button>
        <view class="student-profile-card__body">
          <text class="student-profile-card__name">{{ displayedProfileName }}</text>
          <text class="student-profile-card__phone">{{ displayedMaskedPhone }}</text>
          <text class="student-profile-card__organization">
            所属组织： {{ displayedOrganizationName }}
          </text>
        </view>
        <view class="student-profile-card__status" @tap.stop="handleOrganizationStatusTap">
          <text>{{ displayedOrganizationStatus }}</text>
        </view>
      </view>

      <view class="student-menu">
        <view v-if="!isEnterpriseProfile" class="student-menu__row" @tap="goOrganizationBind">
          <image class="student-menu__icon" src="/static/profile-settings/profile-organization.svg?v=uniform-menu-icons-1" mode="aspectFit" />
          <text class="student-menu__label">绑定组织</text>
          <view class="student-menu__arrow" />
        </view>
        <view v-if="!isEnterpriseProfile" class="student-menu__row" @tap="handleMenu(recordMenus[0])">
          <image class="student-menu__icon" src="/static/profile-settings/profile-learning-record.svg?v=uniform-menu-icons-1" mode="aspectFit" />
          <text class="student-menu__label">{{ recordMenus[0].label }}</text>
          <view class="student-menu__arrow" />
        </view>
        <!-- <view class="student-menu__row" @tap="handleEnterpriseMenu(enterpriseMenuRows[0])">
          <image class="student-menu__icon" src="/static/profile-settings/settings-security.svg?v=uniform-menu-icons-1" mode="aspectFit" />
          <text class="student-menu__label">{{ enterpriseMenuRows[0].label }}</text>
          <view class="student-menu__arrow" />
        </view> -->
        <view class="student-menu__row" @tap="handleEnterpriseMenu(enterpriseMenuRows[1])">
          <image class="student-menu__icon" src="/static/profile-settings/cancel-account.svg?v=uniform-menu-icons-1" mode="aspectFit" />
          <text class="student-menu__label">{{ enterpriseMenuRows[1].label }}</text>
          <view class="student-menu__arrow" />
        </view>
        <view class="student-menu__row" @tap="handleEnterpriseMenu(enterpriseMenuRows[2])">
          <image class="student-menu__icon" src="/static/profile-settings/settings-service.svg?v=uniform-menu-icons-1" mode="aspectFit" />
          <text class="student-menu__label">{{ enterpriseMenuRows[2].label }}</text>
          <view class="student-menu__arrow" />
        </view>
        <view class="student-menu__row" @tap="handleEnterpriseMenu(enterpriseMenuRows[3])">
          <image class="student-menu__icon" src="/static/profile-settings/privacy.svg?v=uniform-menu-icons-1" mode="aspectFit" />
          <text class="student-menu__label">{{ enterpriseMenuRows[3].label }}</text>
          <view class="student-menu__arrow" />
        </view>
        <view class="student-menu__row" @tap="handleEnterpriseMenu(enterpriseMenuRows[4])">
          <image class="student-menu__icon" src="/static/profile-settings/settings-about.svg?v=uniform-menu-icons-1" mode="aspectFit" />
          <text class="student-menu__label">{{ enterpriseMenuRows[4].label }}</text>
          <view class="student-menu__arrow" />
        </view>
        <view class="student-menu__row" @tap="handleEnterpriseMenu(enterpriseMenuRows[5])">
          <image class="student-menu__icon" src="/static/profile-settings/logout.svg?v=uniform-menu-icons-1" mode="aspectFit" />
          <text class="student-menu__label">{{ enterpriseMenuRows[5].label }}</text>
          <view class="student-menu__arrow" />
        </view>
      </view>
      </view>
    </scroll-view>

    <view v-if="profileEditorVisible" class="profile-editor" @tap.stop @click.stop>
      <view class="profile-editor__mask" @tap.stop="closeProfileEditor" @click.stop="closeProfileEditor"></view>
      <view class="profile-editor__sheet" @tap.stop @click.stop>
        <view class="profile-editor__header">
          <text class="profile-editor__title">编辑资料</text>
          <text class="profile-editor__close" @tap.stop="closeProfileEditor" @click.stop="closeProfileEditor">×</text>
        </view>

        <view id="profile-avatar-upload" class="profile-editor__avatar-preview" @tap.stop="chooseAvatarImage">
          <UserProfileAvatar class="avatar avatar--preview" :avatar-id="draftProfile.avatarId" />
          <text class="profile-editor__avatar-action">{{ avatarUploading ? '上传中...' : '点击上传头像' }}</text>
        </view>

        <view class="profile-editor__field">
          <text class="profile-editor__label">昵称</text>
          <input
            v-model="draftProfile.nickname"
            class="profile-editor__input"
            maxlength="12"
            placeholder="请输入昵称"
            placeholder-class="profile-editor__placeholder"
          />
        </view>

        <view class="profile-editor__summary">
          <view class="profile-editor__summary-row">
            <text>手机号</text>
            <text>{{ maskedPhone }}</text>
          </view>
          <view class="profile-editor__summary-row">
            <text>所属组织</text>
            <text>{{ displayOrganizationName }}</text>
          </view>
        </view>

        <button
          id="profile-editor-save"
          class="profile-editor__save"
          :loading="profileSaving"
          :disabled="profileSaving || avatarUploading"
          @tap.stop="saveProfileEditor"
          @click.stop="saveProfileEditor"
        >
          {{ profileSaving ? '保存中...' : '保存' }}
        </button>
      </view>
    </view>
    <ProfileAboutDialog :visible="aboutDialogVisible" @close="closeAboutDialog" />
    <ProfileAccountCancellationDialog
      :visible="accountCancellationDialogVisible"
      @close="closeAccountCancellationDialog"
      @service="contactAccountCancellationService"
    />
    <ProfileLogoutDialog
      :visible="logoutDialogVisible"
      @close="closeLogoutDialog"
      @confirm="confirmLogoutAndRedirect"
    />
    <HomeProfileTabBar active="profile" />
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import HomeProfileTabBar from '@/components/HomeProfileTabBar.vue'
import ProfileAboutDialog from '@/components/ProfileAboutDialog.vue'
import ProfileAccountCancellationDialog from '@/components/ProfileAccountCancellationDialog.vue'
import ProfileLogoutDialog from '@/components/ProfileLogoutDialog.vue'
import UserProfileAvatar from '@/components/UserProfileAvatar.vue'
import { appState, clearUserSession, requireLogin, setActiveTab } from '@/stores/appState'
import {
  fetchCurrentCompany,
  fetchCurrentCustomer,
  fetchCurrentStudentAudit,
  logoutCompany,
  logoutCustomer,
  saveCustomerInfo,
  uploadAvatarImage,
  type StudentAuditStatus
} from '@/services/customerAuth'
import {
  fetchPracticeStatistics,
  fetchPracticeStartPage
} from '@/services/practice'
import { listApprovedOrganizations } from '@/services/organization'
import {
  DEFAULT_PROFILE_AVATAR_ID,
  PROFILE_STORAGE_KEY,
  normalizeProfileAvatarId
} from '@/utils/profileAvatar'
import { chooseAvatarImageFile } from '@/utils/avatarImagePicker'

type ProfileState = {
  nickname: string
  phone: string
  schoolName: string
  avatarId: string
  realName: string
  studentNo: string
  majorName: string
  roleLabel: string
  trainingDirection: string
}
type Tone = 'blue' | 'red'
type PracticeMetric = { key: string; label: string; value: string; unit: string; iconUrl: string; tone: Tone; type?: 'icon' | 'ring' }
type PracticeStatisticsState = {
  practiceTotal: number
  answerTotal: number
  accuracy: number
  streakDays: number
  wrongTotal: number
}
type EnterpriseProfileState = {
  nickname: string
  deptName: string
}
type MenuItem = { key: string; label: string; iconUrl: string; action: 'navigateTo' | 'noop'; targetUrl: string }
type EnterpriseMenuKey = 'security' | 'cancel' | 'service' | 'privacy' | 'about' | 'logout'
type EnterpriseMenuRow = { key: EnterpriseMenuKey; label: string; icon: string; danger?: boolean }

const baseProfile: ProfileState = {
  nickname: '未填写昵称',
  phone: '',
  schoolName: '未绑定组织',
  avatarId: DEFAULT_PROFILE_AVATAR_ID,
  realName: '',
  studentNo: '',
  majorName: '',
  roleLabel: 'student',
  trainingDirection: ''
}

const practiceStatistics = reactive<PracticeStatisticsState>({
  practiceTotal: 0,
  answerTotal: 0,
  accuracy: 0,
  streakDays: 0,
  wrongTotal: 0
})
const enterpriseProfileState = reactive<EnterpriseProfileState>({
  nickname: '企业用户',
  deptName: ''
})

const recordMenus: MenuItem[] = [
  { key: 'practiceRecord', label: '练习记录', iconUrl: '/static/icons/sheet03-r02-c04.png', action: 'navigateTo', targetUrl: '/pages/practice/record' },
  { key: 'selfTestRecord', label: '自测记录', iconUrl: '/static/icons/sheet03-r02-c05.png', action: 'navigateTo', targetUrl: '/pages/practice/self-test-record' }
]

const enterpriseMenuRows: EnterpriseMenuRow[] = [
  { key: 'security', label: '账号安全', icon: '/static/profile-settings/security.svg' },
  { key: 'cancel', label: '注销账号', icon: '/static/profile-settings/cancel-account.svg' },
  { key: 'service', label: '联系客服', icon: '/static/profile-settings/service.svg' },
  { key: 'privacy', label: '隐私协议', icon: '/static/profile-settings/privacy.svg' },
  { key: 'about', label: '关于小技', icon: '/static/profile-settings/about.svg' },
  { key: 'logout', label: '退出登录', icon: '/static/profile-settings/logout.svg', danger: true }
]

const profileState = reactive<ProfileState>(loadStoredProfile())
const draftProfile = reactive<ProfileState>({ ...profileState })
const profileEditorVisible = ref(false)
const aboutDialogVisible = ref(false)
const accountCancellationDialogVisible = ref(false)
const logoutDialogVisible = ref(false)
const profileSaving = ref(false)
const avatarUploading = ref(false)
const avatarChoosing = ref(false)
const currentStudentAudit = ref<StudentAuditStatus | null>(null)
const currentOrganizationName = ref(
  appState.organizationBinding.status === 'approved'
    ? appState.organizationBinding.organizationName
    : ''
)
let avatarChooseLockedUntil = 0
const isEnterpriseProfile = computed(() => appState.loginIdentity === 'enterprise')
const maskedPhone = computed(() => maskPhone(profileState.phone))
const studentAuditStatus = computed(() => {
  const auditStatus = resolveStudentAuditStatus(currentStudentAudit.value)
  if (auditStatus) {
    return auditStatus
  }
  return appState.organizationBinding.status === 'pending' ? 'pending' : null
})
const shouldShowStudentAuditProgress = computed(
  () => studentAuditStatus.value === 'pending' || studentAuditStatus.value === 'rejected'
)
const displayOrganizationName = computed(() => {
  if (shouldShowStudentAuditProgress.value) {
    return '审核进度'
  }
  if (studentAuditStatus.value !== 'approved') {
    return baseProfile.schoolName
  }
  return normalizeOrganizationName(currentOrganizationName.value)
})
const organizationActionText = computed(() =>
  shouldShowStudentAuditProgress.value ? '查看审核进度' : '重新绑定组织'
)
const practiceMetrics = computed<PracticeMetric[]>(() => [
  { key: 'practiceTotal', label: '累计练习次数', value: formatMetricNumber(practiceStatistics.practiceTotal), unit: '次', iconUrl: '/static/icons/sheet03-r02-c04.png', tone: 'blue', type: 'icon' },
  { key: 'answerTotal', label: '累计答题数', value: formatMetricNumber(practiceStatistics.answerTotal), unit: '题', iconUrl: '/static/icons/sheet03-r02-c02.png', tone: 'blue', type: 'icon' },
  { key: 'accuracy', label: '整体正确率', value: String(practiceStatistics.accuracy), unit: '%', iconUrl: '', tone: 'blue', type: 'ring' },
  { key: 'streakDays', label: '连续练习天数', value: formatMetricNumber(practiceStatistics.streakDays), unit: '天', iconUrl: '/static/icons/sheet03-r04-c04.png', tone: 'blue', type: 'icon' },
  { key: 'wrongTotal', label: '错题总数', value: formatMetricNumber(practiceStatistics.wrongTotal), unit: '道', iconUrl: '/static/icons/sheet03-r02-c02.png', tone: 'red', type: 'icon' }
])
const enterpriseProfileInfo = computed(() => {
  const session = appState.userSession
  const nickname = enterpriseProfileState.nickname || session?.name || '企业用户'
  const phone = session?.phone || baseProfile.phone
  const organizationName = normalizeOrganizationName(enterpriseProfileState.deptName)

  return {
    nickname,
    phone,
    organizationName
  }
})
const enterpriseMaskedPhone = computed(() => maskPhone(enterpriseProfileInfo.value.phone))
const displayedProfileName = computed(() =>
  isEnterpriseProfile.value ? enterpriseProfileInfo.value.nickname : profileState.nickname
)
const displayedMaskedPhone = computed(() =>
  isEnterpriseProfile.value ? enterpriseMaskedPhone.value : maskedPhone.value
)
const displayedOrganizationName = computed(() => {
  const organizationName = isEnterpriseProfile.value
    ? enterpriseProfileInfo.value.organizationName
    : displayOrganizationName.value
  return organizationName === '未绑定组织' ? '暂未绑定' : organizationName
})
const displayedOrganizationStatus = computed(() => {
  if (isEnterpriseProfile.value) {
    return '已绑定'
  }
  if (studentAuditStatus.value === 'rejected') {
    return '未通过'
  }
  if (studentAuditStatus.value === 'pending') {
    return '审核中'
  }
  return displayOrganizationName.value === '未绑定组织' ? '未绑定' : '已绑定'
})

onShow(() => {
  if (requireLogin()) {
    setActiveTab('profile')
    loadCurrentCompanyProfile()
    loadCurrentStudentAudit()
    loadPracticeStatistics()
  }
})

function loadStoredProfile(): ProfileState {
  const stored = uni.getStorageSync(PROFILE_STORAGE_KEY)
  if (!stored || typeof stored !== 'object') return { ...baseProfile }
  return {
    nickname: normalizeNickname(readString(stored, 'nickname', baseProfile.nickname)),
    phone: readString(stored, 'phone', baseProfile.phone),
    schoolName: readString(stored, 'schoolName', baseProfile.schoolName),
    avatarId: readAvatarId(readString(stored, 'avatarId', baseProfile.avatarId)),
    realName: readString(stored, 'realName', baseProfile.realName),
    studentNo: readString(stored, 'studentNo', baseProfile.studentNo),
    majorName: readString(stored, 'majorName', baseProfile.majorName),
    roleLabel: readString(stored, 'roleLabel', baseProfile.roleLabel),
    trainingDirection: readString(stored, 'trainingDirection', baseProfile.trainingDirection)
  }
}

async function loadCurrentCompanyProfile() {
  try {
    if (appState.loginIdentity !== 'enterprise') {
      const profile = await fetchCurrentCustomer()
      applyCustomerProfileFromApi({
        nickname: profile.nickname,
        phone: profile.mobile,
        schoolName: profile.schoolName,
        avatarId: profile.avatarUrl,
        realName: profile.realName,
        studentNo: profile.studentNo,
        majorName: profile.majorName,
        roleLabel: profile.roleLabel,
        trainingDirection: profile.trainingDirection
      })
      return
    }

    const profile = await fetchCurrentCompany()
    enterpriseProfileState.nickname = normalizeNickname(
      profile.nickname || appState.userSession?.name || '企业用户'
    )
    enterpriseProfileState.deptName = (profile.deptName || '').trim()
    if (appState.userSession) {
      appState.userSession.name = enterpriseProfileState.nickname
    }
  } catch (error) {
    if (appState.loginIdentity === 'enterprise') {
      enterpriseProfileState.nickname = normalizeNickname(appState.userSession?.name || '企业用户')
      enterpriseProfileState.deptName = ''
    }
    console.warn('load customer profile failed', error)
  }
}

async function loadCurrentStudentAudit() {
  if (appState.loginIdentity === 'enterprise') {
    currentStudentAudit.value = null
    currentOrganizationName.value = ''
    return
  }

  try {
    currentStudentAudit.value = await fetchCurrentStudentAudit()
  } catch (error) {
    currentStudentAudit.value = null
    currentOrganizationName.value =
      appState.organizationBinding.status === 'approved'
        ? appState.organizationBinding.organizationName
        : ''
    console.warn('load student audit failed', error)
    return
  }

  if (resolveStudentAuditStatus(currentStudentAudit.value) !== 'approved') {
    currentOrganizationName.value = ''
    return
  }

  const organizationId = resolveStudentAuditOrganizationId(currentStudentAudit.value)
  const cachedOrganizationName =
    appState.organizationBinding.status === 'approved' &&
    appState.organizationBinding.organizationId === organizationId
      ? appState.organizationBinding.organizationName
      : ''

  try {
    const organizations = await listApprovedOrganizations()
    currentOrganizationName.value =
      organizations.find((organization) => organization.id === organizationId)?.name ||
      cachedOrganizationName
  } catch (error) {
    currentOrganizationName.value = cachedOrganizationName
    console.warn('load organization name failed', error)
  }
}

async function loadPracticeStatistics() {
  if (appState.loginIdentity === 'enterprise') {
    return
  }

  try {
    const [statistics, wrongReview] = await Promise.all([
      fetchPracticeStatistics(),
      fetchPracticeStartPage('', 'wrongReview')
    ])
    Object.assign(practiceStatistics, {
      practiceTotal: normalizeMetricNumber(statistics.practiceTotal),
      answerTotal: normalizeMetricNumber(statistics.answerTotal),
      accuracy: Math.min(normalizeMetricNumber(statistics.accuracy), 100),
      streakDays: normalizeMetricNumber(statistics.streakDays),
      wrongTotal: normalizeMetricNumber(wrongReview.wrongQuestionCount)
    })
  } catch (error) {
    console.warn('load practice statistics failed', error)
  }
}

function applyCustomerProfileFromApi(profile: Partial<ProfileState>) {
  const nextProfile: ProfileState = {
    ...profileState,
    nickname: normalizeNickname(profile.nickname || baseProfile.nickname),
    phone: profile.phone || '',
    schoolName: normalizeOrganizationName(profile.schoolName),
    avatarId: readAvatarId(profile.avatarId || baseProfile.avatarId),
    realName: profile.realName || '',
    studentNo: profile.studentNo || '',
    majorName: profile.majorName || '',
    roleLabel: profile.roleLabel || 'student',
    trainingDirection: profile.trainingDirection || ''
  }
  Object.assign(profileState, nextProfile)
  uni.setStorageSync(PROFILE_STORAGE_KEY, { ...profileState })
}

function readString(source: unknown, key: string, fallback: string) {
  if (!source || typeof source !== 'object') return fallback
  const value = (source as Record<string, unknown>)[key]
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function normalizeNickname(value: string) {
  return value.trim() || baseProfile.nickname
}

function normalizeOrganizationName(value?: string) {
  const normalized = (value || '').trim()
  if (!normalized || normalized === '未填写学校' || normalized === '未填写学校名称') {
    return baseProfile.schoolName
  }
  return normalized
}

function resolveStudentAuditStatus(audit: StudentAuditStatus | null) {
  if (!audit) {
    const bindingStatus = appState.organizationBinding.status
    return bindingStatus === 'pending' || bindingStatus === 'approved' ? bindingStatus : null
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

function resolveStudentAuditOrganizationId(audit: StudentAuditStatus | null) {
  const organizationId = audit?.tenantId || audit?.companyId
  return organizationId ? String(organizationId) : ''
}

function readAvatarId(value: string) {
  return normalizeProfileAvatarId(value)
}

function maskPhone(phone: string) {
  const normalized = phone.replace(/\D/g, '')
  return normalized.length < 11 ? '未绑定手机号' : `${normalized.slice(0, 3)}*****${normalized.slice(-4)}`
}

function normalizeMetricNumber(value: unknown) {
  const numberValue = typeof value === 'number' ? value : Number(value || 0)
  return Number.isFinite(numberValue) && numberValue > 0 ? Math.floor(numberValue) : 0
}

function formatMetricNumber(value: number) {
  return normalizeMetricNumber(value).toLocaleString('en-US')
}

function goOrganizationBind() {
  if (shouldShowStudentAuditProgress.value) {
    uni.navigateTo({ url: '/pages/enterprise/organization-bind?entry=rebind' })
    return
  }

  uni.navigateTo({ url: '/pages/enterprise/organization-bind?entry=rebind' })
}

function handleProfileCardTap() {
  if (!isEnterpriseProfile.value) {
    openProfileEditor()
  }
}

function handleOrganizationStatusTap() {
  if (!isEnterpriseProfile.value) {
    goOrganizationBind()
  }
}

async function openProfileEditor() {
  await loadCurrentCompanyProfile()
  Object.assign(draftProfile, profileState)
  profileEditorVisible.value = true
}

function closeProfileEditor() {
  profileEditorVisible.value = false
}

function closeAboutDialog() {
  aboutDialogVisible.value = false
}

function closeAccountCancellationDialog() {
  accountCancellationDialogVisible.value = false
}

function contactAccountCancellationService() {
  closeAccountCancellationDialog()
  contactService()
}

async function chooseAvatarImage() {
  const now = Date.now()
  if (avatarUploading.value || avatarChoosing.value || now < avatarChooseLockedUntil) {
    return
  }

  avatarChoosing.value = true
  avatarChooseLockedUntil = now + 1500
  try {
    const { filePath, fileName, rawFile } = await chooseAvatarImageFile()
    const previousAvatar = draftProfile.avatarId
    draftProfile.avatarId = filePath
    avatarUploading.value = true
    try {
      draftProfile.avatarId = await uploadAvatarImage(filePath, fileName, rawFile)
      uni.showToast({ title: '头像上传成功', icon: 'success' })
    } catch (error) {
      draftProfile.avatarId = previousAvatar
      uni.showToast({
        title: error instanceof Error ? error.message : '头像上传失败',
        icon: 'none'
      })
    } finally {
      avatarUploading.value = false
    }
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '未选择头像图片',
      icon: 'none'
    })
  } finally {
    avatarChooseLockedUntil = Date.now() + 800
    setTimeout(() => {
      avatarChoosing.value = false
    }, 800)
  }
}

async function saveProfileEditor() {
  if (profileSaving.value) {
    return
  }

  if (avatarUploading.value) {
    uni.showToast({ title: '头像上传中，请稍候', icon: 'none' })
    return
  }

  const nickname = draftProfile.nickname.trim()
  if (!nickname) {
    uni.showToast({ title: '请输入昵称', icon: 'none' })
    return
  }

  const payload = {
    nickName: nickname.slice(0, 12),
    avatarUrl: readAvatarId(draftProfile.avatarId)
  }

  profileSaving.value = true
  try {
    await saveCustomerInfo(payload)
    const latestProfile = await fetchCurrentCustomer()
    applyCustomerProfileFromApi({
      nickname: latestProfile.nickname || payload.nickName,
      phone: latestProfile.mobile,
      schoolName: latestProfile.schoolName,
      avatarId: latestProfile.avatarUrl || payload.avatarUrl,
      realName: latestProfile.realName || profileState.realName,
      studentNo: latestProfile.studentNo || profileState.studentNo,
      majorName: latestProfile.majorName || profileState.majorName,
      roleLabel: latestProfile.roleLabel || profileState.roleLabel,
      trainingDirection: latestProfile.trainingDirection || profileState.trainingDirection
    })

    if (appState.userSession) {
      appState.userSession.name = profileState.nickname
    }

    profileEditorVisible.value = false
    uni.showToast({ title: '已保存', icon: 'success' })
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '学员信息保存失败',
      icon: 'none'
    })
  } finally {
    profileSaving.value = false
  }
}

async function handleMenu(item: MenuItem) {
  if (!item.targetUrl || item.action === 'noop') {
    showComingSoon(item.label)
    return
  }
  uni.navigateTo({ url: item.targetUrl })
}

function showComingSoon(title: string) {
  uni.showToast({ title, icon: 'none' })
}

function openSettings() {
  uni.navigateTo({
    url: '/pages/profile/settings'
  })
}

function handleEnterpriseMenu(item: EnterpriseMenuRow) {
  if (item.key === 'security') {
    uni.navigateTo({ url: '/pages/profile/phone-bind' })
    return
  }

  if (item.key === 'cancel') {
    accountCancellationDialogVisible.value = true
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
    aboutDialogVisible.value = true
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
  uni.reLaunch({ url: '/pages/auth/login' })
}
</script>

<style lang="scss">
page {
  height: 100%;
  min-height: 100%;
  overflow: hidden;
  background: #f8fbff;
}

button::after {
  border: 0;
}

.profile-page {
  position: relative;
  height: 100vh;
  min-height: 0;
  overflow: hidden;
  background: #f8fbff;
  color: #07183a;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.profile-page__scroll {
  width: 100%;
  height: 100%;
}

.profile-content {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  padding: var(--app-safe-area-top) 26rpx calc(env(safe-area-inset-bottom) + 124rpx);
  background: #f8fbff;
}

.profile-content > * {
  position: relative;
  z-index: 1;
}

.student-profile-title,
.student-profile-card text,
.student-menu text {
  display: block;
}

.student-profile-title {
  height: var(--app-page-header-height);
  color: #082432;
  font-size: 34rpx;
  line-height: var(--app-page-header-height);
  font-weight: 600;
  text-align: center;
  transform: none;
}

.student-profile-card,
.student-menu {
  box-sizing: border-box;
  border: 1rpx solid rgba(255, 255, 255, 0.92);
  border-radius: 28rpx;
  background:
    linear-gradient(rgba(255, 255, 255, 0.84), rgba(255, 255, 255, 0.84)),
    url('@/static/profile-settings/settings-paper-texture.jpg') center / 320rpx 188rpx repeat;
  box-shadow:
    0 10rpx 24rpx rgba(20, 70, 125, 0.1),
    inset 0 1rpx 0 rgba(255, 255, 255, 0.94);
}

.student-profile-card {
  position: relative;
  display: grid;
  grid-template-columns: 160rpx minmax(0, 1fr);
  column-gap: 32rpx;
  align-items: center;
  height: 266rpx;
  margin-top: 16rpx;
  padding: 0 32rpx;
}

.avatar {
  position: relative;
  width: 160rpx;
  height: 160rpx;
  overflow: hidden;
  border-radius: 50%;
}

.student-profile-card__avatar {
  box-sizing: border-box;
  border: 4rpx solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 0 0 1rpx rgba(8, 36, 50, 0.04);
  transform: translateY(-18rpx);
}

.student-profile-card__avatar-action {
  position: absolute;
  z-index: 2;
  bottom: 18rpx;
  left: 32rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 160rpx;
  height: 36rpx;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: #004FC4;
  font-size: 24rpx;
  line-height: 36rpx;
  font-weight: 600;
  letter-spacing: 0;
  white-space: nowrap;
}

.student-profile-card__avatar-action--pressed {
  color: #005bd8;
  background: transparent;
}

.student-profile-card__body {
  min-width: 0;
  transform: translateY(-2rpx);
}

.student-profile-card__name,
.student-profile-card__phone,
.student-profile-card__organization {
  overflow: hidden;
  color: #082432;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.student-profile-card__name {
  font-size: 36rpx;
  line-height: 48rpx;
  font-weight: 600;
  -webkit-text-stroke: 0.1px #082432;
}

.student-profile-card__phone,
.student-profile-card__organization {
  font-size: 29rpx;
  line-height: 40rpx;
  font-weight: 400;
}

.student-profile-card__phone {
  margin-top: 8rpx;
}

.student-profile-card__organization {
  margin-top: 8rpx;
  padding-right: 130rpx;
}

.student-profile-card__status {
  position: absolute;
  right: 39rpx;
  bottom: 64rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  min-width: 84rpx;
  height: 44rpx;
  padding: 0 4rpx;
  border-radius: 12rpx;
  background: #efefef;
  color: #242424;
  font-size: 24rpx;
  line-height: 44rpx;
  font-weight: 400;
  white-space: nowrap;
}

.student-menu {
  display: grid;
  grid-auto-rows: 120rpx;
  overflow: hidden;
  margin-top: 30rpx;
  padding: 0 32rpx;
}

.student-menu__row {
  position: relative;
  display: grid;
  grid-template-columns: 50rpx minmax(0, 1fr) 18rpx;
  column-gap: 36rpx;
  align-items: center;
}

.student-menu__row + .student-menu__row {
  border-top: 1rpx solid #E8EFF7;
}

.student-menu__icon {
  display: block;
  width: 50rpx;
  height: 56rpx;
  filter: none;
  transform: translateX(-8rpx);
}

.student-menu__label {
  overflow: hidden;
  color: #082432;
  font-size: 30rpx;
  line-height: 44rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
  -webkit-text-stroke: 0.15px #082432;
}

.student-menu__arrow {
  position: relative;
  right: 8rpx;
  box-sizing: border-box;
  width: 17rpx;
  height: 17rpx;
  border-right: 4rpx solid #b8bac0;
  border-bottom: 4rpx solid #b8bac0;
  border-radius: 1rpx;
  transform: translateX(-10rpx) rotate(-45deg);
}

.profile-editor {
  position: fixed;
  inset: 0;
  z-index: 9999;
}

.profile-editor__mask {
  position: absolute;
  inset: 0;
  background: rgba(6, 25, 54, 0.42);
}

.profile-editor__sheet {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  box-sizing: border-box;
  max-height: calc(100vh - var(--app-safe-area-top) - 40rpx);
  overflow-y: auto;
  padding: 34rpx 34rpx calc(var(--window-bottom, 50px) + env(safe-area-inset-bottom) + 34rpx);
  border-radius: 30rpx 30rpx 0 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(249, 252, 255, 0.98) 100%);
  box-shadow: 0 -22rpx 58rpx rgba(24, 60, 102, 0.2);
}

.profile-editor__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 58rpx;
}

.profile-editor__title,
.profile-editor__close,
.profile-editor__label,
.profile-editor__summary-row text {
  display: block;
}

.profile-editor__title {
  color: #071b3c;
  font-size: 34rpx;
  line-height: 1.2;
  font-weight: 860;
}

.profile-editor__close {
  width: 58rpx;
  height: 58rpx;
  color: #8fa0b7;
  font-size: 48rpx;
  line-height: 54rpx;
  text-align: center;
}

.profile-editor__avatar-preview {
  display: flex;
  align-items: center;
  flex-direction: column;
  justify-content: center;
  margin-top: 30rpx;
}

.profile-editor__avatar-action {
  display: block;
  margin-top: 18rpx;
  color: #167ee8;
  font-size: 24rpx;
  line-height: 1.2;
  font-weight: 760;
}

.avatar--preview {
  width: 142rpx;
  height: 142rpx;
}

.profile-editor__field {
  margin-top: 38rpx;
}

.profile-editor__label {
  color: #344761;
  font-size: 25rpx;
  line-height: 1.2;
  font-weight: 760;
}

.profile-editor__input {
  box-sizing: border-box;
  width: 100%;
  height: 88rpx;
  margin-top: 16rpx;
  padding: 0 24rpx;
  border: 1rpx solid #dce8f5;
  border-radius: 16rpx;
  background: #f7fbff;
  color: #071b3c;
  font-size: 30rpx;
  line-height: 88rpx;
  font-weight: 720;
}

.profile-editor__placeholder {
  color: #9aabc0;
  font-weight: 520;
}

.profile-editor__summary {
  margin-top: 24rpx;
  padding: 6rpx 0;
}

.profile-editor__summary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24rpx;
  min-height: 54rpx;
  color: #6b7d97;
  font-size: 24rpx;
  line-height: 1.2;
  font-weight: 560;
}

.profile-editor__summary-row text:last-child {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: #344761;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-editor__save {
  width: 100%;
  height: 88rpx;
  margin: 28rpx 0 0;
  padding: 0;
  border-radius: 16rpx;
  background: linear-gradient(135deg, #168af5 0%, #0568df 100%);
  box-shadow: 0 14rpx 30rpx rgba(13, 113, 226, 0.24);
  color: #ffffff;
  font-size: 30rpx;
  line-height: 88rpx;
  font-weight: 820;
}

@media (max-width: 360px) {
  .profile-editor__sheet {
    padding-left: 26rpx;
    padding-right: 26rpx;
  }
}
</style>
