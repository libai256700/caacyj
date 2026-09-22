<template>
  <view class="exam-topics-page" :style="$appSafeAreaStyle">
    <view class="exam-topics-nav">
      <button class="exam-topics-nav__back" aria-label="返回首页" @tap="goHome">
        <uv-icon name="arrow-left" color="#0878EE" size="48rpx" />
      </button>
      <text class="exam-topics-nav__title">{{ pageTitle }}</text>
    </view>
    <view class="exam-topics-hero" aria-hidden="true"></view>
    <PracticeTopicGrid v-if="status === 'ready'" :topics="topics" @select="openTopic" />
    <AppStateView
      v-else-if="status !== 'loading'"
      :status="status"
      :title="stateTitle"
      :message="stateMessage"
      :action-text="status === 'error' ? '重新加载' : ''"
      @retry="loadTopics"
    />
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
import AppStateView from '@/components/AppStateView.vue'
import OrganizationBindingRequiredDialog from '@/components/OrganizationBindingRequiredDialog.vue'
import PracticeTopicGrid from '@/components/PracticeTopicGrid.vue'
import { fetchCurrentStudentAudit } from '@/services/customerAuth'
import {
  DEFAULT_PRACTICE_ID,
  fetchPracticeTopics,
  startChapterTestBatch,
  startPractice,
  startPracticeModeBatch,
  type PracticeTopic
} from '@/services/practice'
import { appState, type AppAsyncStatus, requireLogin } from '@/stores/appState'

type TopicEntryMode = 'practice' | 'chapter-test' | 'wrongReview'
const UNRESTRICTED_TOPIC_ID = '1'

const topics = ref<PracticeTopic[]>([])
const status = ref<AppAsyncStatus>('loading')
const errorMessage = ref('')
const mode = ref<TopicEntryMode>('practice')
const startingTopicId = ref('')
const bindingRequiredDialogVisible = ref(false)
const organizationBindingApproved = ref(
  appState.userSession?.auditStatus === 2 || appState.organizationBinding.status === 'approved'
)

const pageTitle = computed(() => {
  if (mode.value === 'chapter-test') return '章节测试'
  if (mode.value === 'wrongReview') return '错题练习'
  return '逐题练习'
})
const stateTitle = computed(() => status.value === 'loading' ? `正在加载${pageTitle.value}分类` : status.value === 'empty' ? '暂无可用题目主题' : `${pageTitle.value}暂不可用`)
const stateMessage = computed(() => errorMessage.value || (status.value === 'empty' ? '当前没有已启用的题目主题。' : '请稍候，正在同步题目主题。'))

const resolveEntryMode = (value: unknown): TopicEntryMode => {
  if (value === 'chapter-test') return 'chapter-test'
  if (value === 'wrongReview') return 'wrongReview'
  return 'practice'
}

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

const requiresOrganizationBinding = (topic: PracticeTopic) => topic.id !== UNRESTRICTED_TOPIC_ID

const loadTopics = async () => {
  status.value = 'loading'
  errorMessage.value = ''
  try {
    const result = await fetchPracticeTopics('', mode.value)
    topics.value = result.filter((topic) => topic.categoryStatus !== false)
    status.value = topics.value.length ? 'ready' : 'empty'
  } catch (error) {
    topics.value = []
    errorMessage.value = error instanceof Error ? error.message : '题目主题加载失败'
    status.value = 'error'
  }
}

const buildNavigateUrl = (nextPage: string, params: Array<[string, string]>) => {
  const query = params
    .filter(([, value]) => Boolean(value))
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join('&')
  if (!query) {
    return nextPage
  }
  return `${nextPage}${nextPage.includes('?') ? '&' : '?'}${query}`
}

const openTopic = async (topic: PracticeTopic) => {
  const selectedTopicId = topic.id || topic.fieldType || ''
  const topicId = topic.id || topic.fieldType || ''
  const topicTitle = topic.categoryName || topic.title
  if (!selectedTopicId || startingTopicId.value) {
    return
  }

  if (requiresOrganizationBinding(topic) && !await ensureOrganizationBindingApproved()) {
    bindingRequiredDialogVisible.value = true
    return
  }

  startingTopicId.value = selectedTopicId
  try {
    if (mode.value === 'wrongReview') {
      if ((topic.wrongQuestionCount || 0) <= 0) {
        uni.showToast({ title: '当前暂无错题可练习', icon: 'none' })
        return
      }
      const result = await startPractice(DEFAULT_PRACTICE_ID, 'wrongReview', selectedTopicId)
      uni.navigateTo({
        url: buildNavigateUrl(result.nextPage, [
          ['id', result.practiceId],
          ['sessionId', result.sessionId],
          ['mode', result.mode],
          ['topicId', topicId],
          ['topicTitle', topicTitle],
          ['recordId', result.recordId],
          ['catalogBatchId', result.catalogBatchId]
        ])
      })
      return
    }

    const startPracticeBatch = mode.value === 'chapter-test' ? startChapterTestBatch : startPracticeModeBatch
    const result = await startPracticeBatch(DEFAULT_PRACTICE_ID, selectedTopicId)
    if (mode.value === 'practice' && result.pendingSubmit) {
      const returnPage = `/pages/practice/exam-topics?mode=${encodeURIComponent(mode.value)}`
      uni.navigateTo({
        url: buildNavigateUrl('/pages/practice/answer', [
          ['id', result.practiceId],
          ['sessionId', result.sessionId],
          ['recordId', result.recordId],
          ['catalogBatchId', result.catalogBatchId],
          ['mode', result.mode],
          ['topicId', topicId],
          ['topicTitle', topicTitle],
          ['resumeQuestionIndex', String(result.resumeQuestionIndex ?? 0)],
          ['pendingSubmit', '1'],
          ['returnPage', returnPage]
        ])
      })
      return
    }
    uni.navigateTo({
      url: buildNavigateUrl('/pages/practice/exam-assessment', [
        ['practiceId', result.practiceId],
        ['catalogBatchId', result.catalogBatchId],
        ['sessionId', result.sessionId],
        ['recordId', result.recordId],
        ['mode', result.mode],
        ['topicId', topicId],
        ['topicTitle', topicTitle]
      ])
    })
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : `${pageTitle.value}创建失败`, icon: 'none' })
  } finally {
    startingTopicId.value = ''
  }
}

const goHome = () => {
  uni.reLaunch({ url: '/pages/home' })
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

onLoad((query) => {
  mode.value = resolveEntryMode(query?.mode)
  if (!requireLogin()) {
    return
  }
  void syncOrganizationBindingApproval()
  void loadTopics()
})

onShow(() => {
  if (!requireLogin()) {
    return
  }
  void syncOrganizationBindingApproval()
})
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #f2f7fd;
}

.exam-topics-page {
  box-sizing: border-box;
  min-height: 100vh;
  overflow: hidden;
  background: #f2f7fd;
}

.exam-topics-nav {
  position: relative;
  z-index: 2;
  height: max(84rpx, calc(var(--app-safe-area-top) + var(--app-page-header-height)));
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  padding: var(--app-safe-area-top) 36rpx 0;
  background: #ffffff;
  box-shadow: 0 2rpx 4rpx rgba(47, 91, 137, 0.14);
}

.exam-topics-nav__back {
  position: absolute;
  top: var(--app-safe-area-top);
  left: 23rpx;
  width: 48rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
}

.exam-topics-nav__back::after {
  border: 0;
}

.exam-topics-nav__title {
  color: #08264e;
  font-size: 36rpx;
  line-height: 44rpx;
  font-weight: 700;
  letter-spacing: 0;
}

.exam-topics-hero {
  position: relative;
  z-index: 0;
  height: 353rpx;
  background: url('@/static/exam-topics/practice-topics-hero-reference.png') center / 100% 100% no-repeat;
}
</style>
