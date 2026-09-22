<template>
  <view v-if="homeReady" class="preview-page" :style="$appSafeAreaStyle">
    <view class="phone-screen">
      <scroll-view class="content-scroll" scroll-y :show-scrollbar="false">
        <view class="reference-content">
          <image
            class="reference-content__image"
            src="/static/home/student-home-reference-v5.jpg?v=20260902-bottom-arc"
            mode="scaleToFill"
            aria-hidden="true"
          />

          <button
            class="reference-hotspot reference-hotspot--assessment-start"
            :disabled="startingSelfTest || startingCareerAssessment"
            aria-label="开始测评"
            @tap="openAssessmentChoice"
          >
            <text>开始测评</text>
          </button>
          <button
            class="reference-hotspot reference-hotspot--assessment-result"
            :disabled="selfTestReportLoading || careerReportLoading"
            aria-label="评测结果"
            @tap="openReportChoice"
          >
            <text>{{ selfTestReportLoading ? '加载中' : '评测结果' }}</text>
          </button>

          <button
            v-for="(entry, index) in assessmentEntries"
            :key="entry.label"
            class="reference-hotspot reference-hotspot--training"
            :class="`reference-hotspot--training-${index + 1}`"
            :disabled="entry.mode ? Boolean(startingAssessmentMode) : false"
            :aria-label="entry.label"
            @tap="startAssessmentTraining(entry.mode)"
          >
            <text>{{ entry.label }}</text>
          </button>

          <view
            v-if="wrongTotal !== null"
            class="wrong-count"
            :class="{ 'wrong-count--compact': wrongTotal >= 100 }"
            aria-live="polite"
          >
            <text>{{ wrongTotal }}</text>
          </view>
          <button
            class="reference-hotspot reference-hotspot--wrong"
            :disabled="startingWrongReview"
            aria-label="开始错题练习"
            @tap="startWrongReview"
          >
            <text>{{ startingWrongReview ? '准备中' : '开始练习' }}</text>
          </button>

          <button
            v-for="item in assistantItems"
            :key="item.title"
            class="reference-hotspot reference-hotspot--common"
            :class="`reference-hotspot--${item.action}`"
            :aria-label="item.title"
            @tap="handleAssistantAction(item.action)"
          >
            <text>{{ item.title }}</text>
          </button>
        </view>
        <view class="reference-nav-spacer" aria-hidden="true" />
      </scroll-view>

      <HomeProfileTabBar
        class="student-home-tabbar"
        active="home"
        brand-image-src="/static/home/bottom-nav-mascot-cutout.png"
        indicator-color="#ff9709"
      />
      <OrganizationBindingRequiredDialog
        :visible="bindingRequiredDialogVisible"
        @close="closeBindingRequiredDialog"
        @service="openCustomerService"
        @bind="openProfileBinding"
      />
      <SelfTestRestartDialog
        :visible="restartDialogVisible"
        :title="restartDialogTitle"
        :description="restartDialogDescription"
        :confirm-text="restartDialogConfirmText"
        @cancel="resolveAssessmentRestart(false)"
        @confirm="resolveAssessmentRestart(true)"
      />
      <SelfTestRestartDialog
        :visible="assessmentSavingDialogVisible"
        title="评测处理中"
        description="上次评测正在初始化分析，请稍后"
        confirm-text="知道了"
        :show-cancel="false"
        :close-on-mask="true"
        @cancel="closeAssessmentSavingDialog"
        @confirm="closeAssessmentSavingDialog"
      />
      <AssessmentChoiceDialog
        :visible="assessmentChoiceVisible"
        title="开始测评"
        description="请选择本次要进行的评测类型"
        :options="assessmentChoices"
        @close="closeAssessmentChoice"
        @select="selectAssessment"
      />
      <AssessmentChoiceDialog
        :visible="reportChoiceVisible"
        title="评测结果"
        description="请选择要查看的评测报告"
        :options="reportChoices"
        @close="closeReportChoice"
        @select="selectReport"
      />
    </view>
  </view>
</template>

<script setup lang="ts">
import { onLoad, onShow } from '@dcloudio/uni-app'
import { computed, ref } from 'vue'
import HomeProfileTabBar from '@/components/HomeProfileTabBar.vue'
import OrganizationBindingRequiredDialog from '@/components/OrganizationBindingRequiredDialog.vue'
import AssessmentChoiceDialog from '@/components/practice/AssessmentChoiceDialog.vue'
import SelfTestRestartDialog from '@/components/practice/SelfTestRestartDialog.vue'
import { appState, requireLogin, type EnterpriseReviewStatus } from '@/stores/appState'

type AssistantAction = 'jobs' | 'service'
type AssessmentEntryMode = 'practice' | 'chapter-test'

type AssessmentEntry = {
  label: string
  mode?: AssessmentEntryMode
}

const homeReady = ref(false)
const wrongTotal = ref<number | null>(null)
const startingWrongReview = ref(false)
const startingAssessmentMode = ref<AssessmentEntryMode | ''>('')
const bindingRequiredDialogVisible = ref(false)
const restartDialogVisible = ref(false)
const assessmentSavingDialogVisible = ref(false)
const enterpriseRedirecting = ref(false)
const enterpriseReviewRedirecting = ref(false)
const isEnterpriseTeacher = computed(() =>
  appState.loginIdentity === 'enterprise' && appState.userSession?.hasWtPost === true
)
const organizationBindingApproved = ref(
  appState.userSession?.auditStatus === 2 || appState.organizationBinding.status === 'approved'
)
const selfTestReportLoading = ref(false)
const careerReportLoading = ref(false)
const startingSelfTest = ref(false)
const startingCareerAssessment = ref(false)
const assessmentChoiceVisible = ref(false)
const reportChoiceVisible = ref(false)
const restartDialogTitle = ref('重新测评')
const restartDialogDescription = ref('已有测评记录，是否重新测评？')
const restartDialogConfirmText = ref('重新测评')
let restartDialogResolver: ((confirmed: boolean) => void) | null = null

const assessmentChoices = [
  { value: 'self', label: '自我评测', primary: true },
  { value: 'career', label: '职业规划评测' }
]

const reportChoices = [
  { value: 'self', label: '自我评测报告', primary: true },
  { value: 'career', label: '职业规划评测报告' }
]

const assessmentEntries: AssessmentEntry[] = [
  { label: '逐题练习', mode: 'practice' },
  { label: '章节测试', mode: 'chapter-test' },
  { label: '模拟考试' },
]

const assistantItems: Array<{
  title: string
  action: AssistantAction
}> = [
  { title: '岗位信息', action: 'jobs' },
  { title: '联系客服', action: 'service' },
]

function openPage(url: string) {
  uni.navigateTo({ url })
}

const confirmAssessmentRestart = (
  title = '重新测评',
  description = '已有测评记录，是否重新测评？',
  confirmText = '重新测评'
) => new Promise<boolean>((resolve) => {
  restartDialogTitle.value = title
  restartDialogDescription.value = description
  restartDialogConfirmText.value = confirmText
  restartDialogResolver = resolve
  restartDialogVisible.value = true
})

function resolveAssessmentRestart(confirmed: boolean) {
  restartDialogVisible.value = false
  restartDialogTitle.value = '重新测评'
  restartDialogDescription.value = '已有测评记录，是否重新测评？'
  restartDialogConfirmText.value = '重新测评'
  const resolve = restartDialogResolver
  restartDialogResolver = null
  resolve?.(confirmed)
}

function openAssessmentSavingDialog() {
  assessmentSavingDialogVisible.value = true
}

function closeAssessmentSavingDialog() {
  assessmentSavingDialogVisible.value = false
}

function openAssessmentChoice() {
  if (startingSelfTest.value || startingCareerAssessment.value) return
  assessmentChoiceVisible.value = true
}

function closeAssessmentChoice() {
  assessmentChoiceVisible.value = false
}

async function selectAssessment(value: string) {
  closeAssessmentChoice()
  if (value === 'self') {
    await startSelfTest()
    return
  }
  await startCareerAssessment()
}

async function startSelfTest() {
  if (startingSelfTest.value) return
  startingSelfTest.value = true
  try {
    const {
      fetchLatestAssessmentResultStatus,
      hasCompletedAssessment,
      resetCompletedAssessment
    } = await import('@/services/assessment')
    const latestStatus = await fetchLatestAssessmentResultStatus()
    if (latestStatus?.batchSaveStatus === 1) {
      openAssessmentSavingDialog()
      return
    }
    if (await hasCompletedAssessment()) {
      const confirmed = await confirmAssessmentRestart()
      if (!confirmed) return
      if (!await resetCompletedAssessment()) {
        throw new Error('未找到可重置的已完成测评，请刷新后重试')
      }
    }
    openPage('/pages/practice/self-test-answer')
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '自测启动失败，请稍后重试', icon: 'none' })
  } finally {
    startingSelfTest.value = false
  }
}

async function startCareerAssessment() {
  if (startingCareerAssessment.value) return
  startingCareerAssessment.value = true
  try {
    const {
      fetchLatestCareerAssessmentStatus,
      hasCompletedCareerAssessment
    } = await import('@/services/careerAssessment')
    const latestStatus = await fetchLatestCareerAssessmentStatus()
    if (latestStatus?.batchSaveStatus === 1) {
      openAssessmentSavingDialog()
      return
    }
    if (await hasCompletedCareerAssessment()) {
      const confirmed = await confirmAssessmentRestart(
        '重新职业规划评测',
        '已有职业规划评测记录，是否重新评测？',
        '重新评测'
      )
      if (!confirmed) return
    }
    openPage('/pages/practice/career-assessment-answer')
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '职业规划评测启动失败，请稍后重试', icon: 'none' })
  } finally {
    startingCareerAssessment.value = false
  }
}

async function startAssessmentTraining(mode?: AssessmentEntryMode) {
  if (mode) {
    if (startingAssessmentMode.value) {
      return
    }

    startingAssessmentMode.value = mode
    try {
      const { fetchLatestPracticeCatalogBatchDetail } = await import('@/services/practice')
      const latestBatch = await fetchLatestPracticeCatalogBatchDetail(mode === 'practice' ? 1 : 2, mode)
      if (latestBatch && !latestBatch.completed && latestBatch.practiceId && latestBatch.sessionId && latestBatch.recordId) {
        const returnPage = `/pages/practice/exam-topics?mode=${encodeURIComponent(mode)}`
        const resumeParams = latestBatch.pendingSubmit
          ? `&resumeQuestionIndex=${encodeURIComponent(String(latestBatch.resumeQuestionIndex ?? 0))}&pendingSubmit=1`
          : ''
        openPage(
          `/pages/practice/answer?id=${encodeURIComponent(latestBatch.practiceId)}` +
          `&sessionId=${encodeURIComponent(latestBatch.sessionId)}` +
          `&recordId=${encodeURIComponent(latestBatch.recordId)}` +
          `&catalogBatchId=${encodeURIComponent(latestBatch.catalogBatchId)}` +
          `&mode=${encodeURIComponent(mode)}` +
          `&topicId=${encodeURIComponent(String(latestBatch.categoryId || ''))}` +
          `&topicTitle=${encodeURIComponent(latestBatch.categoryName || (mode === 'practice' ? '逐题练习' : '章节测试'))}` +
          `${resumeParams}` +
          `&returnPage=${encodeURIComponent(returnPage)}`
        )
        return
      }
    } catch {
      // 继续原有分类页流程
    } finally {
      startingAssessmentMode.value = ''
    }

    openPage(`/pages/practice/exam-topics?mode=${encodeURIComponent(mode)}`)
    return
  }

  if (organizationBindingApproved.value) {
    openPage('/pages/practice/exam-modes')
    return
  }

  bindingRequiredDialogVisible.value = true
}

function closeBindingRequiredDialog() {
  bindingRequiredDialogVisible.value = false
}

function openProfileBinding() {
  bindingRequiredDialogVisible.value = false
  uni.navigateTo({ url: '/pages/enterprise/organization-bind?entry=direct' })
}

function openCustomerService() {
  bindingRequiredDialogVisible.value = false
  openPage('/pages/service/customer-service-chat?conversationId=default')
}

function handleAssistantAction(action: AssistantAction) {
  if (action === 'jobs') {
    openPage('/pages/jobs')
    return
  }

  openPage('/pages/service/customer-service-chat?conversationId=default')
}

async function openLatestSelfTestReport() {
  if (selfTestReportLoading.value) return
  selfTestReportLoading.value = true
  try {
    const { fetchLatestAssessmentResultStatus } = await import('@/services/assessment')
    const status = await fetchLatestAssessmentResultStatus()
    if (status?.completed !== true || !status.recordId) {
      uni.showModal({
        title: '测评未完成',
        content: '您的测评未完成，请继续完成测评',
        confirmText: '知道了',
        showCancel: false
      })
      return
    }
    openPage(`/pages/center/self-test-report?id=${encodeURIComponent(status.recordId)}`)
  } catch (error) {
    const message = error instanceof Error ? error.message : '自测报告加载失败，请稍后重试'
    if (/(不存在|未找到)/.test(message)) {
      uni.showModal({
        title: '测评未完成',
        content: '您的测评未完成，请继续完成测评',
        confirmText: '知道了',
        showCancel: false
      })
      return
    }
    uni.showToast({ title: message, icon: 'none' })
  } finally {
    selfTestReportLoading.value = false
  }
}

function openReportChoice() {
  if (selfTestReportLoading.value || careerReportLoading.value) return
  reportChoiceVisible.value = true
}

function closeReportChoice() {
  reportChoiceVisible.value = false
}

async function selectReport(value: string) {
  closeReportChoice()
  if (value === 'self') {
    await openLatestSelfTestReport()
    return
  }
  await openLatestCareerAssessmentReport()
}

async function openLatestCareerAssessmentReport() {
  if (careerReportLoading.value) return
  careerReportLoading.value = true
  try {
    const { fetchLatestCareerAssessmentReportEntry } = await import('@/services/careerAssessment')
    const status = await fetchLatestCareerAssessmentReportEntry()
    if (status?.completed !== true || !status.recordId) {
      uni.showModal({
        title: '暂无职业规划评测报告',
        content: '暂无可查看的职业规划评测报告。',
        confirmText: '知道了',
        showCancel: false
      })
      return
    }
    openPage(`/pages/center/career-assessment-report?id=${encodeURIComponent(status.recordId)}`)
  } catch (error) {
    const message = error instanceof Error ? error.message : '职业规划评测报告加载失败，请稍后重试'
    if (/(不存在|未找到)/.test(message)) {
      uni.showModal({
        title: '暂无职业规划评测报告',
        content: '暂无可查看的职业规划评测报告。',
        confirmText: '知道了',
        showCancel: false
      })
      return
    }
    uni.showToast({ title: message, icon: 'none' })
  } finally {
    careerReportLoading.value = false
  }
}

async function startWrongReview() {
  if (startingWrongReview.value || (wrongTotal.value ?? 0) <= 0) return
  startingWrongReview.value = true
  try {
    openPage('/pages/practice/exam-topics?mode=wrongReview')
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '练习启动失败', icon: 'none' })
  } finally {
    startingWrongReview.value = false
  }
}

async function guardHome() {
  if (!requireLogin()) {
    homeReady.value = false
    return
  }

  if (appState.loginIdentity === 'enterprise') {
    if (!isEnterpriseTeacher.value && Number(appState.userSession?.auditStatus ?? 0) !== 2) {
      homeReady.value = false
      if (!enterpriseReviewRedirecting.value) {
        enterpriseReviewRedirecting.value = true
        uni.reLaunch({
          url: resolveEnterpriseReviewRedirectUrl(),
          fail: () => {}
        })
      }
      return
    }

    enterpriseReviewRedirecting.value = false
    homeReady.value = false
    if (!enterpriseRedirecting.value) {
      enterpriseRedirecting.value = true
      uni.reLaunch({
        url: '/pages/enterprise/students',
        fail: () => {}
      })
    }
    return
  }

  enterpriseReviewRedirecting.value = false
  enterpriseRedirecting.value = false
  homeReady.value = true
  wrongTotal.value = null
  if (appState.userSession?.isPreview) {
    wrongTotal.value = 0
    organizationBindingApproved.value = true
    return
  }

  try {
    const { fetchPracticeStartPage } = await import('@/services/practice')
    const { fetchCurrentStudentAudit } = await import('@/services/customerAuth')
    const [wrongReview, studentAudit] = await Promise.all([
      fetchPracticeStartPage('', 'wrongReview'),
      fetchCurrentStudentAudit().catch(() => null)
    ])
    wrongTotal.value = wrongReview.wrongQuestionCount
    organizationBindingApproved.value =
      studentAudit?.auditStatus === 2 ||
      appState.userSession?.auditStatus === 2 ||
      appState.organizationBinding.status === 'approved'
  } catch {
    wrongTotal.value = null
    organizationBindingApproved.value =
      appState.userSession?.auditStatus === 2 || appState.organizationBinding.status === 'approved'
  }
}

function resolveEnterpriseReviewRedirectUrl() {
  const auditStatus = Number(appState.userSession?.auditStatus ?? 0)
  if (auditStatus === 1 || auditStatus === 3) {
    return `/pages/enterprise/review?status=${resolveEnterpriseReviewStatus(auditStatus)}`
  }
  return '/pages/enterprise/register'
}

function resolveEnterpriseReviewStatus(auditStatus: number): EnterpriseReviewStatus {
  if (auditStatus === 1) {
    return 'reviewing'
  }
  if (auditStatus === 3) {
    return 'rejected'
  }
  return 'pending'
}

onLoad(guardHome)

onShow(guardHome)
</script>

<style scoped lang="scss">
page {
  height: 100%;
  overflow: hidden;
  background: #f8fbff;
}

.preview-page {
  display: flex;
  height: 100vh;
  min-height: 0;
  overflow: hidden;
  justify-content: center;
  background: #f8fbff;
  color: #0b2244;
  font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
}

.phone-screen {
  position: relative;
  width: 100%;
  max-width: 430px;
  height: 100vh;
  overflow: hidden;
  background: #f8fbff;
}

.content-scroll {
  width: 100%;
  height: 100%;
}

.reference-content {
  position: relative;
  width: 100%;
  min-height: calc(100vh - min(104rpx, 60px));
  aspect-ratio: 852 / 1731;
  margin-top: var(--app-safe-area-top-extra);
  overflow: hidden;
  background: #f8fbff;
}

.reference-content__image {
  position: absolute;
  top: 0;
  left: 0;
  display: block;
  width: 100%;
  height: 106.6436%;
  pointer-events: none;
  user-select: none;
}

.student-home-tabbar :deep(.bottom-nav__surface) {
  height: 92rpx;
  max-height: 53px;
}

.reference-nav-spacer {
  width: 100%;
  height: 132.203rpx;
  max-height: 76.271px;
  background: #f8fbff;
}

.reference-hotspot {
  position: absolute;
  z-index: 2;
  box-sizing: border-box;
  display: block;
  min-width: 0;
  min-height: 0;
  margin: 0;
  padding: 0;
  overflow: hidden;
  border: 0;
  border-radius: 0;
  outline: 0;
  background: transparent;
  color: transparent;
  font-size: 0;
  line-height: 0;
  -webkit-tap-highlight-color: transparent;
}

.reference-hotspot::after {
  border: 0;
}

.reference-hotspot text {
  opacity: 0;
}

.reference-hotspot:focus-visible {
  outline: 2px solid #0878EE;
  outline-offset: -2px;
}

.reference-hotspot--assessment-start {
  top: 24.1898%;
  left: 55.7512%;
  width: 37.4413%;
  height: 6.5394%;
}

.reference-hotspot--assessment-result {
  top: 32.4074%;
  left: 55.7512%;
  width: 37.4413%;
  height: 7.0602%;
}

.reference-hotspot--training {
  top: 51.1574%;
  height: 18.0556%;
}

.reference-hotspot--training-1 {
  left: 5.5164%;
  width: 28.5211%;
}

.reference-hotspot--training-2 {
  left: 35.6808%;
  width: 27.3474%;
}

.reference-hotspot--training-3 {
  left: 64.7887%;
  width: 28.9906%;
}

.reference-hotspot--wrong {
  top: 81.8287%;
  left: 5.9859%;
  width: 32.277%;
  height: 4.5139%;
}

.reference-hotspot--common {
  top: 94.0394%;
  width: 20.892%;
  height: 3.7037%;
}

.reference-hotspot--jobs {
  left: 26.9953%;
}

.reference-hotspot--service {
  left: 72.1831%;
}

.wrong-count {
  position: absolute;
  z-index: 3;
  top: 76.55%;
  left: 12.2%;
  display: flex;
  width: 3.2%;
  height: 1.75%;
  align-items: center;
  justify-content: center;
  overflow: visible;
  background: #fcfdfe;
  color: #0878ee;
  font-size: clamp(11px, 2.95vw, 13px);
  line-height: 1;
  font-weight: 500;
  letter-spacing: 0;
  white-space: nowrap;
}

.wrong-count--compact {
  font-size: 9px;
}

@media (min-width: 431px) {
  .wrong-count {
    font-size: 13px;
  }

  .wrong-count--compact {
    font-size: 9px;
  }
}
</style>
