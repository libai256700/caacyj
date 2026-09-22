<template>
  <view class="career-answer-page" :style="$appSafeAreaStyle">
    <view class="career-answer-page__backdrop" />
    <view class="career-answer-page__content">
      <view class="career-answer-nav">
        <button aria-label="返回" @tap="goBack"><uv-icon name="arrow-left" color="#06224A" size="44rpx" /></button>
        <text>职业规划评测</text>
        <text v-if="progressLabel">{{ progressLabel }}</text>
      </view>

      <AppStateView
        v-if="status === 'empty' || status === 'error'"
        :status="status"
        :title="stateTitle"
        :message="errorMessage"
        action-text="重新加载"
        @retry="loadAssessment"
      />
      <template v-else-if="showInterestGroup">
        <view class="career-answer-progress"><view :style="{ width: `${progress}%` }" /></view>
        <CoreScaleQuestionGroup
          :questions="groupQuestions"
          :answers="answers"
          :group-start-index="interestGroupStartIndex"
          variant="supplement"
          title="兴趣倾向"
          guide-text="请分别选择最符合你当前感受的数字。"
          section-title="兴趣倾向"
          :show-endpoints="false"
          @select="toggleQuestionOptionById"
        />
        <view class="career-answer-actions">
          <button v-if="previousIndex >= 0" class="career-answer-action career-answer-action--previous" :disabled="loading || questionLoading || submitting" @tap="previousQuestion">上一组</button>
          <button class="career-answer-action career-answer-action--next" :disabled="!canContinue || loading || questionLoading || submitting" @tap="nextQuestion">
            {{ submitting ? '提交中...' : (isLastQuestion ? '提交并生成报告' : '下一组') }}
          </button>
        </view>
      </template>
      <template v-else-if="question">
        <view class="career-answer-progress"><view :style="{ width: `${progress}%` }" /></view>
        <view class="career-answer-card">
          <text v-if="question.stepName" class="career-answer-card__step">{{ question.stepName }}</text>
          <text class="career-answer-card__type">{{ question.type }}</text>
          <text class="career-answer-card__stem">{{ question.stem || question.title }}<text v-if="!question.isRequired">（选填）</text></text>
          <textarea
            v-if="isTextQuestion"
            v-model="currentTextAnswer"
            class="career-answer-card__text"
            placeholder="请输入你的答案"
            maxlength="500"
            auto-height
          />
          <view v-else class="career-answer-options">
            <button
              v-for="option in question.options"
              :key="option.id"
              class="career-answer-option"
              :class="{ 'career-answer-option--selected': selectedOptionIds.includes(option.id) }"
              @tap="toggleQuestionOption(question, option.id)"
            >
              <text class="career-answer-option__label">{{ option.label }}</text>
              <text class="career-answer-option__content">{{ option.content }}</text>
            </button>
          </view>
        </view>
        <view class="career-answer-actions">
          <button v-if="previousIndex >= 0" class="career-answer-action career-answer-action--previous" :disabled="loading || questionLoading || submitting" @tap="previousQuestion">上一题</button>
          <button class="career-answer-action career-answer-action--next" :disabled="!canContinue || loading || questionLoading || submitting" @tap="nextQuestion">
            {{ submitting ? '提交中...' : (isLastQuestion ? '提交并生成报告' : '下一题') }}
          </button>
        </view>
      </template>
    </view>
    <SelfTestSubmittedDialog
      :visible="submittedDialogVisible"
      message="职业规划报告正在生成中，请稍后在首页“职业规划评测报告”中查看。"
      notice-text="生成完成后即可查看完整职业规划评测结果。"
      @home="returnHome"
    />
    <SelfTestLoadingOverlay :show="status === 'loading'" title="正在加载职业规划题目" message="请稍候，系统正在同步题目。" />
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import AppStateView from '@/components/AppStateView.vue'
import CoreScaleQuestionGroup from '@/components/practice/CoreScaleQuestionGroup.vue'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import SelfTestSubmittedDialog from '@/components/practice/SelfTestSubmittedDialog.vue'
import {
  fetchCareerAssessmentQuestion,
  fetchCareerAssessmentQuestions,
  submitCareerAssessmentAnswers,
  type CareerAssessmentQuestion
} from '@/services/careerAssessment'
import { type AppAsyncStatus, requireLogin } from '@/stores/appState'

const practiceId = ref('')
const sessionId = ref('')
const questionCache = ref<Record<number, CareerAssessmentQuestion>>({})
const answers = ref<Record<string, string[]>>({})
const textAnswers = ref<Record<string, string>>({})
const currentIndex = ref(0)
const totalQuestions = ref(0)
const status = ref<AppAsyncStatus>('loading')
const errorMessage = ref('')
const loading = ref(false)
const questionLoading = ref(false)
const submitting = ref(false)
const submittedDialogVisible = ref(false)
const interestGroupReady = ref(false)

const CAREER_WORK_VALUE_STEP = '工作价值'
const CAREER_INTEREST_STEP = '兴趣倾向'
const INTEREST_GROUP_START_INDEX = 13
const INTEREST_GROUP_END_INDEX = 24
const INTEREST_GROUP_COUNT = INTEREST_GROUP_END_INDEX - INTEREST_GROUP_START_INDEX + 1
const INTEREST_GROUP_ERROR = '职业规划兴趣倾向题目分组异常，请联系管理员检查题库配置'

const question = computed(() => questionCache.value[currentIndex.value] || null)
const isTextQuestion = computed(() => Boolean(question.value && (question.value.type === '文本题' || question.value.type === 'text' || !question.value.options.length)))
const selectedOptionIds = computed(() => question.value ? answers.value[question.value.id] || [] : [])
const currentTextAnswer = computed({
  get: () => question.value
    ? textAnswers.value[question.value.id] ?? answers.value[question.value.id]?.[0] ?? ''
    : '',
  set: (value: string) => {
    if (question.value) textAnswers.value[question.value.id] = value
  }
})
const interestGroupStartIndex = computed(() => groupQuestions.value[0]?.index ?? INTEREST_GROUP_START_INDEX)
const groupQuestions = computed(() => Object.values(questionCache.value)
  .filter((candidate) => candidate.index >= INTEREST_GROUP_START_INDEX && candidate.index <= INTEREST_GROUP_END_INDEX)
  .sort((left, right) => left.index - right.index))
const isInterestGroupQuestion = (candidate: CareerAssessmentQuestion | null | undefined) =>
  Boolean(candidate
    && candidate.index >= INTEREST_GROUP_START_INDEX
    && candidate.index <= INTEREST_GROUP_END_INDEX
    && candidate.stepName?.trim() === CAREER_INTEREST_STEP)
const hasValidInterestGroup = computed(() => groupQuestions.value.length === INTEREST_GROUP_COUNT
  && groupQuestions.value.every((candidate, offset) =>
    isInterestGroupQuestion(candidate) && candidate.index === INTEREST_GROUP_START_INDEX + offset))
const showInterestGroup = computed(() => Boolean(question.value
  && isInterestGroupQuestion(question.value)
  && interestGroupReady.value
  && hasValidInterestGroup.value))
const displayGroupEndIndex = computed(() => showInterestGroup.value
  ? groupQuestions.value[groupQuestions.value.length - 1]?.index ?? currentIndex.value
  : currentIndex.value)
const progress = computed(() => totalQuestions.value ? Math.round(((displayGroupEndIndex.value + 1) / totalQuestions.value) * 100) : 0)
const progressLabel = computed(() => totalQuestions.value
  ? `${showInterestGroup.value ? `${INTEREST_GROUP_START_INDEX + 1}-${displayGroupEndIndex.value + 1}` : currentIndex.value + 1}/${totalQuestions.value}`
  : '')
const previousIndex = computed(() => {
  if (showInterestGroup.value) {
    return INTEREST_GROUP_START_INDEX - 1
  }
  if (currentIndex.value === INTEREST_GROUP_END_INDEX + 1) {
    return INTEREST_GROUP_START_INDEX
  }
  return currentIndex.value - 1
})
const canContinue = computed(() => showInterestGroup.value
  ? groupQuestions.value.every((candidate) => candidate.isRequired === false || (answers.value[candidate.id] || []).length > 0)
  : question.value?.isRequired === false || (isTextQuestion.value
    ? Boolean(currentTextAnswer.value.trim())
    : selectedOptionIds.value.length > 0))
const isLastQuestion = computed(() => totalQuestions.value > 0 && displayGroupEndIndex.value >= totalQuestions.value - 1)
const stateTitle = computed(() => status.value === 'empty' ? '暂无职业规划评测题目' : '职业规划评测题目加载失败')
const isMultipleChoice = (candidate: CareerAssessmentQuestion | null) =>
  candidate?.type === '多选题' || candidate?.type === 'multiple_choice'
const isWorkValueQuestion = (candidate: CareerAssessmentQuestion | null) =>
  candidate?.stepName === CAREER_WORK_VALUE_STEP
const isTopValuesQuestion = (candidate: CareerAssessmentQuestion | null) =>
  isWorkValueQuestion(candidate) && isMultipleChoice(candidate)
const isLeastValueQuestion = (candidate: CareerAssessmentQuestion | null) =>
  isWorkValueQuestion(candidate) && !isMultipleChoice(candidate)

const cacheQuestion = (nextQuestion: CareerAssessmentQuestion) => {
  questionCache.value = { ...questionCache.value, [nextQuestion.index]: nextQuestion }
}

const loadInterestGroup = async (seedQuestion: CareerAssessmentQuestion) => {
  if (!seedQuestion || !isInterestGroupQuestion(seedQuestion)) {
    return
  }
  interestGroupReady.value = false
  if (groupQuestions.value.length >= INTEREST_GROUP_COUNT) {
    if (!hasValidInterestGroup.value) {
      throw new Error(INTEREST_GROUP_ERROR)
    }
    currentIndex.value = INTEREST_GROUP_START_INDEX
    interestGroupReady.value = true
    return
  }
  for (let index = INTEREST_GROUP_START_INDEX; index <= INTEREST_GROUP_END_INDEX; index += 1) {
    if (questionCache.value[index]) continue
    const page = await fetchCareerAssessmentQuestion(practiceId.value, sessionId.value, index)
    totalQuestions.value = page.totalQuestions
    if (page.question) cacheQuestion(page.question)
  }
  if (!hasValidInterestGroup.value) {
    throw new Error(INTEREST_GROUP_ERROR)
  }
  currentIndex.value = INTEREST_GROUP_START_INDEX
  interestGroupReady.value = true
}

const loadQuestion = async (index: number) => {
  interestGroupReady.value = false
  const cached = questionCache.value[index]
  if (cached) {
    if (isInterestGroupQuestion(cached)) {
      await loadInterestGroup(cached)
    } else {
      currentIndex.value = index
    }
    return
  }
  const page = await fetchCareerAssessmentQuestion(practiceId.value, sessionId.value, index)
  totalQuestions.value = page.totalQuestions
  if (!page.question) {
    status.value = 'empty'
    return
  }
  cacheQuestion(page.question)
  if (isInterestGroupQuestion(page.question)) {
    await loadInterestGroup(page.question)
  } else {
    currentIndex.value = page.currentIndex
  }
}

const loadAssessment = async () => {
  if (loading.value) return
  loading.value = true
  status.value = 'loading'
  errorMessage.value = ''
  try {
    const firstPage = await fetchCareerAssessmentQuestions()
    practiceId.value = firstPage.practiceId
    sessionId.value = firstPage.sessionId
    totalQuestions.value = firstPage.totalQuestions
    currentIndex.value = firstPage.currentIndex
    questionCache.value = {}
    answers.value = {}
    textAnswers.value = {}
    questionLoading.value = false
    interestGroupReady.value = false
    if (firstPage.question) {
      cacheQuestion(firstPage.question)
      if (isInterestGroupQuestion(firstPage.question)) {
        await loadInterestGroup(firstPage.question)
      } else {
        currentIndex.value = firstPage.currentIndex
      }
    }
    status.value = question.value ? 'ready' : 'empty'
  } catch (error) {
    status.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : '职业规划评测题目加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

const toggleQuestionOption = (candidate: CareerAssessmentQuestion, optionId: string) => {
  const current = answers.value[candidate.id] || []
  const multiple = isMultipleChoice(candidate)
  if (isTopValuesQuestion(candidate) && !current.includes(optionId) && current.length >= 3) {
    uni.showToast({ title: '最看重的工作价值只能选择 3 项', icon: 'none' })
    return
  }
  answers.value[candidate.id] = multiple
    ? current.includes(optionId) ? current.filter((id) => id !== optionId) : [...current, optionId]
    : [optionId]
}

const toggleQuestionOptionById = (questionId: string, optionId: string) => {
  const candidate = Object.values(questionCache.value).find((item) => item.id === questionId)
  if (!candidate) {
    return
  }
  toggleQuestionOption(candidate, optionId)
}

const optionContent = (candidate: CareerAssessmentQuestion, optionId: string) =>
  candidate.options.find((option) => option.id === optionId)?.content || ''

const validateCareerRules = (): boolean => {
  if (showInterestGroup.value) {
    return groupQuestions.value.every((candidate) => candidate.isRequired === false || (answers.value[candidate.id] || []).length > 0)
  }
  if (!question.value) return false
  if (isTopValuesQuestion(question.value) && selectedOptionIds.value.length !== 3) {
    uni.showToast({ title: '请选出刚好 3 项最看重的工作价值', icon: 'none' })
    return false
  }
  if (isLeastValueQuestion(question.value) && selectedOptionIds.value.length) {
    const topValuesQuestion = Object.values(questionCache.value).find((candidate) => isTopValuesQuestion(candidate))
    const leastValue = optionContent(question.value, selectedOptionIds.value[0])
    const topValues = topValuesQuestion
      ? (answers.value[topValuesQuestion.id] || []).map((id) => optionContent(topValuesQuestion, id))
      : []
    if (leastValue && topValues.includes(leastValue)) {
      uni.showToast({ title: '最不看重的项目不能与最看重的 3 项重复', icon: 'none' })
      return false
    }
  }
  return true
}

const previousQuestion = async () => {
  if (questionLoading.value || submitting.value) return
  if (previousIndex.value >= 0) {
    questionLoading.value = true
    try {
      await loadQuestion(previousIndex.value)
    } catch (error) {
      uni.showToast({ title: error instanceof Error ? error.message : '职业规划评测题目加载失败', icon: 'none' })
    } finally {
      questionLoading.value = false
    }
  }
}

const nextQuestion = async () => {
  if ((!question.value && !showInterestGroup.value) || !canContinue.value || loading.value || questionLoading.value || submitting.value) return
  if (!validateCareerRules()) return
  if (showInterestGroup.value) {
    questionLoading.value = true
    try {
      await loadQuestion(INTEREST_GROUP_END_INDEX + 1)
    } catch (error) {
      uni.showToast({ title: error instanceof Error ? error.message : '职业规划评测题目加载失败', icon: 'none' })
    } finally {
      questionLoading.value = false
    }
    return
  }
  if (isTextQuestion.value && question.value) answers.value[question.value.id] = [currentTextAnswer.value.trim()]
  if (!isLastQuestion.value) {
    questionLoading.value = true
    try {
      await loadQuestion(currentIndex.value + 1)
    } catch (error) {
      uni.showToast({ title: error instanceof Error ? error.message : '职业规划评测题目加载失败', icon: 'none' })
    } finally {
      questionLoading.value = false
    }
    return
  }

  submitting.value = true
  try {
    const loadedQuestions = Object.values(questionCache.value).sort((left, right) => left.index - right.index)
    const submissionPromise = submitCareerAssessmentAnswers(
      practiceId.value,
      sessionId.value,
      loadedQuestions.map((loadedQuestion) => ({
        questionId: loadedQuestion.id,
        selectedOptionIds: answers.value[loadedQuestion.id] || [],
        index: loadedQuestion.index
      }))
    )
    submittedDialogVisible.value = true
    await nextTick()
    await submissionPromise
  } catch (error) {
    submittedDialogVisible.value = false
    uni.showToast({ title: error instanceof Error ? error.message : '职业规划评测提交失败', icon: 'none' })
  } finally {
    submitting.value = false
  }
}

const returnHome = () => {
  submittedDialogVisible.value = false
  uni.reLaunch({ url: '/pages/home' })
}

const goBack = () => uni.navigateBack({ delta: 1, fail: () => uni.reLaunch({ url: '/pages/home' }) })

onLoad(() => {
  if (!requireLogin()) return
  void loadAssessment()
})
</script>

<style scoped lang="scss">
page { min-height: 100%; background: #F8FBFF; }
.career-answer-page { position: relative; min-height: 100vh; color: #09244a; background: #F8FBFF; }
.career-answer-page__backdrop { position: fixed; inset: 0; background: linear-gradient(rgba(248, 251, 255, .82), rgba(248, 251, 255, .82)), url('@/static/practice-start/paper-texture.jpg') center / 256rpx 150rpx repeat; }
.career-answer-page__content { position: relative; box-sizing: border-box; min-height: 100vh; padding: var(--app-safe-area-top) 28rpx calc(env(safe-area-inset-bottom) + 52rpx); }
.career-answer-nav { display: grid; height: var(--app-page-header-height); grid-template-columns: 110rpx minmax(0, 1fr) 110rpx; align-items: center; }
.career-answer-nav button { width: 72rpx; height: var(--app-page-header-height); margin: 0; padding: 0; border: 0; background: transparent; }
.career-answer-nav button::after { border: 0; }
.career-answer-nav text { font-size: 38rpx; font-weight: 600; text-align: center; }
.career-answer-nav text:last-child { font-size: 25rpx; font-weight: 400; text-align: right; }
.career-answer-progress { height: 8rpx; margin: 24rpx 6rpx 45rpx; overflow: hidden; border-radius: 99rpx; background: #EDF5FD; }
.career-answer-progress view { height: 100%; border-radius: inherit; background: #0868F4; transition: width .2s ease; }
.career-answer-card { min-height: 870rpx; padding: 40rpx 30rpx; border: 2rpx solid #DCE7F2; border-radius: 23rpx; background: rgba(255,255,255,.38); }
.career-answer-card__step, .career-answer-card__type, .career-answer-card__stem { display: block; }
.career-answer-card__step { color: #09244a; font-size: 30rpx; font-weight: 700; }
.career-answer-card__type { width: fit-content; margin-top: 22rpx; padding: 7rpx 14rpx; border: 2rpx solid #005BD8; border-radius: 12rpx; color: #005BD8; font-size: 24rpx; }
.career-answer-card__stem { margin-top: 35rpx; color: #000; font-size: 36rpx; line-height: 1.45; font-weight: 500; }
.career-answer-card__text { box-sizing: border-box; width: 100%; min-height: 200rpx; margin-top: 34rpx; padding: 24rpx; border: 2rpx solid #C9D8E8; border-radius: 14rpx; background: rgba(255,255,255,.5); font-size: 30rpx; line-height: 1.5; }
.career-answer-options { display: flex; flex-direction: column; gap: 20rpx; margin-top: 34rpx; }
.career-answer-option { display: flex; min-height: 112rpx; margin: 0; padding: 20rpx 28rpx; align-items: center; gap: 12rpx; border: 2rpx solid #C9D8E8; border-radius: 14rpx; background: rgba(255,255,255,.46); color: #000; text-align: left; }
.career-answer-option::after { border: 0; }
.career-answer-option--selected { border-color: #005BD8; background: #EAF4FF; }
.career-answer-option__label { flex: 0 0 auto; font-size: 30rpx; font-weight: 700; }
.career-answer-option__content { flex: 1; font-size: 30rpx; line-height: 1.35; }
.career-answer-actions { display: flex; gap: 18rpx; margin: 30rpx 4rpx 0; }
.career-answer-action { height: 94rpx; margin: 0; padding: 0; border-radius: 14rpx; font-size: 35rpx; line-height: 94rpx; font-weight: 500; }
.career-answer-action::after { border: 0; }
.career-answer-action--previous { width: 190rpx; border: 2rpx solid #005BD8; background: rgba(255,255,255,.72); color: #005BD8; }
.career-answer-action--next { min-width: 0; flex: 1; border: 0; background: #005BD8; color: #fff; }
.career-answer-action[disabled] { opacity: .55; }
</style>
