<template>
  <view class="practice-start-page" :style="$appSafeAreaStyle">
    <view class="practice-start-page__backdrop"></view>
    <view class="practice-start-page__content">
      <view class="practice-start-nav">
        <view class="practice-start-nav__back" @tap="goBack">
          <uv-icon name="arrow-left" color="#066AF4" size="46rpx" />
        </view>
        <text class="practice-start-nav__title">{{ selectedCategory }}</text>
        <view class="practice-start-nav__spacer"></view>
      </view>

      <AppStateView
        v-if="pageStatus === 'error' || pageStatus === 'empty'"
        :status="pageStatus"
        :title="pageStatus === 'empty' ? '暂无练习信息' : '练习信息暂不可用'"
        :message="stateMessage"
        action-text="重新加载"
        @retry="loadPractice"
      />

      <PracticeStartSummary
        v-else-if="practice"
        :practice="practice"
        :category="selectedCategory"
        :loading="starting || pageStatus === 'loading'"
        :disabled="pageStatus !== 'ready'"
        :show-intro="false"
        @start="handleStart"
        @wrong-review="handleWrongReview"
      />
    </view>
    <SelfTestLoadingOverlay
      :show="pageStatus === 'loading'"
      title="正在加载练习题目"
      message="请稍候，系统正在同步练习批次。"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import AppStateView from '@/components/AppStateView.vue'
import PracticeStartSummary from '@/components/PracticeStartSummary.vue'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import {
  fetchPracticeStartPage,
  startPractice,
  type PracticeStartMode,
  type PracticeStartPage
} from '@/services/practice'
import { type AppAsyncStatus, requireLogin } from '@/stores/appState'

const practice = ref<PracticeStartPage | null>(null)
const pageStatus = ref<AppAsyncStatus>('loading')
const errorMessage = ref('')
const practiceId = ref('')
const topicId = ref('')
const topicTitle = ref('')
const mode = ref<PracticeStartMode>('standard')
const starting = ref(false)

const stateMessage = computed(() => errorMessage.value || '请从练习中心选择题型后重新进入。')
const selectedCategory = computed(() => topicTitle.value || practice.value?.category || '综合练习')

const createPracticeSkeleton = (): PracticeStartPage => ({
  id: practiceId.value || 'uav-basic-001',
  subject: '无人机驾驶员理论',
  category: selectedCategory.value,
  paperNo: '--',
  title: '无人机题库练习',
  questionCount: 0,
  totalScore: 0,
  timeLimitMinutes: 45,
  gradingMode: '系统阅卷',
  wrongQuestionCount: 0
})

const normalizedTopicId = computed(() => {
  if (topicId.value) {
    return topicId.value
  }
  const categoryTopicMap: Record<string, string> = {
    概述: 'overview',
    系统组成及介绍: 'system',
    空中交通管制: 'traffic',
    无人机飞行手册: 'manual',
    法律法规及其他: 'law',
    无人机操作注意事项: 'attention',
    气象: 'weather',
    旋翼无人机: 'rotor',
    无人机任务规划: 'planning',
    飞行原理与飞行性能: 'performance',
    综合问答: 'qa',
    无人机教员题库: 'teacher'
  }
  return categoryTopicMap[topicTitle.value] || ''
})

const loadPractice = async () => {
  pageStatus.value = 'loading'
  errorMessage.value = ''
  try {
    const result = await fetchPracticeStartPage(normalizedTopicId.value, mode.value)
    practice.value = result
    if (practiceId.value && result.id !== practiceId.value) {
      errorMessage.value = '练习信息已更新，请返回练习中心重新选择。'
      pageStatus.value = 'error'
      return
    }
    pageStatus.value = result ? 'ready' : 'empty'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '练习信息加载失败'
    pageStatus.value = 'error'
  }
}

const goBack = () => {
  uni.navigateBack({
    delta: 1,
    fail: () => uni.reLaunch({ url: '/pages/practice/exam-topics' })
  })
}

const navigateToAnswer = async (nextMode: PracticeStartMode) => {
  if (!practice.value || starting.value) {
    return
  }

  starting.value = true
  try {
    let nextPractice = practice.value
    if (nextMode === 'wrongReview') {
      nextPractice = await fetchPracticeStartPage(normalizedTopicId.value, 'wrongReview')
      practice.value = nextPractice
      pageStatus.value = nextPractice ? 'ready' : 'empty'
      if ((nextPractice?.wrongQuestionCount ?? 0) <= 0) {
        uni.showToast({ title: '当前练习服务暂无可复习错题', icon: 'none' })
        return
      }
    }

    const result = await startPractice(nextPractice.id, nextMode, normalizedTopicId.value)
    uni.navigateTo({
      url:
        `${result.nextPage}?id=${encodeURIComponent(result.practiceId)}` +
        `&sessionId=${encodeURIComponent(result.sessionId)}` +
        `&mode=${result.mode}` +
        `&topicId=${encodeURIComponent(normalizedTopicId.value)}` +
        `&topicTitle=${encodeURIComponent(selectedCategory.value)}`
    })
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '练习启动失败', icon: 'none' })
  } finally {
    starting.value = false
  }
}

const handleStart = () => navigateToAnswer(mode.value)
const handleWrongReview = () => navigateToAnswer('wrongReview')

onLoad((query) => {
  if (!requireLogin()) {
    return
  }

  practiceId.value = typeof query?.id === 'string' ? decodeURIComponent(query.id) : ''
  topicId.value = typeof query?.topicId === 'string' ? decodeURIComponent(query.topicId) : ''
  topicTitle.value = typeof query?.topicTitle === 'string' ? decodeURIComponent(query.topicTitle) : ''
  mode.value = query?.mode === 'wrongReview' ? 'wrongReview' : 'standard'
  practice.value = createPracticeSkeleton()
  void loadPractice()
})
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #f8fbff;
}

.practice-start-page {
  position: relative;
  min-height: 100vh;
  overflow-x: hidden;
  background-color: #f8fbff;
}

.practice-start-page__backdrop {
  position: absolute;
  z-index: 0;
  top: calc(var(--app-safe-area-top) + 108rpx);
  left: 50%;
  width: 100%;
  max-width: 750px;
  height: 372rpx;
  background: url('@/static/practice-start/overview-desk.jpg') center top / cover no-repeat;
  transform: translateX(-50%);
}

.practice-start-page__content {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  width: 100%;
  max-width: 750px;
  min-height: 100vh;
  margin: 0 auto;
  padding: var(--app-safe-area-top) 34rpx calc(env(safe-area-inset-bottom) + 40rpx);
}

.practice-start-nav {
  position: relative;
  height: 108rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f8fbff;
  box-shadow: 0 1rpx 0 rgba(96, 137, 185, 0.16);
  margin-right: -34rpx;
  margin-left: -34rpx;
  padding: 0 34rpx;
}

.practice-start-nav__back,
.practice-start-nav__spacer {
  position: absolute;
  top: 0;
  width: 72rpx;
  height: 108rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 0;
}

.practice-start-nav__back {
  left: 16rpx;
  transform: none;
}

.practice-start-nav__spacer {
  right: 12rpx;
}

.practice-start-nav__title {
  min-width: 0;
  overflow: hidden;
  color: #0b3150;
  font-size: 34rpx;
  line-height: 1.2;
  font-weight: 700;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: 0;
  transform: none;
}

.practice-start-page__content > .practice-start {
  margin-top: 372rpx;
  margin-right: -34rpx;
  margin-left: -34rpx;
}

.practice-start-page__content > .app-state-view {
  margin-top: 304rpx;
}

@media (max-width: 360px) {
  .practice-start-page__content {
    padding-right: 28rpx;
    padding-left: 28rpx;
  }

  .practice-start-nav {
    margin-right: -28rpx;
    margin-left: -28rpx;
    padding-right: 28rpx;
    padding-left: 28rpx;
  }

  .practice-start-nav__title {
    font-size: 32rpx;
  }

  .practice-start-page__content > .practice-start {
    margin-right: -28rpx;
    margin-left: -28rpx;
  }
}
</style>
