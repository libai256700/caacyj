<template>
  <view class="exam-modes-page" :style="$appSafeAreaStyle">
    <view class="exam-modes-nav">
      <button class="exam-modes-nav__back" aria-label="返回首页" @tap="goHome">
        <uv-icon name="arrow-left" color="#0878EE" size="52rpx" />
      </button>
      <text class="exam-modes-nav__title">考试</text>
    </view>

    <view class="exam-modes-hero">
      <text class="exam-modes-hero__title">选择考试模式</text>
      <text class="exam-modes-hero__note">批次创建后统一进入详情页，再开始答题</text>
    </view>

    <view class="exam-modes-list">
      <button
        v-for="entry in examEntries"
        :key="entry.mode"
        class="exam-modes-entry"
        :disabled="Boolean(startingMode)"
        :hover-class="startingMode ? '' : 'exam-modes-entry--pressed'"
        @tap="startExam(entry)"
      >
        <view class="exam-modes-entry__copy">
          <text class="exam-modes-entry__title">{{ entry.label }}</text>
          <text class="exam-modes-entry__desc">{{ entry.description }}</text>
        </view>
        <view class="exam-modes-entry__tail">
          <text v-if="startingMode === entry.mode" class="exam-modes-entry__loading">正在生成练习（考试）</text>
          <uv-icon v-else name="arrow-right" color="#8ea4ba" size="16" />
        </view>
      </button>
    </view>
    <OrganizationBindingRequiredDialog
      :visible="bindingRequiredDialogVisible"
      @close="closeBindingRequiredDialog"
      @service="openCustomerService"
      @bind="openProfileBinding"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import OrganizationBindingRequiredDialog from '@/components/OrganizationBindingRequiredDialog.vue'
import { fetchCurrentStudentAudit } from '@/services/customerAuth'
import {
  DEFAULT_PRACTICE_ID,
  closeIncompleteExamBatches,
  startComprehensiveExamBatch,
  startInstructorExamBatch,
  startTheoryExamBatch,
  type PracticeStartMode
} from '@/services/practice'
import { appState, requireLogin } from '@/stores/appState'

type ExamModeEntry = {
  label: string
  description: string
  mode: Extract<PracticeStartMode, 'comprehensive-exam' | 'theory-exam' | 'instructor-exam'>
}

const examEntries: ExamModeEntry[] = [
  {
    label: '理论考试',
    description: '按理论考试规则创建正式批次',
    mode: 'comprehensive-exam'
  },
  {
    label: '综合考试',
    description: '按综合考试规则创建正式批次',
    mode: 'theory-exam'
  },
  {
    label: '教员考试',
    description: '按教员考试规则创建正式批次',
    mode: 'instructor-exam'
  }
]

const startingMode = ref<ExamModeEntry['mode'] | ''>('')
const startingExamLabel = computed(() => examEntries.find((entry) => entry.mode === startingMode.value)?.label || '考试')
const bindingRequiredDialogVisible = ref(false)
const organizationBindingApproved = ref(
  appState.userSession?.auditStatus === 2 || appState.organizationBinding.status === 'approved'
)

const syncOrganizationBindingApproval = async () => {
  try {
    const studentAudit = await fetchCurrentStudentAudit().catch(() => null)
    organizationBindingApproved.value =
      studentAudit?.auditStatus === 2 ||
      appState.userSession?.auditStatus === 2 ||
      appState.organizationBinding.status === 'approved'
  } catch {
    organizationBindingApproved.value =
      appState.userSession?.auditStatus === 2 || appState.organizationBinding.status === 'approved'
  }
  return organizationBindingApproved.value
}

const ensureOrganizationBindingApproved = async () => {
  if (organizationBindingApproved.value) {
    return true
  }

  return syncOrganizationBindingApproval()
}

const goHome = () => {
  uni.reLaunch({ url: '/pages/home' })
}

const startExam = async (entry: ExamModeEntry) => {
  if (startingMode.value) {
    return
  }

  if (!await ensureOrganizationBindingApproved()) {
    bindingRequiredDialogVisible.value = true
    return
  }

  startingMode.value = entry.mode

  try {
    const startAction = entry.mode === 'comprehensive-exam'
      ? startComprehensiveExamBatch
      : entry.mode === 'theory-exam'
        ? startTheoryExamBatch
        : startInstructorExamBatch
    const result = await startAction(DEFAULT_PRACTICE_ID)
    uni.navigateTo({
      url:
        `/pages/practice/exam-assessment?practiceId=${encodeURIComponent(result.practiceId)}` +
        `&catalogBatchId=${encodeURIComponent(result.catalogBatchId)}` +
        `&sessionId=${encodeURIComponent(result.sessionId)}` +
        `&recordId=${encodeURIComponent(result.recordId)}` +
        `&mode=${encodeURIComponent(result.mode)}` +
        `&topicTitle=${encodeURIComponent(entry.label)}`
    })
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : `${entry.label}创建失败`, icon: 'none' })
  } finally {
    startingMode.value = ''
  }
}

const closeBindingRequiredDialog = () => {
  bindingRequiredDialogVisible.value = false
}

const openProfileBinding = () => {
  bindingRequiredDialogVisible.value = false
  uni.navigateTo({ url: '/pages/enterprise/organization-bind?entry=direct' })
}

const openCustomerService = () => {
  bindingRequiredDialogVisible.value = false
  uni.navigateTo({ url: '/pages/service/customer-service-chat?conversationId=default' })
}

onLoad(() => {
  if (!requireLogin()) {
    return
  }
  void syncOrganizationBindingApproval()
  void closeIncompleteExamBatches()
})

onShow(() => {
  if (!requireLogin()) {
    return
  }
  void syncOrganizationBindingApproval()
  void closeIncompleteExamBatches()
})
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #F3F8FD;
}

.exam-modes-page {
  box-sizing: border-box;
  min-height: 100vh;
  padding-bottom: calc(env(safe-area-inset-bottom) + 40rpx);
  background:
    linear-gradient(rgba(255, 253, 250, 0.58), rgba(255, 253, 250, 0.58)),
    url('@/static/practice-start/paper-texture.jpg') center / 256rpx 150rpx repeat;
}

.exam-modes-nav {
  position: relative;
  z-index: 2;
  height: calc(var(--app-safe-area-top) + var(--app-page-header-height));
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  padding: var(--app-safe-area-top) 36rpx 0;
  background: rgba(255, 253, 250, 0.94);
  box-shadow: 0 2rpx 2rpx rgba(47, 91, 137, 0.16);
}

.exam-modes-nav__back {
  position: absolute;
  bottom: 0;
  left: 25rpx;
  width: 72rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
}

.exam-modes-nav__back::after {
  border: 0;
}

.exam-modes-nav__title {
  color: #08264e;
  font-size: 40rpx;
  line-height: 48rpx;
  font-weight: 700;
  letter-spacing: 0;
}

.exam-modes-hero {
  padding: 48rpx 42rpx 24rpx;
}

.exam-modes-hero__title,
.exam-modes-hero__note {
  display: block;
}

.exam-modes-hero__title {
  color: #0b3150;
  font-size: 40rpx;
  line-height: 1.2;
  font-weight: 800;
}

.exam-modes-hero__note {
  margin-top: 12rpx;
  color: #637890;
  font-size: 24rpx;
  line-height: 1.5;
  font-weight: 500;
}

.exam-modes-list {
  display: flex;
  flex-direction: column;
  gap: 18rpx;
  padding: 0 42rpx;
}

.exam-modes-entry {
  box-sizing: border-box;
  display: grid;
  width: 100%;
  min-height: 138rpx;
  margin: 0;
  padding: 0 24rpx;
  align-items: center;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18rpx;
  border: 1rpx solid rgba(8, 104, 244, 0.2);
  border-radius: 24rpx;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 8rpx 20rpx rgba(21, 75, 133, 0.09);
  text-align: left;
}

.exam-modes-entry::after {
  border: 0;
}

.exam-modes-entry__copy {
  min-width: 0;
}

.exam-modes-entry__title,
.exam-modes-entry__desc,
.exam-modes-entry__loading {
  display: block;
}

.exam-modes-entry__title {
  color: #07394b;
  font-size: 30rpx;
  line-height: 1.3;
  font-weight: 700;
}

.exam-modes-entry__desc {
  margin-top: 8rpx;
  color: #637890;
  font-size: 22rpx;
  line-height: 1.5;
}

.exam-modes-entry__tail {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 48rpx;
}

.exam-modes-entry__loading {
  color: #0868F4;
  font-size: 22rpx;
  line-height: 1.2;
  font-weight: 600;
  white-space: nowrap;
}

.exam-modes-entry--pressed {
  border-color: #0868F4;
  background: #EAF4FF;
  box-shadow: 0 4rpx 10rpx rgba(21, 75, 133, 0.1);
  transform: translateY(1rpx);
}

.exam-modes-entry[disabled] {
  opacity: 1;
}

@media (max-width: 360px) {
  .exam-modes-hero,
  .exam-modes-list {
    padding-right: 28rpx;
    padding-left: 28rpx;
  }

  .exam-modes-entry {
    grid-template-columns: minmax(0, 1fr) auto;
    padding-right: 20rpx;
    padding-left: 20rpx;
  }
}
</style>
