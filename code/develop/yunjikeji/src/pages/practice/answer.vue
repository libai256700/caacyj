<template>
  <view
    class="answer-page"
    :style="$appSafeAreaStyle"
    :class="{
      'answer-page--result': Boolean(answerResult),
      'answer-page--compact': !answerResult && !isTextQuestion && (displayQuestion?.options.length || 0) <= 4
    }"
  >
    <view class="answer-page__bg"></view>
    <view class="answer-page__content">
      <view class="answer-nav">
        <button class="answer-nav__back" aria-label="返回" @tap="goBack">
          <uv-icon name="arrow-left" color="#0b0b0b" size="44rpx" />
        </button>
        <text v-if="isTimedExam" class="answer-nav__timer">剩余 {{ formattedRemainingTime }}</text>

      </view>

      <AppStateView
        v-if="pageStatus === 'empty' || pageStatus === 'error'"
        :status="pageStatus"
        :title="stateTitle"
        :message="stateMessage"
        action-text="重新加载"
        @retry="reloadQuestion"
      />

      <template v-else-if="questionPage && displayQuestion">
        <view class="answer-hero">
          <view class="answer-progress">
            <view class="answer-progress__copy">
              <text class="answer-progress__current">{{ currentIndex + 1 }}</text>
              <text class="answer-progress__total">/ {{ questionPage.totalQuestions }}</text>
            </view>
            <view class="answer-progress__track">
              <view class="answer-progress__bar" :style="{ width: `${questionProgressPercent}%` }"></view>
            </view>
          </view>
          <image class="answer-hero__illustration" src="/static/practice-answer/drone-checklist.png" mode="aspectFit" />
        </view>

        <view class="answer-card-stage">
          <view class="answer-card-stage__layer"></view>
          <scroll-view
            class="answer-card-scroll"
            scroll-y
            scroll-with-animation
            :scroll-top="answerScrollTop"
          >
            <view class="question-card">
            <view class="question-card__header">
              <text class="question-card__tag" :class="{ 'question-card__tag--multiple': isMultipleChoice }">
                {{ questionTypeLabel }}
              </text>
              <text v-if="displayQuestion.title" class="question-card__title">{{ displayQuestion.title }}</text>
            </view>

            <text class="question-card__stem">{{ displayQuestion.stem }}</text>

            <view v-if="isTextQuestion" class="question-text-answer">
              <textarea
                v-model="textAnswer"
                class="question-text-answer__input"
                :disabled="Boolean(answerResult) || answerBusy"
                placeholder="请输入你的答案"
                maxlength="500"
                auto-height
              />
            </view>

            <view v-else class="question-options" :class="{ 'question-options--multiple': isMultipleChoice }">
              <button
                v-for="option in displayQuestion.options"
                :key="option.id"
                class="question-options__item"
                :class="optionClass(option.id)"
                :disabled="Boolean(answerResult) || answerBusy"
                @tap="selectOption(option.id)"
              >
                <view class="question-options__copy">
                  <text class="question-options__label">{{ option.label }}.</text>
                  <text class="question-options__content">{{ option.content }}</text>
                </view>
                <view class="question-options__status">
                  <uv-icon
                    v-if="isWrongSelected(option.id)"
                    name="close"
                    color="#b94747"
                    size="30rpx"
                  />
                  <uv-icon
                    v-else-if="selectedOptionIds.includes(option.id) || answerResult?.correctOptionIds.includes(option.id)"
                    name="checkmark"
                    color="#151a1c"
                    size="32rpx"
                  />
                </view>
              </button>
            </view>

            <view v-if="answerBusy && !answerResult" class="question-card__pending">
              <text>{{ autoSubmitting ? '正在判题' : '提交中' }}</text>
            </view>

          </view>

          <view v-if="answerResult" class="result-card" :class="answerResult.correct ? 'result-card--correct' : 'result-card--wrong'">
            <view class="result-card__head">
              <view class="result-card__badge">
                <uv-icon :name="answerResult.correct ? 'checkmark' : 'close'" color="#FFFFFF" size="34rpx" />
              </view>
              <view class="result-card__title-wrap">
                <text class="result-card__title">{{ answerResult.correct ? '回答正确' : '回答错误' }}</text>
                <view v-if="!answerResult.correct && correctAnswerLabel" class="result-card__answer">
                  <text>正确答案</text>
                  <text>{{ correctAnswerLabel }}</text>
                </view>
              </view>
            </view>

            <view v-if="showAnswerExplanation" class="result-detail">
              <view class="result-detail__head">
                <text>试题详解</text>
                <button class="result-detail__ai" @tap="openAiAnswer">
                  <image class="result-detail__ai-logo" src="/static/brand/ai-assistant-logo.png" mode="aspectFit" />
                  <text>AI 深度解答</text>
                  <uv-icon name="arrow-right" color="#6557b8" size="28rpx" />
                </button>
              </view>
              <text class="result-detail__text">{{ answerResult.explanation }}</text>
            </view>

            <view class="question-video">
              <button class="question-video__button" :disabled="videoLoading || !displayQuestion?.videoAvailable" @tap="openQuestionVideo">
                <uv-icon name="play-circle" color="#167b68" size="36rpx" />
                <text>{{ videoLoading ? '加载中' : '视频讲解' }}</text>
                <text v-if="!displayQuestion?.videoAvailable" class="question-video__empty">暂无视频</text>
              </button>
            </view>

            <view class="answer-summary">
              <view v-for="item in summaryItems" :key="item.label" class="answer-summary__item">
                <text class="answer-summary__label">{{ item.label }}</text>
                <text class="answer-summary__value">{{ item.value }}</text>
              </view>
            </view>
          </view>
          </scroll-view>
        </view>

        <view class="answer-actions" :class="{ 'answer-actions--split': currentIndex > 0 }">
          <button
            v-if="currentIndex > 0"
            class="answer-actions__secondary"
            :disabled="answerBusy"
            @tap="goPrevious"
          >
            上一题
          </button>
          <button
            v-if="!answerResult && (isMultipleChoice || isTextQuestion)"
            class="answer-actions__primary"
            :disabled="!canSubmitAnswer || answerBusy"
            @tap="submitAnswer"
          >
            {{ answerBusy ? '提交中' : (isPracticePendingSubmit ? '完成测试' : '提交') }}
          </button>
          <button v-else-if="!answerResult" class="answer-actions__primary" :disabled="answerBusy">
            {{ answerBusy ? '判题中' : '下一题' }}
          </button>
          <button v-else class="answer-actions__primary" @tap="goNext">
            {{ answerResult.completed ? (isPracticePendingSubmit ? '完成测试' : '完成练习') : '下一题' }}
          </button>
        </view>

        <view v-if="videoPlaybackUrl" class="question-video-modal" @tap="closeQuestionVideo">
          <view class="question-video-modal__panel" @tap.stop>
            <view class="question-video-modal__head">
              <text class="question-video-modal__title">视频讲解</text>
              <button class="question-video-modal__close" aria-label="关闭视频" @tap="closeQuestionVideo">
                <uv-icon name="close" color="#252b2f" size="34rpx" />
              </button>
            </view>
            <view class="question-video-modal__frame">
              <video
                :key="videoPlaybackUrl"
                class="question-video-modal__player"
                :src="videoPlaybackUrl"
                controls
                autoplay
                object-fit="contain"
                :show-mute-btn="true"
                :show-center-play-btn="true"
                :show-fullscreen-btn="true"
                @error="onVideoError"
              />
            </view>
          </view>
        </view>
      </template>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import AppStateView from '@/components/AppStateView.vue'
import {
  fetchAnswerCard,
  fetchPracticeRecordDetail,
  fetchPracticeQuestion,
  submitPracticeAnswer,
  type PracticeAnswerResult,
  type PracticeQuestion,
  type PracticeQuestionPage,
  type PracticeQuestionListPage,
  type PracticeRecordAnswer,
  type PracticeStartMode
} from '@/services/practice'
import { type AppAsyncStatus, requireLogin } from '@/stores/appState'

const practiceId = ref('')
const sessionId = ref('')
const recordId = ref('')
const catalogBatchId = ref('')
const topicId = ref('')
const topicTitle = ref('')
const returnPage = ref('')
const mode = ref<PracticeStartMode>('practice')
const pendingSubmit = ref(false)
const resumeQuestionIndex = ref<number | null>(null)
const currentIndex = ref(0)
const pageStatus = ref<AppAsyncStatus>('loading')
const questionLoading = ref(false)
const errorMessage = ref('')
const questionPage = ref<PracticeQuestionListPage | null>(null)
const recordAnswers = ref<PracticeRecordAnswer[]>([])
const selectedOptionIds = ref<string[]>([])
const textAnswer = ref('')
const answerResult = ref<PracticeAnswerResult | null>(null)
const submitting = ref(false)
const autoSubmitting = ref(false)
const answeredQuestionSnapshot = ref<PracticeQuestion | null>(null)
const answerScrollTop = ref(0)
const remainingSeconds = ref(0)
let examTimer: ReturnType<typeof setInterval> | null = null

const cloneQuestion = (question: PracticeQuestion): PracticeQuestion => ({
  ...question,
  options: question.options.map((option) => ({ ...option }))
})

const currentQuestion = computed(() => questionPage.value?.questions[0] || null)
const displayQuestion = computed(() => answeredQuestionSnapshot.value || currentQuestion.value)
const videoPlaybackUrl = ref('')
const videoLoading = ref(false)
let videoRequestVersion = 0
watch(() => displayQuestion.value?.id, () => {
  videoRequestVersion += 1
  videoPlaybackUrl.value = ''
  videoLoading.value = false
})

const openQuestionVideo = async () => {
  if (videoLoading.value || !displayQuestion.value?.videoAvailable) return
  const questionId = displayQuestion.value.id
  const version = ++videoRequestVersion
  videoLoading.value = true
  videoPlaybackUrl.value = ''
  try {
    // Refresh the short-lived URL without changing the current answer or cloud batch.
    const result = await fetchPracticeQuestion(practiceId.value, sessionId.value, mode.value, currentIndex.value)
    if (version !== videoRequestVersion || displayQuestion.value?.id !== questionId) return
    if (result.question?.id !== questionId || !result.question.videoUrl) {
      throw new Error('视频暂不可用，请稍后重试')
    }
    videoPlaybackUrl.value = result.question.videoUrl
  } catch (error) {
    if (version === videoRequestVersion) {
      uni.showToast({ title: error instanceof Error ? error.message : '视频加载失败', icon: 'none' })
    }
  } finally {
    if (version === videoRequestVersion) videoLoading.value = false
  }
}

const closeQuestionVideo = () => {
  videoRequestVersion += 1
  videoPlaybackUrl.value = ''
  videoLoading.value = false
}

const onVideoError = () => {
  closeQuestionVideo()
  uni.showToast({ title: '视频播放失败，请点击重试', icon: 'none' })
}
const answerBusy = computed(() => submitting.value || autoSubmitting.value)

const questionProgressPercent = computed(() => {
  if (!questionPage.value?.totalQuestions) {
    return 0
  }
  return Math.min(Math.ceil(((currentIndex.value + 1) / questionPage.value.totalQuestions) * 100), 100)
})

const wrongCount = computed(() => {
  if (!questionPage.value) {
    return 0
  }
  return Math.max(questionPage.value.answeredCount - questionPage.value.correctCount, 0)
})

const summaryItems = computed(() => {
  const correct = questionPage.value?.correctCount || 0
  const total = questionPage.value?.totalQuestions || 0
  return [
    { label: '总题数', value: total },
    { label: '答对', value: correct },
    { label: '答错', value: wrongCount.value }
  ]
})

const questionTypeLabel = computed(() => displayQuestion.value?.type || '单选题')
const modeLabel = computed(() => {
  switch (mode.value) {
    case 'chapter-test': return '章节测试'
    case 'theory-exam': return '综合考试'
    case 'comprehensive-exam': return '理论考试'
    case 'instructor-exam': return '教员考试'
    default: return '逐题练习'
  }
})

const isTimedExam = computed(() => ['theory-exam', 'comprehensive-exam', 'instructor-exam'].includes(mode.value))
const isPracticePendingSubmit = computed(() => mode.value === 'practice' && pendingSubmit.value)
const formattedRemainingTime = computed(() => {
  const total = Math.max(remainingSeconds.value, 0)
  const minutes = Math.floor(total / 60).toString().padStart(2, '0')
  const seconds = (total % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
})

const stopExamTimer = () => {
  if (examTimer) {
    clearInterval(examTimer)
    examTimer = null
  }
}

const startExamTimer = () => {
  stopExamTimer()
  if (!isTimedExam.value || remainingSeconds.value <= 0) return
  examTimer = setInterval(() => {
    remainingSeconds.value = Math.max(remainingSeconds.value - 1, 0)
    if (remainingSeconds.value === 0) {
      stopExamTimer()
      uni.showToast({ title: '考试时间已到，本次考试结束', icon: 'none' })
      const targetRecordId = recordId.value || ''
      setTimeout(() => uni.reLaunch({ url: buildRecordDetailUrl(targetRecordId) }), 350)
    }
  }, 1000)
}

const stateTitle = computed(() => {
  if (pageStatus.value === 'loading') {
    return '正在拉取题目'
  }
  if (pageStatus.value === 'empty') {
    return '暂无练习题'
  }
  return '题目加载失败'
})

const stateMessage = computed(() => errorMessage.value || '请确认练习会话有效后重试。')

const buildRecordDetailUrl = (id = '') =>
  id
    ? `/pages/practice/record-detail?recordId=${encodeURIComponent(id)}`
    : '/pages/practice/record-detail'

const readQueryValue = (value: unknown) => {
  if (typeof value !== 'string') {
    return ''
  }
  try {
    return decodeURIComponent(value).trim()
  } catch {
    return value.trim()
  }
}

const readBooleanValue = (value: unknown) => {
  if (typeof value !== 'string') {
    return false
  }
  return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase())
}

const readMode = (value: unknown): PracticeStartMode => {
  if (value === 'chapter-test') return 'chapter-test'
  if (value === 'theory-exam') return 'theory-exam'
  if (value === 'comprehensive-exam') return 'comprehensive-exam'
  if (value === 'instructor-exam') return 'instructor-exam'
  if (value === 'wrongReview') return 'wrongReview'
  if (value === 'standard') return 'standard'
  return 'practice'
}

const applyQuestionPage = (result: PracticeQuestionListPage) => {
  questionPage.value = result
  currentIndex.value = Math.max(result.currentIndex || 0, 0)
  selectedOptionIds.value = []
  textAnswer.value = ''
  answerResult.value = null
  answeredQuestionSnapshot.value = null
  errorMessage.value = ''
  pageStatus.value = result.questions.length ? 'ready' : 'empty'
  restoreRecordedAnswer()
}

const toQuestionListPage = (result: PracticeQuestionPage): PracticeQuestionListPage => ({
  practiceId: result.practiceId,
  sessionId: result.sessionId,
  mode: result.mode,
  currentIndex: result.currentIndex,
  totalQuestions: result.totalQuestions,
  answeredCount: result.answeredCount,
  correctCount: result.correctCount,
  progressPercent: result.progressPercent,
  questions: result.question ? [result.question] : []
})

const loadQuestion = async (index = currentIndex.value) => {
  if (!practiceId.value || !sessionId.value) {
    pageStatus.value = 'error'
    errorMessage.value = '练习会话参数缺失，无法拉取题目。'
    return
  }

  const hasQuestion = Boolean(currentQuestion.value)
  questionLoading.value = true
  if (!hasQuestion) {
    pageStatus.value = 'loading'
  }
  errorMessage.value = ''
  try {
    const result = await fetchPracticeQuestion(practiceId.value, sessionId.value, mode.value, index)
    applyQuestionPage(toQuestionListPage(result))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '题目加载失败'
    if (isTimedExam.value && remainingSeconds.value === 0) {
      pageStatus.value = 'error'
      uni.showToast({ title: '考试时间已到，本次考试结束', icon: 'none' })
      const targetRecordId = recordId.value || ''
      setTimeout(() => uni.reLaunch({ url: buildRecordDetailUrl(targetRecordId) }), 350)
      return
    }
    if (!hasQuestion) {
      pageStatus.value = 'error'
    } else {
      uni.showToast({
        title: errorMessage.value,
        icon: 'none'
      })
    }
  } finally {
    questionLoading.value = false
  }
}

const loadRecordAnswers = async () => {
  recordAnswers.value = []
  if (!recordId.value) {
    return
  }

  try {
    const record = await fetchPracticeRecordDetail(recordId.value)
    recordAnswers.value = record.answers || []
  } catch {
    recordAnswers.value = []
  }
}

const restoreRecordedAnswer = () => {
  const questionId = currentQuestion.value?.id
  if (!questionId) {
    return
  }

  const recordAnswer = recordAnswers.value.find((item) => item.questionId === questionId)
  if (!recordAnswer) {
    return
  }

  const restoredSelectedOptionIds = resolveRecordedOptionIds(recordAnswer.selectedOptionIds || [])
  const restoredCorrectOptionIds = resolveRecordedOptionIds(recordAnswer.correctOptionIds || [])
  selectedOptionIds.value = restoredSelectedOptionIds
  textAnswer.value = isTextQuestion.value
    ? (recordAnswer.selectedOptionIds?.[0] || recordAnswer.answer || '')
    : ''
  answerResult.value = buildRecordedAnswerResult(recordAnswer, restoredSelectedOptionIds, restoredCorrectOptionIds)
}

const resolveRecordedOptionIds = (optionIds: string[]) => {
  if (isTextQuestion.value) {
    return optionIds
  }
  const options = currentQuestion.value?.options || []
  return optionIds
    .map((optionId) => {
      const normalizedOptionId = optionId.trim()
      if (!normalizedOptionId) {
        return ''
      }
      const matchedOption = options.find((option) =>
        option.id === normalizedOptionId || option.label === normalizedOptionId
      )
      return matchedOption?.id || normalizedOptionId
    })
    .filter(Boolean)
}

const buildRecordedAnswerResult = (
  recordAnswer: PracticeRecordAnswer,
  restoredSelectedOptionIds: string[],
  restoredCorrectOptionIds: string[]
): PracticeAnswerResult => {
  const totalQuestions = questionPage.value?.totalQuestions || 0
  const lastQuestionIndex = totalQuestions > 0 ? totalQuestions - 1 : currentIndex.value
  const nextQuestionIndex = Math.min(currentIndex.value + 1, Math.max(lastQuestionIndex, currentIndex.value))

  return {
    questionId: recordAnswer.questionId,
    selectedOptionId: restoredSelectedOptionIds.join(','),
    selectedOptionIds: [...restoredSelectedOptionIds],
    correctOptionId: restoredCorrectOptionIds.join(','),
    correctOptionIds: [...restoredCorrectOptionIds],
    correct: Boolean(recordAnswer.correctFlag),
    explanation: recordAnswer.explanation || '暂无标准解析。',
    currentIndex: currentIndex.value,
    nextQuestionIndex,
    totalQuestions,
    answeredCount: questionPage.value?.answeredCount || 0,
    correctCount: questionPage.value?.correctCount || 0,
    progressPercent: questionPage.value?.progressPercent || 0,
    completed: totalQuestions > 0 && currentIndex.value >= lastQuestionIndex,
    recordId: recordId.value,
    stepName: recordAnswer.stepName,
    stepStatus: recordAnswer.stepStatus
  }
}

const loadInitialQuestion = async () => {
  await loadRecordAnswers()
  const resumeBatch = (mode.value === 'practice' || mode.value === 'chapter-test')
    && Boolean(recordId.value)
    && !pendingSubmit.value
  if (!resumeBatch) {
    if (mode.value === 'practice' && pendingSubmit.value && recordId.value) {
      const targetIndex = Math.max(resumeQuestionIndex.value ?? 0, 0)
      pageStatus.value = 'loading'
      errorMessage.value = ''
      try {
        await loadQuestion(targetIndex)
      } catch (error) {
        errorMessage.value = error instanceof Error ? error.message : '答题进度加载失败'
        pageStatus.value = 'error'
      }
      return
    }
    await loadQuestion(0)
    return
  }

  pageStatus.value = 'loading'
  errorMessage.value = ''
  try {
    const answerCard = await fetchAnswerCard(recordId.value)
    const nextQuestionIndex = [...answerCard.detail]
      .sort((left, right) => left.sortNo - right.sortNo)
      .findIndex((detail) => !detail.isCompleted)
    if (nextQuestionIndex < 0) {
      pageStatus.value = 'empty'
      errorMessage.value = '当前批次没有待完成题目。'
      return
    }
    await loadQuestion(nextQuestionIndex)
  } catch (error) {
    pageStatus.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : '答题进度加载失败'
  }
}

const reloadQuestion = () => {
  void loadQuestion(currentIndex.value)
}

const isMultipleChoice = computed(() => displayQuestion.value?.type === '多选题')
const isTextQuestion = computed(() => displayQuestion.value?.type === '文本题')
const showAnswerExplanation = computed(() => mode.value !== 'chapter-test' && !isTimedExam.value)
const correctAnswerLabel = computed(() => {
  const result = answerResult.value
  if (!result || result.correct || isTextQuestion.value) {
    return ''
  }

  const optionIds = (result.correctOptionIds?.length ? result.correctOptionIds : [result.correctOptionId])
    .flatMap((optionId) => optionId.split(',').map((item) => item.trim()).filter(Boolean))
  const options = displayQuestion.value?.options || []
  const labels = optionIds
    .map((optionId) => options.find((option) => option.id === optionId || option.label === optionId)?.label || optionId)
    .filter(Boolean)

  return labels.join('、')
})
const canSubmitAnswer = computed(() => {
  if (isTextQuestion.value) {
    return Boolean(textAnswer.value.trim())
  }
  return Boolean(selectedOptionIds.value.length)
})

const selectOption = async (optionId: string) => {
  if (answerResult.value || answerBusy.value) {
    return
  }
  if (!isMultipleChoice.value) {
    selectedOptionIds.value = [optionId]
    autoSubmitting.value = true
    await nextTick()
    void submitAnswer().finally(() => {
      autoSubmitting.value = false
    })
    return
  }
  if (selectedOptionIds.value.includes(optionId)) {
    selectedOptionIds.value = selectedOptionIds.value.filter((item) => item !== optionId)
    return
  }
  selectedOptionIds.value = [...selectedOptionIds.value, optionId]
}

const isWrongSelected = (optionId: string) => {
  const result = answerResult.value
  if (!result) {
    return false
  }
  return result.selectedOptionIds.includes(optionId)
    && !result.correctOptionIds.includes(optionId)
}

const optionClass = (optionId: string) => {
  const result = answerResult.value
  return {
    'question-options__item--selected': selectedOptionIds.value.includes(optionId) && !result,
    'question-options__item--correct':
      result ? result.correctOptionIds.includes(optionId) : false,
    'question-options__item--wrong': isWrongSelected(optionId)
  }
}

const goPrevious = async () => {
  if (currentIndex.value <= 0 || answerBusy.value) {
    return
  }
  await loadQuestion(currentIndex.value - 1)
}

const goBack = () => {
  if (returnPage.value) {
    uni.reLaunch({ url: returnPage.value })
    return
  }
  const fallbackQuery =
    `?catalogBatchId=${encodeURIComponent(catalogBatchId.value)}` +
    `&recordId=${encodeURIComponent(recordId.value)}` +
    `&sessionId=${encodeURIComponent(sessionId.value)}` +
    `&mode=${encodeURIComponent(mode.value)}` +
    `&topicId=${encodeURIComponent(topicId.value)}` +
    `&topicTitle=${encodeURIComponent(topicTitle.value)}`
  uni.navigateBack({
    delta: 1,
    fail: () => {
      uni.reLaunch({
        url: `/pages/practice/exam-assessment${fallbackQuery}`
      })
    }
  })
}

const submitAnswer = async () => {
  const question = currentQuestion.value
  if (!questionPage.value || !question || !canSubmitAnswer.value || submitting.value) {
    return
  }

  const answerIds = isTextQuestion.value ? [textAnswer.value.trim()] : selectedOptionIds.value
  submitting.value = true
  answeredQuestionSnapshot.value = cloneQuestion(question)
  try {
    answerResult.value = await submitPracticeAnswer(
      practiceId.value,
      sessionId.value,
      question.id,
      answerIds,
      currentIndex.value
    )
    questionPage.value = {
      ...questionPage.value,
      currentIndex: currentIndex.value,
      answeredCount: answerResult.value.answeredCount,
      correctCount: answerResult.value.correctCount,
      progressPercent: answerResult.value.progressPercent,
      totalQuestions: answerResult.value.totalQuestions
    }
    upsertRecordedAnswer(answerResult.value, question)
    nextTick(() => {
      answerScrollTop.value += 1
    })
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '答案提交失败',
      icon: 'none'
    })
  } finally {
    submitting.value = false
  }
}

const upsertRecordedAnswer = (result: PracticeAnswerResult, question: PracticeQuestion) => {
  const cachedAnswer: PracticeRecordAnswer = {
    no: currentIndex.value + 1,
    questionId: result.questionId,
    type: question.type,
    question: question.stem,
    selectedOptionIds: [...(result.selectedOptionIds || [])],
    answer: isTextQuestion.value ? textAnswer.value.trim() : (result.selectedOptionIds || []).join(','),
    correctOptionIds: [...(result.correctOptionIds || [])],
    correct: (result.correctOptionIds || []).join(','),
    correctFlag: Boolean(result.correct),
    explanation: result.explanation || '暂无标准解析。',
    stepName: question.stepName,
    stepStatus: question.stepStatus
  }

  const index = recordAnswers.value.findIndex((item) => item.questionId === result.questionId)
  if (index >= 0) {
    recordAnswers.value.splice(index, 1, cachedAnswer)
    return
  }
  recordAnswers.value.push(cachedAnswer)
}

const goNext = async () => {
  if (!answerResult.value) {
    return
  }
  if (answerResult.value.completed) {
    const targetRecordId = answerResult.value.recordId || recordId.value
    uni.reLaunch({ url: buildRecordDetailUrl(targetRecordId) })
    return
  }
  const nextIndex = answerResult.value.nextQuestionIndex
  selectedOptionIds.value = []
  textAnswer.value = ''
  answerResult.value = null
  answeredQuestionSnapshot.value = null
  answerScrollTop.value = 0
  currentIndex.value = nextIndex
  await loadQuestion(nextIndex)
}

const openAiAnswer = () => {
  if (!answerResult.value || !questionPage.value) {
    return
  }
  uni.setStorageSync(`aiAnswerQuestion:${answerResult.value.questionId}`, {
    question: displayQuestion.value || currentQuestion.value,
    selectedOptionId: answerResult.value.selectedOptionId,
    correctOptionId: answerResult.value.correctOptionId
  })
  uni.navigateTo({
    url:
      `/pages/practice/ai-answer?id=${encodeURIComponent(practiceId.value)}` +
      `&sessionId=${encodeURIComponent(sessionId.value)}` +
      `&mode=${mode.value}` +
      `&recordId=${encodeURIComponent(recordId.value)}` +
      `&catalogBatchId=${encodeURIComponent(catalogBatchId.value)}` +
      `&questionId=${encodeURIComponent(answerResult.value.questionId)}` +
      `&selectedOptionId=${encodeURIComponent(answerResult.value.selectedOptionId)}`
  })
}

onLoad((query) => {
  if (!requireLogin()) {
    return
  }
  practiceId.value = readQueryValue(query?.id)
  sessionId.value = readQueryValue(query?.sessionId)
  recordId.value = readQueryValue(query?.recordId)
  catalogBatchId.value = readQueryValue(query?.catalogBatchId)
  topicId.value = readQueryValue(query?.topicId)
  topicTitle.value = readQueryValue(query?.topicTitle)
  returnPage.value = readQueryValue(query?.returnPage)
  mode.value = readMode(readQueryValue(query?.mode))
  pendingSubmit.value = readBooleanValue(query?.pendingSubmit)
  const resumeIndex = Number(readQueryValue(query?.resumeQuestionIndex))
  resumeQuestionIndex.value = Number.isFinite(resumeIndex) ? Math.max(Math.floor(resumeIndex), 0) : null
  const remaining = Number(readQueryValue(query?.remainingSeconds))
  remainingSeconds.value = Number.isFinite(remaining) ? Math.max(Math.floor(remaining), 0) : 0
  startExamTimer()

  void loadInitialQuestion()
})

onUnload(stopExamTimer)
</script>

<style lang="scss" src="./answer-reference.scss"></style>
<style scoped>
.question-video { margin-top: 24rpx; }
.question-video__button { display: flex; align-items: center; justify-content: center; gap: 12rpx; min-height: 88rpx; padding: 16rpx 24rpx; border-radius: 8rpx; background: #edf7f3; color: #176c5c; font-size: 28rpx; line-height: 1.5; }
.question-video__button[disabled] { opacity: 0.55; }
.question-video__empty { font-size: 24rpx; color: #68736f; }
.question-video-modal { position: fixed; z-index: 1000; inset: 0; box-sizing: border-box; padding: calc(var(--app-safe-area-top) + 28rpx) 32rpx calc(env(safe-area-inset-bottom) + 28rpx); display: flex; align-items: center; justify-content: center; background: rgba(17, 24, 29, 0.72); }
.question-video-modal__panel { box-sizing: border-box; width: 100%; max-width: 900rpx; overflow: hidden; border-radius: 16rpx; background: #f8fbff; box-shadow: 0 18rpx 60rpx rgba(0, 0, 0, 0.24); }
.question-video-modal__head { box-sizing: border-box; height: 88rpx; padding: 0 14rpx 0 28rpx; display: flex; align-items: center; justify-content: space-between; }
.question-video-modal__title { color: #171b1e; font-size: 30rpx; line-height: 1.4; font-weight: 600; }
.question-video-modal__close { width: 64rpx; height: 64rpx; margin: 0; padding: 0; display: flex; align-items: center; justify-content: center; border: 0; border-radius: 50%; background: transparent; line-height: 64rpx; }
.question-video-modal__close::after { border: 0; }
.question-video-modal__frame { box-sizing: border-box; width: 100%; height: 386rpx; overflow: hidden; background: #000; }
.question-video-modal__player { display: block; width: 100%; height: 100%; background: #000; }
</style>
