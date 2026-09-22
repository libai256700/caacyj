<template>
  <view class="ai-page" :style="$appSafeAreaStyle">
    <view class="ai-page__bg"></view>
    <view class="ai-page__content">
      <view class="ai-hero">
        <button class="ai-hero__back" aria-label="返回" @tap="backToAnswer">
          <uv-icon name="arrow-left" color="#071D3D" size="44rpx" />
        </button>
        <view class="ai-hero__title-wrap">
          <text class="ai-hero__title">AI 深度解答</text>
        </view>
        <view class="ai-hero__drone" aria-hidden="true">
          <view class="ai-hero__drone-body"></view>
          <view class="ai-hero__drone-line ai-hero__drone-line--one"></view>
          <view class="ai-hero__drone-line ai-hero__drone-line--two"></view>
        </view>
      </view>

      <SelfTestLoadingOverlay
        :show="!displayQuestion && pageStatus === 'loading'"
        :title="stateTitle"
        :message="stateMessage"
      />

      <AppStateView
        v-if="!displayQuestion && pageStatus !== 'ready' && pageStatus !== 'loading'"
        :status="pageStatus"
        :title="stateTitle"
        :message="stateMessage"
        action-text="重新加载"
        @retry="loadAiAnswer"
      />

      <view v-else-if="displayQuestion" class="ai-answer">
        <scroll-view class="ai-answer__scroll" scroll-y scroll-with-animation :scroll-top="aiScrollTop">
          <view class="wrong-review">
            <view class="wrong-review__header">
              <view class="section-heading">
                <view class="section-heading__mark"></view>
                <text class="wrong-review__title">错题回顾</text>
              </view>
              <button
                class="wrong-review__toggle"
                :aria-label="questionCollapsed ? '展开题目' : '收起题目'"
                @tap="questionCollapsed = !questionCollapsed"
              >
                <uv-icon
                  :name="questionCollapsed ? 'arrow-down' : 'arrow-up'"
                  color="#8EA4BA"
                  size="28rpx"
                />
              </button>
            </view>

            <view v-if="!questionCollapsed" class="wrong-review__body">
              <view class="wrong-review__tag">
                <text>{{ questionTypeLabel }}</text>
                <text class="wrong-review__tag-dot">·</text>
                <text>{{ questionLevelLabel }}</text>
              </view>
              <text class="question-card__stem">{{ questionIndexLabel }}{{ displayQuestion.stem || displayQuestion.title }}</text>
              <view class="wrong-review__divider"></view>
              <view class="answer-summary">
                <view class="answer-summary__row answer-summary__row--wrong">
                  <view class="answer-summary__icon">
                    <uv-icon name="close" color="#FFFFFF" size="28rpx" />
                  </view>
                  <text class="answer-summary__text">
                    <text class="answer-summary__label">你的选择：</text>
                    {{ selectedOptionLabel }}
                  </text>
                </view>
                <view class="answer-summary__row answer-summary__row--correct">
                  <view class="answer-summary__icon">
                    <uv-icon name="checkmark" color="#FFFFFF" size="28rpx" />
                  </view>
                  <text class="answer-summary__text">
                    <text class="answer-summary__label">正确答案：</text>
                    {{ correctOptionLabel }}
                  </text>
                </view>
              </view>
            </view>
          </view>

          <view class="ai-result">
            <view class="ai-result__header">
              <view class="section-heading">
                <view class="section-heading__mark"></view>
                <text class="ai-result__brand">AI 深度解答</text>
              </view>
              <text class="ai-result__source">AI 基于知识点为你深度解析这道错题</text>
            </view>

            <view class="ai-stream">
              <SelfTestLoadingOverlay
                v-if="pageStatus === 'loading' && !aiStreamContent"
                :show="true"
                :title="stateTitle"
                :message="stateMessage"
              />
              <AppStateView
                v-else-if="pageStatus === 'error' && !aiStreamContent"
                class="ai-state-view"
                :status="pageStatus"
                :title="stateTitle"
                :message="stateMessage"
                action-text="重新加载"
                @retry="loadAiAnswer"
              />
              <template v-else>
                <view v-if="aiSectionItems.length" class="ai-section-list">
                  <view v-for="(section, index) in aiSectionItems" :key="`${section.title}-${index}`" class="ai-section">
                    <view v-if="section.title !== '知识库解答'" class="ai-section__heading">
                      <view class="section-heading__mark"></view>
                      <text class="ai-section__title">{{ section.title }}</text>
                    </view>
                    <view class="ai-presentation">
                      <template
                        v-for="(block, blockIndex) in section.blocks"
                        :key="`${block.type}-${blockIndex}`"
                      >
                        <text v-if="block.type === 'heading'" class="ai-presentation__heading">
                          {{ block.text }}
                        </text>
                        <view v-else-if="block.type === 'bullets'" class="ai-presentation__bullets">
                          <view
                            v-for="(item, itemIndex) in block.items"
                            :key="`${item}-${itemIndex}`"
                            class="ai-presentation__bullet"
                          >
                            <text class="ai-presentation__bullet-mark">•</text>
                            <text class="ai-presentation__bullet-text">{{ item }}</text>
                          </view>
                        </view>
                        <text v-else class="ai-presentation__paragraph">{{ block.text }}</text>
                      </template>
                    </view>
                  </view>
                </view>
                <text v-else class="ai-stream__paragraph">{{ aiStreamText }}</text>
              </template>
            </view>
          </view>

          <view class="follow-panel">
            <view class="follow-panel__header">
              <view class="follow-panel__title">
                <view class="section-heading__mark"></view>
                <text>继续追问（当前题目）</text>
              </view>
            </view>

            <view v-if="latestFollowUp" class="follow-stream">
              <view class="follow-stream__user">
                <text class="follow-stream__question">{{ latestFollowUp.prompt }}</text>
                <text class="follow-stream__time">{{ followUpTimeLabel }}</text>
              </view>
              <view v-if="latestFollowUp.answer" class="follow-stream__assistant">
                <view class="robot-face robot-face--small"></view>
                <view class="follow-stream__assistant-body">
                  <text class="follow-stream__answer">{{ latestFollowUp.answer }}</text>
                </view>
                <text class="follow-stream__time follow-stream__time--assistant">{{ followUpTimeLabel }}</text>
              </view>
            </view>

            <view class="follow-input">
              <input
                v-model="followUpPrompt"
                class="follow-input__control"
                type="text"
                maxlength="200"
                placeholder="继续追问当前错题（支持文字提问）"
                placeholder-class="follow-input__placeholder"
                confirm-type="send"
                @confirm="sendFollowUp"
              />
              <text class="follow-input__count">{{ followUpPrompt.length }}/200</text>
              <button class="follow-input__send" :loading="submittingFollowUp" :disabled="!canSendFollowUp" @tap="sendFollowUp">
                <uv-icon name="share-fill" color="#FFFFFF" size="38rpx" />
              </button>
            </view>
          </view>

          <text class="ai-disclaimer">AI 生成内容仅供参考，请结合教材与规范理解。若内容存在疑问，请以官方规范为准。</text>
        </scroll-view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import AppStateView from '@/components/AppStateView.vue'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import {
  fetchAiAnswer,
  queryKnowledge,
  submitAiFollowUp,
  streamAiAnswer,
  streamAiFollowUp,
  type AiAnswer,
  type AiFollowUp,
  type AiAnswerStreamEvent,
  type AiFollowUpStreamEvent,
  type PracticeQuestion,
  type PracticeStartMode
} from '@/services/practice'
import { type AppAsyncStatus, requireLogin } from '@/stores/appState'

const practiceId = ref('')
const sessionId = ref('')
const mode = ref<PracticeStartMode>('standard')
const questionId = ref('')
const selectedOptionId = ref('')
const pageStatus = ref<AppAsyncStatus>('loading')
const errorMessage = ref('')
const aiAnswer = ref<AiAnswer | null>(null)
const aiStreamContent = ref('')
const cachedQuestion = ref<PracticeQuestion | null>(null)
const cachedCorrectOptionId = ref('')
const followUpPrompt = ref('')
const followUps = ref<AiFollowUp[]>([])
const submittingFollowUp = ref(false)
const questionCollapsed = ref(false)
const aiAbortController = ref<AbortController | null>(null)
const followUpAbortController = ref<AbortController | null>(null)
const aiStreamQueue = ref<string[]>([])
const aiTypingTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const aiStreamCompleted = ref(false)
const forceStreamDisplay = ref(false)
const followUpDraft = ref<AiFollowUp | null>(null)
const followUpQueue = ref<string[]>([])
const followUpTypingTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const followUpStreamCompleted = ref(false)
const aiScrollTop = ref(0)
const scrollPending = ref(false)

const TYPEWRITER_DELAY_MS = 20

type CachedAiAnswerQuestion = {
  question?: PracticeQuestion
  selectedOptionId?: string
  correctOptionId?: string
}

type AiPresentationBlock = {
  type: 'paragraph' | 'heading' | 'bullets'
  text: string
  items: string[]
}

const parseAiPresentationBlocks = (content: string): AiPresentationBlock[] => {
  const blocks: AiPresentationBlock[] = []
  const paragraphLines: string[] = []
  const bulletItems: string[] = []
  const lines = content.split(/\r?\n/)

  const flushParagraph = () => {
    if (!paragraphLines.length) {
      return
    }
    blocks.push({
      type: 'paragraph',
      text: paragraphLines.join('\n'),
      items: []
    })
    paragraphLines.length = 0
  }

  const flushBullets = () => {
    if (!bulletItems.length) {
      return
    }
    blocks.push({
      type: 'bullets',
      text: '',
      items: [...bulletItems]
    })
    bulletItems.length = 0
  }

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim()
    if (!line) {
      flushParagraph()
      flushBullets()
      return
    }

    const bulletMatch = line.match(/^[-•·*]\s*(.+)$/)
    if (bulletMatch) {
      flushParagraph()
      bulletItems.push(bulletMatch[1].trim())
      return
    }

    flushBullets()
    const nextLine = lines[index + 1]?.trim() || ''
    if (/^[-•·*]\s*\S/.test(nextLine)) {
      flushParagraph()
      blocks.push({
        type: 'heading',
        text: line,
        items: []
      })
      return
    }

    paragraphLines.push(line)
  })

  flushParagraph()
  flushBullets()
  return blocks
}

const displayQuestion = computed(() => aiAnswer.value?.question || cachedQuestion.value)
const displaySelectedOptionId = computed(() => aiAnswer.value?.selectedOptionId || selectedOptionId.value)
const displayCorrectOptionId = computed(() => aiAnswer.value?.correctOptionId || cachedCorrectOptionId.value)
const questionTypeLabel = computed(() => displayQuestion.value?.type || '单选题')
const questionLevelLabel = computed(() => {
  const score = Number(displayQuestion.value?.score || 0)
  if (score >= 3) {
    return '较难'
  }
  if (score >= 2) {
    return '中等'
  }
  return '基础'
})
const questionIndexLabel = computed(() => {
  const numericId = Number(displayQuestion.value?.id)
  if (Number.isFinite(numericId) && numericId > 0 && numericId < 1000) {
    return `${numericId}. `
  }
  return ''
})
const aiSectionItems = computed(() => {
  const sections = aiAnswer.value?.sections || []
  if (!sections.length || (forceStreamDisplay.value && (!aiStreamCompleted.value || aiStreamQueue.value.length > 0))) {
    return []
  }
  return sections
    .map((section) => {
      const content = section.content?.trim() || ''
      return {
        title: normalizeSectionTitle(section.title),
        content,
        blocks: parseAiPresentationBlocks(content)
      }
    })
    .filter((section) => section.content)
})

const aiStreamText = computed(() => {
  if (forceStreamDisplay.value) {
    return aiStreamContent.value
  }
  if (aiStreamContent.value.trim()) {
    return aiStreamContent.value
  }
  if (!aiAnswer.value?.sections?.length) {
    return 'AI 暂未生成有效解答，请稍后重试，或返回答题页重新进入 AI 深度解答。'
  }
  return aiAnswer.value.sections
    .map((section) => section.content)
    .filter((content) => Boolean(content?.trim()))
    .join('\n\n') || 'AI 暂未生成有效解答，请稍后重试。'
})

const stateTitle = computed(() => {
  if (pageStatus.value === 'loading') {
    return '正在思考'
  }
  if (pageStatus.value === 'empty') {
    return '缺少错题上下文'
  }
  return 'AI 解答加载失败'
})

const stateMessage = computed(() => {
  if (errorMessage.value) {
    return errorMessage.value
  }
  if (pageStatus.value === 'loading' && displayQuestion.value) {
    return '题目已带入，AI 解答生成后会自动展示。'
  }
  return '请从答题页答错后进入，系统会自动带入当前错题。'
})

const canSendFollowUp = computed(() => Boolean(followUpPrompt.value.trim()) && !submittingFollowUp.value)
const latestFollowUp = computed(() => followUps.value[0] || null)
const followUpTimeLabel = computed(() => {
  const date = new Date()
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${hours}:${minutes}`
})
const isStreamUnsupported = (error: unknown) =>
  error instanceof Error && error.message.includes('当前环境暂不支持流式AI解答')

const sectionIconName = (index: number) => {
  const icons = ['checkmark', 'close', 'file-text', 'level', 'calendar']
  return icons[index % icons.length]
}

const selectedOptionLabel = computed(() => {
  const question = displayQuestion.value
  const selectedId = displaySelectedOptionId.value
  if (!question || !selectedId) {
    return selectedId || '未选择'
  }
  return selectedId
    .split(',')
    .map((id) => {
      const normalized = id.trim()
      const option = question.options.find((item) => item.id === normalized || item.label === normalized)
      return option ? `${option.label}. ${option.content}` : normalized
    })
    .filter(Boolean)
    .join('；') || selectedId
})

const correctOptionLabel = computed(() => {
  const question = displayQuestion.value
  const correctId = displayCorrectOptionId.value
  if (!question || !correctId) {
    return correctId || '未知'
  }
  return correctId
    .split(',')
    .map((id) => {
      const normalized = id.trim()
      const option = question.options.find((item) => item.id === normalized || item.label === normalized)
      return option ? `${option.label}. ${option.content}` : normalized
    })
    .filter(Boolean)
    .join('；') || correctId
})

const normalizeSectionTitle = (title: string) => {
  const normalized = title?.trim()
  if (normalized) {
    return normalized.replace(/^\d+[.、]\s*/, '')
  }
  return '知识点解析'
}

const shouldUseAiStream = () => {
  // #ifdef APP-PLUS
  return false
  // #endif
  return true
}

const optionClass = (optionId: string) => {
  return {
    'question-option--selected': optionId === displaySelectedOptionId.value,
    'question-option--correct': optionId === displayCorrectOptionId.value
  }
}

const buildKnowledgeQuery = (prompt = '') => {
  const question = displayQuestion.value
  const parts: string[] = []
  if (prompt.trim()) {
    parts.push(prompt.trim())
  }
  if (question) {
    parts.push(`题干：${question.stem || question.title}`)
    if (question.options?.length) {
      parts.push(`选项：${question.options.map((option) => `${option.label}. ${option.content}`).join('；')}`)
    }
  }
  parts.push(`我的答案：${selectedOptionLabel.value}`)
  parts.push(`正确答案：${correctOptionLabel.value}`)
  return parts.filter(Boolean).join('\n')
}

const buildKnowledgeAiAnswer = (content: string, references: { source: string; content: string }[]): AiAnswer => {
  const question = displayQuestion.value
  if (!question) {
    throw new Error('题目上下文缺失，无法生成知识库解答')
  }
  return {
    practiceId: practiceId.value,
    sessionId: sessionId.value,
    mode: mode.value,
    question,
    selectedOptionId: displaySelectedOptionId.value,
    correctOptionId: displayCorrectOptionId.value,
    standardExplanation: '',
    sections: [
      {
        title: '知识库解答',
        content
      }
    ],
    references
  }
}

const clearTypingTimer = (timer: typeof aiTypingTimer | typeof followUpTypingTimer) => {
  if (!timer.value) {
    return
  }
  clearTimeout(timer.value)
  timer.value = null
}

const syncFollowUpDraft = () => {
  if (!followUpDraft.value) {
    return
  }
  followUps.value = [{ ...followUpDraft.value }]
  requestScrollToBottom()
}

const startFollowUpDraft = (prompt: string) => {
  followUpDraft.value = {
    questionId: questionId.value,
    prompt,
    answer: '',
    references: aiAnswer.value?.references || []
  }
  syncFollowUpDraft()
}

const flushAiReadyState = () => {
  if (aiStreamQueue.value.length > 0) {
    return
  }
  if (pageStatus.value === 'loading') {
    pageStatus.value = aiAnswer.value || aiStreamContent.value.trim() ? 'ready' : 'empty'
  }
}

const requestScrollToBottom = () => {
  if (scrollPending.value) {
    return
  }
  scrollPending.value = true
  nextTick(() => {
    aiScrollTop.value += 10000
    scrollPending.value = false
  })
}

const drainAiStreamQueue = () => {
  if (aiTypingTimer.value || aiStreamQueue.value.length === 0) {
    if (aiStreamQueue.value.length === 0 && aiStreamCompleted.value) {
      flushAiReadyState()
    }
    return
  }

  const step = () => {
    const nextChar = aiStreamQueue.value.shift()
    if (nextChar) {
      aiStreamContent.value += nextChar
      requestScrollToBottom()
      if (pageStatus.value === 'loading' && aiStreamContent.value.trim()) {
        pageStatus.value = 'ready'
      }
    }

    if (aiStreamQueue.value.length > 0) {
      aiTypingTimer.value = setTimeout(step, TYPEWRITER_DELAY_MS)
      return
    }

    aiTypingTimer.value = null
    if (aiStreamCompleted.value) {
      flushAiReadyState()
    }
  }

  aiTypingTimer.value = setTimeout(step, TYPEWRITER_DELAY_MS)
}

const enqueueAiContent = (content: string) => {
  if (!content) {
    return
  }
  forceStreamDisplay.value = true
  aiStreamQueue.value.push(...Array.from(content))
  drainAiStreamQueue()
}

const drainFollowUpQueue = () => {
  if (followUpTypingTimer.value || followUpQueue.value.length === 0 || !followUpDraft.value) {
    if (followUpQueue.value.length === 0 && followUpStreamCompleted.value) {
      syncFollowUpDraft()
    }
    return
  }

  const step = () => {
    const nextChar = followUpQueue.value.shift()
    if (nextChar && followUpDraft.value) {
      followUpDraft.value.answer += nextChar
      syncFollowUpDraft()
      requestScrollToBottom()
    }

    if (followUpQueue.value.length > 0) {
      followUpTypingTimer.value = setTimeout(step, TYPEWRITER_DELAY_MS)
      return
    }

    followUpTypingTimer.value = null
    if (followUpStreamCompleted.value) {
      syncFollowUpDraft()
    }
  }

  followUpTypingTimer.value = setTimeout(step, TYPEWRITER_DELAY_MS)
}

const enqueueFollowUpContent = (content: string) => {
  if (!content) {
    return
  }
  followUpQueue.value.push(...Array.from(content))
  drainFollowUpQueue()
}

const resetAiTypingState = () => {
  clearTypingTimer(aiTypingTimer)
  aiStreamQueue.value = []
  aiStreamCompleted.value = false
  aiStreamContent.value = ''
  forceStreamDisplay.value = false
}

const resetFollowUpTypingState = () => {
  clearTypingTimer(followUpTypingTimer)
  followUpQueue.value = []
  followUpStreamCompleted.value = false
  followUpDraft.value = null
}

const handleAiStreamEvent = (event: AiAnswerStreamEvent) => {
  if (event.type === 'context') {
    aiAnswer.value = event.answer
    forceStreamDisplay.value = true
    return
  }

  if (event.type === 'references') {
    if (aiAnswer.value) {
      aiAnswer.value = {
        ...aiAnswer.value,
        references: event.references || []
      }
    }
    return
  }

  if (event.type === 'delta') {
    enqueueAiContent(event.content)
    return
  }

  if (event.type === 'done') {
    aiStreamCompleted.value = true
    if (aiStreamQueue.value.length === 0) {
      flushAiReadyState()
    }
    return
  }

  errorMessage.value = event.message
  pageStatus.value = 'error'
}

const handleFollowUpStreamEvent = (prompt: string) => {
  return (event: AiFollowUpStreamEvent) => {
    if (event.type === 'references') {
      if (!followUpDraft.value) {
        startFollowUpDraft(prompt)
      }
      if (followUpDraft.value) {
        followUpDraft.value = {
          ...followUpDraft.value,
          prompt,
          references: event.references || []
        }
        syncFollowUpDraft()
      }
      return
    }

    if (event.type === 'delta') {
      enqueueFollowUpContent(event.content)
      return
    }

    if (event.type === 'done') {
      followUpStreamCompleted.value = true
      if (followUpQueue.value.length === 0) {
        syncFollowUpDraft()
      }
      return
    }

    throw new Error(event.message)
  }
}

const loadAiAnswerFallback = async () => {
  const result = await fetchAiAnswer(practiceId.value, sessionId.value, mode.value, questionId.value, selectedOptionId.value)
  aiAnswer.value = result
  const content = result.sections
    .map((section) => section.content)
    .filter((section) => Boolean(section?.trim()))
    .join('\n\n')
  forceStreamDisplay.value = true
  aiStreamCompleted.value = true
  enqueueAiContent(content)
  if (!content.trim()) {
    pageStatus.value = aiAnswer.value ? 'ready' : 'empty'
  }
}

const sendFollowUpFallback = async (prompt: string) => {
  const result = await submitAiFollowUp(practiceId.value, sessionId.value, questionId.value, selectedOptionId.value, prompt)
  if (!followUpDraft.value) {
    startFollowUpDraft(result.prompt)
  } else {
    followUpDraft.value = {
      ...followUpDraft.value,
      questionId: result.questionId,
      prompt: result.prompt,
      references: result.references?.length ? result.references : (aiAnswer.value?.references || [])
    }
    syncFollowUpDraft()
  }
  followUpStreamCompleted.value = true
  enqueueFollowUpContent(result.answer)
  if (!result.answer.trim()) {
    syncFollowUpDraft()
  }
}

const loadAiAnswer = async () => {
  if (!questionId.value) {
    pageStatus.value = 'empty'
    errorMessage.value = '题目参数缺失，无法生成当前错题解答。'
    return
  }
  if (!displayQuestion.value) {
    pageStatus.value = 'empty'
    errorMessage.value = '题目上下文缺失，无法查询知识库。'
    return
  }

  aiAbortController.value?.abort()
  pageStatus.value = 'loading'
  errorMessage.value = ''
  resetAiTypingState()
  aiAnswer.value = null
  try {
    const result = await queryKnowledge(buildKnowledgeQuery(), 'practice_ai_answer')
    aiAnswer.value = buildKnowledgeAiAnswer(result.answer, result.references)
    forceStreamDisplay.value = true
    aiStreamCompleted.value = true
    enqueueAiContent(result.answer)
    if (!result.answer.trim()) {
      pageStatus.value = 'empty'
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '知识库解答加载失败'
    pageStatus.value = 'error'
  } finally {
    aiAbortController.value = null
  }
}

const sendFollowUp = async () => {
  if (!displayQuestion.value || !canSendFollowUp.value) {
    return
  }

  const prompt = followUpPrompt.value.trim()
  followUpPrompt.value = ''
  submittingFollowUp.value = true
  followUpAbortController.value?.abort()
  followUpAbortController.value = typeof AbortController !== 'undefined' ? new AbortController() : null
  resetFollowUpTypingState()
  startFollowUpDraft(prompt)
  try {
    const result = await queryKnowledge(buildKnowledgeQuery(prompt), 'practice_ai_answer')
    if (followUpDraft.value) {
      followUpDraft.value = {
        ...followUpDraft.value,
        questionId: questionId.value,
        prompt,
        references: result.references?.length ? result.references : (aiAnswer.value?.references || [])
      }
      syncFollowUpDraft()
    }
    followUpStreamCompleted.value = true
    enqueueFollowUpContent(result.answer)
    if (!result.answer.trim()) {
      syncFollowUpDraft()
    }
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '追问失败',
      icon: 'none'
    })
  } finally {
    submittingFollowUp.value = false
    followUpAbortController.value = null
  }
}

const backToAnswer = () => {
  uni.navigateBack()
}

const loadCachedQuestion = () => {
  if (!questionId.value) {
    return
  }
  const cached = uni.getStorageSync(`aiAnswerQuestion:${questionId.value}`) as CachedAiAnswerQuestion | ''
  if (!cached || !cached.question) {
    return
  }
  cachedQuestion.value = cached.question
  selectedOptionId.value = cached.selectedOptionId || selectedOptionId.value
  cachedCorrectOptionId.value = cached.correctOptionId || ''
}

onLoad((query) => {
  if (!requireLogin()) {
    return
  }
  practiceId.value = typeof query?.id === 'string' ? query.id : ''
  sessionId.value = typeof query?.sessionId === 'string' ? query.sessionId : ''
  mode.value = query?.mode === 'wrongReview' ? 'wrongReview' : 'standard'
  questionId.value = typeof query?.questionId === 'string' ? query.questionId : ''
  selectedOptionId.value = typeof query?.selectedOptionId === 'string' ? query.selectedOptionId : ''
  loadCachedQuestion()
  loadAiAnswer()
})

onUnload(() => {
  aiAbortController.value?.abort()
  followUpAbortController.value?.abort()
  clearTypingTimer(aiTypingTimer)
  clearTypingTimer(followUpTypingTimer)
})
</script>

<style lang="scss">
page {
  background: #edf7ff;
  height: 100vh;
  overflow: hidden;
}

.ai-page {
  position: fixed;
  inset: 0;
  overflow: hidden;
  color: #10284a;
  background: #edf7ff;
}

.ai-page__bg {
  position: fixed;
  inset: 0;
  background:
    radial-gradient(circle at 82% 2%, rgba(182, 222, 255, 0.86) 0, rgba(182, 222, 255, 0) 28%),
    radial-gradient(circle at 8% 32%, rgba(221, 241, 255, 0.82) 0, rgba(221, 241, 255, 0) 24%),
    linear-gradient(180deg, #e6f5ff 0%, #f8fcff 45%, #eaf7ff 100%);
}

.ai-page__bg::before,
.ai-page__bg::after {
  content: "";
  position: absolute;
  pointer-events: none;
}

.ai-page__bg::before {
  top: 66rpx;
  right: 42rpx;
  width: 220rpx;
  height: 86rpx;
  opacity: 0.24;
  background:
    linear-gradient(90deg, transparent 0 18%, rgba(111, 180, 239, 0.38) 18% 20%, transparent 20% 100%),
    linear-gradient(0deg, transparent 0 47%, rgba(111, 180, 239, 0.38) 47% 50%, transparent 50% 100%),
    radial-gradient(circle at 15% 50%, rgba(111, 180, 239, 0.48) 0 7rpx, transparent 8rpx),
    radial-gradient(circle at 85% 50%, rgba(111, 180, 239, 0.48) 0 7rpx, transparent 8rpx);
}

.ai-page__bg::after {
  left: 0;
  right: 0;
  top: 430rpx;
  height: 720rpx;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.76), rgba(255, 255, 255, 0));
}

.ai-page__content {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  height: 100%;
  padding: calc(var(--app-safe-area-top) + 34rpx) 30rpx 28rpx;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ai-hero {
  position: relative;
  min-height: 160rpx;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 0;
  flex: 0 0 auto;
}

.ai-hero__back {
  position: absolute;
  left: -2rpx;
  top: 2rpx;
  width: 64rpx;
  height: 64rpx;
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: transparent;
  line-height: 1;
}

.ai-hero__back::after,
.follow-input__send::after {
  border: 0;
}

.ai-hero__title-wrap {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 18rpx;
  text-align: center;
}

.ai-hero__title,
.ai-hero__subtitle,
.wrong-review__title,
.wrong-review__hint,
.wrong-review__source,
.question-card__label,
.question-card__stem,
.question-option__content,
.question-option__mark,
.ai-result__brand,
.ai-result__source,
.ai-stream__paragraph,
.ai-section__title,
.ai-section__content,
.ai-reference__title,
.ai-reference__hint,
.follow-panel__title,
.follow-stream__question,
.follow-stream__answer,
.follow-stream__time,
.ai-disclaimer {
  display: block;
}

.ai-hero__title {
  font-size: 42rpx;
  line-height: 1.15;
  font-weight: 900;
  color: #071d3d;
}

.ai-hero__subtitle {
  margin-top: 16rpx;
  font-size: 26rpx;
  line-height: 1.3;
  color: #637b99;
  font-weight: 520;
}

.ai-hero__spark {
  position: relative;
  width: 28rpx;
  height: 28rpx;
  margin-top: 8rpx;
}

.ai-hero__spark::before,
.ai-hero__spark::after {
  content: "";
  position: absolute;
  inset: 0;
  margin: auto;
  border-radius: 6rpx;
  background: #54a9ff;
}

.ai-hero__spark::before {
  width: 10rpx;
  height: 28rpx;
}

.ai-hero__spark::after {
  width: 28rpx;
  height: 10rpx;
}

.ai-hero__spark--right {
  width: 36rpx;
  height: 44rpx;
  margin-top: 0;
}

.ai-hero__spark--right::before {
  left: 14rpx;
  top: 0;
  width: 8rpx;
  height: 8rpx;
  border-radius: 50%;
}

.ai-hero__spark--right::after {
  left: 2rpx;
  top: 30rpx;
  width: 8rpx;
  height: 8rpx;
  border-radius: 50%;
}

.ai-hero__drone {
  position: absolute;
  right: 20rpx;
  top: 8rpx;
  width: 146rpx;
  height: 72rpx;
  opacity: 0.18;
}

.ai-hero__drone-body {
  position: absolute;
  left: 58rpx;
  top: 28rpx;
  width: 32rpx;
  height: 18rpx;
  border: 4rpx solid #7db9ee;
  border-radius: 50%;
}

.ai-hero__drone-line {
  position: absolute;
  left: 16rpx;
  right: 16rpx;
  top: 33rpx;
  height: 4rpx;
  border-radius: 999rpx;
  background: #7db9ee;
}

.ai-hero__drone-line--two {
  left: 70rpx;
  top: 8rpx;
  width: 4rpx;
  height: 60rpx;
}

.ai-answer {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ai-answer__scroll {
  flex: 1;
  min-height: 0;
  height: 0;
  box-sizing: border-box;
}

.wrong-review,
.ai-result,
.follow-panel {
  box-sizing: border-box;
  border-radius: 16rpx;
  background: rgba(255, 255, 255, 0.9);
  border: 1rpx solid rgba(226, 239, 250, 0.86);
  box-shadow: 0 18rpx 54rpx rgba(64, 108, 150, 0.11);
}

.wrong-review {
  flex: 0 0 auto;
  padding: 28rpx 30rpx 30rpx;
}

.wrong-review__header,
.wrong-review__toggle,
.question-option,
.question-option__mark,
.ai-result__header,
.ai-result__brand,
.follow-panel__header,
.follow-panel__title,
.follow-panel__title-icon,
.follow-stream__assistant,
.follow-input,
.follow-input__send {
  display: flex;
  align-items: center;
}

.wrong-review__header {
  justify-content: space-between;
  gap: 20rpx;
  margin-bottom: 28rpx;
}

.wrong-review__status {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 18rpx;
  flex-wrap: wrap;
}

.wrong-review__title {
  font-size: 29rpx;
  line-height: 1.25;
  font-weight: 900;
  color: #092145;
}

.wrong-review__pill {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 98rpx;
  height: 48rpx;
  padding: 0 18rpx;
  border-radius: 24rpx;
  background: #fff0f0;
  color: #ff3f3f;
  font-size: 24rpx;
  line-height: 48rpx;
  font-weight: 900;
}

.wrong-review__hint {
  font-size: 25rpx;
  line-height: 1.3;
  color: #71839b;
}

.wrong-review__source {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10rpx;
  color: #697c96;
  font-size: 24rpx;
  line-height: 1.2;
  font-weight: 650;
}

.wrong-review__source-strong {
  color: #23344f;
  font-weight: 900;
}

.wrong-review__level {
  display: inline-flex;
  align-items: center;
  height: 38rpx;
  padding: 0 14rpx;
  border-radius: 19rpx;
  background: #e9f4ff;
  color: #1684e8;
  font-weight: 900;
}

.wrong-review__toggle {
  display: flex;
  align-items: center;
  height: 50rpx;
  flex: 0 0 auto;
  margin: 0;
  padding: 0 16rpx;
  justify-content: center;
  gap: 8rpx;
  border-radius: 25rpx;
  background: #eef7ff;
  color: #167ee8;
  font-size: 24rpx;
  line-height: 50rpx;
  font-weight: 800;
}

.wrong-review__toggle::after {
  border: 0;
}

.question-card {
  box-sizing: border-box;
  padding: 30rpx 30rpx 28rpx;
  border-radius: 16rpx;
  background: rgba(255, 255, 255, 0.9);
  box-shadow:
    0 12rpx 36rpx rgba(54, 90, 130, 0.08),
    inset 0 0 0 1rpx rgba(226, 239, 250, 0.86);
}

.question-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18rpx;
}

.question-card__label {
  font-size: 25rpx;
  color: #718299;
}

.question-card__body {
  display: block;
}

.question-card__stem {
  margin-top: 20rpx;
  font-size: 30rpx;
  line-height: 1.4;
  font-weight: 860;
  color: #132b4b;
}

.question-options {
  margin-top: 28rpx;
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}

.question-option {
  position: relative;
  box-sizing: border-box;
  min-height: 82rpx;
  gap: 22rpx;
  padding: 16rpx 28rpx;
  border-radius: 16rpx;
  border: 2rpx solid #e6edf5;
  background: #ffffff;
}

.question-option--correct {
  border-color: rgba(40, 200, 120, 0.4);
  background: linear-gradient(90deg, rgba(231, 250, 239, 0.96), rgba(241, 255, 247, 0.92));
}

.question-option--selected {
  border-color: rgba(255, 78, 78, 0.6);
  background: linear-gradient(90deg, rgba(255, 241, 241, 0.96), rgba(255, 252, 252, 0.94));
  box-shadow: 0 10rpx 26rpx rgba(255, 78, 78, 0.12);
}

.question-option__letter {
  width: 40rpx;
  height: 40rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 2rpx solid #d9e2ec;
  color: #95a2b2;
  font-size: 24rpx;
  line-height: 1;
  font-weight: 860;
}

.question-option--correct .question-option__letter {
  color: #29bf71;
  border-color: #59d996;
  background: #effaf4;
}

.question-option--selected .question-option__letter {
  color: #ff4e4e;
  border-color: #ffa1a1;
  background: #fff4f4;
}

.question-option__content {
  min-width: 0;
  flex: 1;
  font-size: 28rpx;
  line-height: 1.35;
  color: #23354c;
  font-weight: 650;
}

.question-option__mark {
  flex: 0 0 auto;
  gap: 8rpx;
  font-size: 24rpx;
  font-weight: 860;
}

.question-option__mark--correct {
  color: #25b96b;
}

.question-option__mark--wrong {
  color: #ff3f3f;
}

.ai-result {
  margin-top: 28rpx;
  padding: 28rpx 28rpx 30rpx;
}

.ai-result__header {
  flex: 0 0 auto;
  justify-content: space-between;
  gap: 18rpx;
  padding: 0 4rpx 26rpx;
  border-bottom: 1rpx solid rgba(226, 239, 250, 0.86);
}

.ai-result__brand {
  gap: 14rpx;
  font-size: 28rpx;
  line-height: 1.2;
  color: #0c2449;
  font-weight: 900;
}

.ai-result__source {
  font-size: 24rpx;
  color: #899ab1;
}

.robot-face {
  width: 50rpx;
  height: 50rpx;
  position: relative;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 50%;
  background-image: url("@/static/brand/ai-assistant-logo.png");
  background-position: center center;
  background-size: cover;
}

.robot-face::before {
  content: none;
}

.robot-face__eye {
  display: none;
}

.robot-face--small {
  width: 52rpx;
  height: 52rpx;
}

.ai-stream {
  box-sizing: border-box;
  padding: 24rpx 0 0;
}

.ai-state-view :deep(.state-view__mark) {
  display: none;
}

.ai-state-view :deep(.state-view__title) {
  margin-top: 0;
}

.ai-state-view {
  padding-top: 0;
  padding-bottom: 0;
}

.ai-stream__paragraph {
  font-size: 30rpx;
  line-height: 1.68;
  color: #1f395c;
  font-weight: 520;
  white-space: pre-wrap;
}

.ai-section-list {
  display: flex;
  flex-direction: column;
  gap: 22rpx;
}

.ai-section {
  display: grid;
  grid-template-columns: 72rpx minmax(0, 1fr);
  gap: 18rpx;
  align-items: flex-start;
}

.ai-section__icon {
  width: 56rpx;
  height: 56rpx;
  margin-top: 12rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  box-shadow: 0 10rpx 22rpx rgba(22, 132, 232, 0.16);
}

.ai-section__icon--0 {
  background: linear-gradient(180deg, #72dca5 0%, #3fc982 100%);
}

.ai-section__icon--1 {
  background: linear-gradient(180deg, #ff8585 0%, #ff5959 100%);
}

.ai-section__icon--2 {
  background: linear-gradient(180deg, #87c8ff 0%, #43a4ff 100%);
}

.ai-section__icon--3 {
  background: linear-gradient(180deg, #4c9cff 0%, #167ee8 100%);
}

.ai-section__icon--4 {
  background: linear-gradient(180deg, #ffd278 0%, #ffad33 100%);
}

.ai-section__card {
  box-sizing: border-box;
  min-height: 88rpx;
  padding: 24rpx 26rpx;
  border-radius: 16rpx;
  background: rgba(255, 255, 255, 0.72);
  box-shadow:
    0 12rpx 30rpx rgba(64, 108, 150, 0.06),
    inset 0 0 0 1rpx rgba(226, 239, 250, 0.76);
}

.ai-section__title {
  font-size: 27rpx;
  line-height: 1.36;
  color: #10284a;
  font-weight: 900;
}

.ai-section__content {
  margin-top: 12rpx;
  font-size: 27rpx;
  line-height: 1.62;
  color: #405a7a;
  font-weight: 520;
  white-space: pre-wrap;
}

.ai-reference {
  margin-top: 24rpx;
  box-sizing: border-box;
  padding: 20rpx 20rpx 18rpx;
  border-radius: 16rpx;
  background: linear-gradient(180deg, rgba(245, 250, 255, 0.98), rgba(235, 245, 255, 0.95));
  border: 1rpx solid rgba(205, 224, 242, 0.94);
}

.ai-reference--follow {
  margin-top: 18rpx;
}

.ai-reference__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12rpx;
  margin-bottom: 14rpx;
}

.ai-reference__title {
  font-size: 24rpx;
  line-height: 1.2;
  color: #167ee8;
  font-weight: 900;
}

.ai-reference__hint {
  font-size: 22rpx;
  line-height: 1.2;
  color: #8d9db3;
  font-weight: 650;
}

.ai-reference__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
}

.ai-reference__tag {
  box-sizing: border-box;
  padding: 14rpx 18rpx;
  border-radius: 999rpx;
  background: #ffffff;
  box-shadow: inset 0 0 0 1rpx rgba(224, 233, 244, 0.94);
  color: #0f2f59;
  font-size: 24rpx;
  line-height: 1.2;
  font-weight: 800;
}
.follow-panel {
  margin-top: 26rpx;
  padding: 26rpx 30rpx 28rpx;
  background: linear-gradient(180deg, rgba(246, 251, 255, 0.92) 0%, rgba(228, 244, 255, 0.72) 100%);
  border-color: rgba(221, 238, 252, 0.92);
  box-shadow: 0 16rpx 44rpx rgba(68, 132, 190, 0.08);
}

.follow-panel__header {
  justify-content: space-between;
  margin-bottom: 26rpx;
}

.follow-panel__title {
  gap: 12rpx;
  font-size: 27rpx;
  line-height: 1.25;
  color: #092145;
  font-weight: 900;
}

.follow-panel__title-icon {
  width: 34rpx;
  height: 34rpx;
  justify-content: center;
  border-radius: 10rpx;
  background: linear-gradient(180deg, #4aa9ff 0%, #1684e8 100%);
}

.follow-stream {
  display: flex;
  flex-direction: column;
  gap: 18rpx;
  margin-bottom: 22rpx;
}

.follow-stream__user {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.follow-stream__question {
  box-sizing: border-box;
  max-width: 72%;
  padding: 18rpx 26rpx;
  border-radius: 20rpx 20rpx 8rpx 20rpx;
  background: linear-gradient(180deg, #bfe0ff 0%, #9dcbfb 100%);
  color: #0e5ba6;
  font-size: 25rpx;
  line-height: 1.48;
  text-align: left;
  font-weight: 650;
  box-shadow: 0 12rpx 24rpx rgba(22, 132, 232, 0.18);
}

.follow-stream__assistant {
  align-items: flex-start;
  gap: 12rpx;
}

.follow-stream__answer {
  font-size: 26rpx;
  line-height: 1.58;
  color: #405a7a;
  font-weight: 520;
  white-space: pre-wrap;
}

.follow-stream__assistant-body {
  box-sizing: border-box;
  min-width: 0;
  flex: 1;
  max-width: calc(100% - 68rpx);
  padding: 18rpx 24rpx;
  border-radius: 8rpx 20rpx 20rpx 20rpx;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 12rpx 28rpx rgba(64, 108, 150, 0.08);
}

.follow-stream__time {
  margin-top: 8rpx;
  font-size: 22rpx;
  line-height: 1.2;
  color: #9aabba;
}

.follow-stream__time--assistant {
  align-self: flex-end;
  margin-left: -54rpx;
}

.follow-input {
  box-sizing: border-box;
  min-height: 78rpx;
  gap: 14rpx;
  padding: 10rpx 16rpx 10rpx 26rpx;
  margin-top: 18rpx;
  border-radius: 39rpx;
  background: rgba(255, 255, 255, 0.95);
  box-shadow:
    0 10rpx 26rpx rgba(64, 108, 150, 0.08),
    inset 0 0 0 1rpx rgba(228, 238, 247, 0.94);
}

.follow-input__control {
  min-width: 0;
  flex: 1;
  height: 58rpx;
  color: #10284a;
  font-size: 24rpx;
}

.follow-input__placeholder {
  color: #a8b4c4;
}

.follow-input__count {
  flex: 0 0 auto;
  color: #8fa1b8;
  font-size: 23rpx;
  line-height: 1;
}

.follow-input__send {
  width: 118rpx;
  height: 58rpx;
  flex: 0 0 auto;
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  border-radius: 29rpx;
  background: linear-gradient(180deg, #2499f4 0%, #1684e8 100%);
  color: #ffffff;
  font-size: 23rpx;
  line-height: 58rpx;
  font-weight: 860;
  box-shadow: 0 12rpx 26rpx rgba(22, 132, 232, 0.24);
}

.follow-input__send[disabled] {
  opacity: 0.56;
}

.ai-disclaimer {
  padding: 18rpx 12rpx 0;
  text-align: center;
  color: #90a0b5;
  font-size: 23rpx;
  line-height: 1.5;
}

@media (max-width: 360px) {
  .ai-page__content {
    padding-left: 22rpx;
    padding-right: 22rpx;
  }

  .ai-hero__title {
    font-size: 38rpx;
  }

  .wrong-review__header,
  .ai-result__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .question-option {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .question-option__mark {
    margin-left: 62rpx;
  }

  .ai-section {
    grid-template-columns: 58rpx minmax(0, 1fr);
    gap: 12rpx;
  }

  .ai-section__icon {
    width: 48rpx;
    height: 48rpx;
  }

  .ai-stream__paragraph,
  .follow-stream__question,
  .follow-stream__answer {
    font-size: 28rpx;
  }

  .follow-input {
    padding-left: 20rpx;
  }

  .follow-input__send {
    width: 126rpx;
  }
}

page {
  background: #F8FBFF;
}

.ai-page {
  color: #0b2347;
  background: #F8FBFF;
  font-family:
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    Arial,
    sans-serif;
  -webkit-font-smoothing: antialiased;
  text-rendering: geometricPrecision;
}

.ai-page__bg {
  background:
    linear-gradient(rgba(253, 251, 247, 0.88), rgba(253, 251, 247, 0.88)),
    url("@/static/practice-start/paper-texture.jpg") center top / 320rpx 188rpx repeat;
}

.ai-page__bg::before {
  top: -170rpx;
  right: -130rpx;
  left: auto;
  width: 500rpx;
  height: 430rpx;
  opacity: 0.42;
  background: repeating-radial-gradient(
    ellipse at 100% 0,
    transparent 0 28rpx,
    rgba(145, 179, 214, 0.16) 29rpx 31rpx,
    transparent 32rpx 52rpx
  );
  transform: rotate(6deg);
}

.ai-page__bg::after {
  top: auto;
  right: -180rpx;
  bottom: -230rpx;
  left: auto;
  width: 520rpx;
  height: 560rpx;
  opacity: 0.38;
  background: repeating-radial-gradient(
    ellipse at 100% 100%,
    transparent 0 34rpx,
    rgba(145, 179, 214, 0.15) 35rpx 37rpx,
    transparent 38rpx 62rpx
  );
  transform: rotate(-8deg);
}

.ai-page__content {
  padding: calc(var(--app-safe-area-top) + 20rpx) 30rpx 28rpx;
}

.ai-hero {
  min-height: 160rpx;
  padding-top: 28rpx;
  align-items: flex-start;
}

.ai-hero__back {
  left: -10rpx;
  top: 14rpx;
  width: 72rpx;
  height: 72rpx;
  border-radius: 0;
}

.ai-hero__title-wrap {
  position: relative;
  z-index: 2;
  display: block;
  text-align: center;
}

.ai-hero__title {
  color: #0b2347;
  font-size: 50rpx;
  line-height: 1.2;
  font-weight: 800;
  letter-spacing: 0;
}

.ai-hero__drone {
  top: 54rpx;
  right: -2rpx;
  width: 156rpx;
  height: 76rpx;
  opacity: 0.19;
  transform: rotate(8deg);
}

.ai-hero__drone-body {
  left: 66rpx;
  top: 31rpx;
  width: 31rpx;
  height: 20rpx;
  border: 3rpx solid #8EA4BA;
  border-radius: 8rpx 8rpx 14rpx 14rpx;
}

.ai-hero__drone-body::before,
.ai-hero__drone-body::after {
  content: "";
  position: absolute;
  top: -7rpx;
  width: 48rpx;
  height: 3rpx;
  border-radius: 999rpx;
  background: #8EA4BA;
}

.ai-hero__drone-body::before {
  right: 24rpx;
  transform: rotate(20deg);
  transform-origin: right center;
}

.ai-hero__drone-body::after {
  left: 24rpx;
  transform: rotate(-20deg);
  transform-origin: left center;
}

.ai-hero__drone-line {
  left: 12rpx;
  right: 12rpx;
  top: 22rpx;
  height: 3rpx;
  background: #8EA4BA;
}

.ai-hero__drone-line--one::before,
.ai-hero__drone-line--one::after {
  content: "";
  position: absolute;
  top: -7rpx;
  width: 28rpx;
  height: 14rpx;
  box-sizing: border-box;
  border: 2rpx solid #8EA4BA;
  border-radius: 50%;
}

.ai-hero__drone-line--one::before {
  left: -4rpx;
}

.ai-hero__drone-line--one::after {
  right: -4rpx;
}

.ai-hero__drone-line--two {
  left: 78rpx;
  top: 43rpx;
  width: 3rpx;
  height: 24rpx;
  background: #8EA4BA;
}

.ai-answer__scroll {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  padding-bottom: calc(env(safe-area-inset-bottom) + 24rpx);
}

.wrong-review,
.ai-result,
.follow-panel {
  width: 100%;
  max-width: 100%;
  border: 1rpx solid rgba(222, 234, 246, 0.9);
  border-radius: 36rpx;
  background: rgba(255, 253, 252, 0.96);
  box-shadow:
    0 14rpx 30rpx rgba(27, 63, 104, 0.09),
    0 2rpx 6rpx rgba(27, 63, 104, 0.05);
}

.wrong-review {
  padding: 28rpx 34rpx 30rpx;
}

.wrong-review__header {
  min-height: 44rpx;
  margin-bottom: 0;
  justify-content: space-between;
  gap: 20rpx;
}

.section-heading,
.ai-section__heading,
.ai-reference__label,
.ai-reference__meta {
  min-width: 0;
  display: flex;
  align-items: center;
}

.section-heading,
.ai-section__heading {
  gap: 16rpx;
}

.section-heading__mark {
  width: 7rpx;
  height: 34rpx;
  flex: 0 0 auto;
  border-radius: 999rpx;
  background: #0878EE;
}

.wrong-review__title,
.ai-result__brand,
.follow-panel__title,
.ai-section__title {
  color: #0b2347;
  letter-spacing: 0;
}

.wrong-review__title {
  font-size: 36rpx;
  line-height: 1.25;
  font-weight: 800;
}

.wrong-review__toggle {
  width: 52rpx;
  height: 52rpx;
  min-width: 52rpx;
  margin: -4rpx -10rpx -4rpx 0;
  padding: 0;
  border-radius: 50%;
  background: transparent;
  line-height: 1;
}

.wrong-review__toggle::after {
  border: 0;
}

.wrong-review__body {
  min-width: 0;
}

.wrong-review__tag {
  width: fit-content;
  max-width: 100%;
  min-height: 46rpx;
  box-sizing: border-box;
  margin-top: 25rpx;
  padding: 7rpx 16rpx;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10rpx;
  border: 1rpx solid rgba(8, 120, 238, 0.23);
  border-radius: 12rpx;
  color: #0b5fb8;
  background: rgba(234, 244, 255, 0.82);
  font-size: 27rpx;
  line-height: 1.25;
  font-weight: 500;
}

.wrong-review__tag-dot {
  color: #0878EE;
  font-weight: 800;
}

.question-card__stem {
  min-width: 0;
  margin-top: 25rpx;
  color: #0b2347;
  font-size: 35rpx;
  line-height: 1.48;
  font-weight: 700;
  letter-spacing: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.wrong-review__divider {
  height: 1rpx;
  margin: 24rpx 0 20rpx;
  background: #dedede;
}

.answer-summary {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 15rpx;
}

.answer-summary__row {
  width: 100%;
  min-width: 0;
  min-height: 70rpx;
  box-sizing: border-box;
  padding: 13rpx 20rpx;
  display: flex;
  align-items: center;
  gap: 17rpx;
  border-radius: 15rpx;
}

.answer-summary__row--wrong {
  color: #fa372a;
  background: rgba(250, 55, 42, 0.065);
}

.answer-summary__row--correct {
  color: #309c54;
  background: rgba(48, 156, 84, 0.07);
}

.answer-summary__icon {
  width: 40rpx;
  height: 40rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.answer-summary__row--wrong .answer-summary__icon {
  background: #fa372a;
  box-shadow: 0 4rpx 10rpx rgba(250, 55, 42, 0.18);
}

.answer-summary__row--correct .answer-summary__icon {
  background: #30a95c;
  box-shadow: 0 4rpx 10rpx rgba(48, 156, 84, 0.16);
}

.answer-summary__text {
  min-width: 0;
  flex: 1;
  font-size: 29rpx;
  line-height: 1.45;
  font-weight: 500;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.answer-summary__label {
  font-weight: 700;
}

.ai-result {
  margin-top: 30rpx;
  padding: 29rpx 34rpx 30rpx;
}

.ai-result__header {
  display: block;
  padding: 0 0 22rpx;
  border-bottom: 1rpx dashed #dce7f2;
}

.ai-result__brand {
  display: block;
  font-size: 36rpx;
  line-height: 1.25;
  font-weight: 800;
}

.ai-result__source {
  margin-top: 15rpx;
  color: #7b8290;
  font-size: 26rpx;
  line-height: 1.45;
  font-weight: 400;
}

.ai-stream {
  padding: 23rpx 0 0;
}

.ai-state-view {
  min-height: 180rpx;
  padding: 18rpx 0 8rpx;
}

.ai-state-view :deep(.state-view__mark) {
  display: none;
}

.ai-state-view :deep(.state-view__title) {
  margin-top: 0;
  color: #0b2347;
}

.ai-state-view :deep(.state-view__action) {
  background: #0878EE;
}

.ai-stream__paragraph {
  color: #0b2347;
  font-size: 31rpx;
  line-height: 1.75;
  font-weight: 400;
  letter-spacing: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.ai-section-list {
  gap: 0;
}

.ai-section {
  display: block;
  min-width: 0;
}

.ai-section + .ai-section {
  margin-top: 29rpx;
}

.ai-section__heading {
  margin-bottom: 14rpx;
}

.ai-section__title {
  display: block;
  min-width: 0;
  font-size: 34rpx;
  line-height: 1.35;
  font-weight: 800;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.ai-section__content {
  margin-top: 0;
  padding-left: 22rpx;
  color: #0b2347;
  font-size: 30rpx;
  line-height: 1.75;
  font-weight: 400;
  letter-spacing: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.ai-reference {
  margin-top: 28rpx;
  padding: 19rpx 0 0;
  border: 0;
  border-top: 1rpx dashed #dce7f2;
  border-radius: 0;
  background: transparent;
}

.ai-reference__head {
  min-height: 62rpx;
  margin-bottom: 0;
  gap: 18rpx;
}

.ai-reference__label {
  flex: 1;
  gap: 18rpx;
}

.ai-reference__icon {
  width: 52rpx;
  height: 52rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #f1f2f3;
}

.ai-reference__title {
  color: #0b2347;
  font-size: 30rpx;
  line-height: 1.3;
  font-weight: 700;
}

.ai-reference__meta {
  flex: 0 0 auto;
  gap: 10rpx;
}

.ai-reference__hint {
  color: #909090;
  font-size: 23rpx;
  line-height: 1.2;
  font-weight: 400;
}

.ai-reference__tags {
  margin-top: 13rpx;
  padding-left: 70rpx;
  gap: 10rpx;
}

.ai-reference__tag {
  max-width: 100%;
  padding: 8rpx 13rpx;
  border-radius: 8rpx;
  color: #496684;
  background: #F3F7FB;
  box-shadow: none;
  font-size: 22rpx;
  line-height: 1.35;
  font-weight: 500;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.ai-reference--follow {
  margin-top: 18rpx;
  padding-top: 16rpx;
}

.follow-panel {
  margin-top: 30rpx;
  padding: 27rpx 29rpx 30rpx;
  border-color: rgba(222, 234, 246, 0.9);
  background: rgba(255, 253, 252, 0.96);
  box-shadow:
    0 14rpx 30rpx rgba(27, 63, 104, 0.09),
    0 2rpx 6rpx rgba(27, 63, 104, 0.05);
}

.follow-panel__header {
  margin-bottom: 24rpx;
}

.follow-panel__title {
  gap: 16rpx;
  font-size: 33rpx;
  line-height: 1.35;
  font-weight: 800;
}

.follow-stream {
  margin-bottom: 22rpx;
}

.follow-stream__question {
  border-radius: 18rpx 18rpx 6rpx 18rpx;
  color: #0b5fb8;
  background: #E8F3FF;
  box-shadow: none;
}

.follow-stream__assistant-body {
  border: 1rpx solid #E1EAF4;
  background: #F8FBFF;
  box-shadow: none;
}

.follow-stream__answer {
  color: #263b57;
}

.follow-input {
  position: relative;
  min-height: 132rpx;
  margin-top: 0;
  padding: 22rpx 110rpx 22rpx 28rpx;
  border: 2rpx solid #dfe9f4;
  border-radius: 18rpx;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: none;
}

.follow-input__control {
  min-width: 0;
  width: 100%;
  height: 84rpx;
  color: #0b2347;
  font-size: 27rpx;
  line-height: 84rpx;
}

.follow-input__placeholder {
  color: #98979a;
}

.follow-input__count {
  display: none;
}

.follow-input__send {
  position: absolute;
  top: 50%;
  right: 18rpx;
  width: 76rpx;
  height: 76rpx;
  min-width: 76rpx;
  margin: 0;
  padding: 0;
  border-radius: 17rpx;
  background: #0878EE;
  box-shadow: 0 8rpx 16rpx rgba(8, 120, 238, 0.18);
  transform: translateY(-50%);
}

.follow-input__send[disabled] {
  opacity: 0.72;
}

.follow-input__send::after {
  border: 0;
}

.ai-disclaimer {
  display: none;
}

@media (max-width: 360px) {
  .ai-page__content {
    padding-right: 24rpx;
    padding-left: 24rpx;
  }

  .ai-hero__title {
    font-size: 46rpx;
  }

  .wrong-review__header,
  .ai-result__header {
    align-items: initial;
    flex-direction: initial;
  }

  .question-card__stem {
    font-size: 33rpx;
  }

  .answer-summary__text,
  .ai-stream__paragraph,
  .ai-section__content {
    font-size: 28rpx;
  }

  .ai-section {
    display: block;
  }

  .follow-input {
    padding-left: 24rpx;
  }

  .follow-input__send {
    width: 72rpx;
    min-width: 72rpx;
  }
}

.ai-page__content {
  padding-top: var(--app-safe-area-top);
}

.ai-hero {
  min-height: var(--app-page-header-height);
  align-items: center;
  padding-top: 0;
}

.ai-hero__title-wrap {
  align-items: center;
}

.ai-hero__back {
  top: 0;
  height: var(--app-page-header-height);
}

.ai-hero__title {
  font-size: 40rpx;
}

.question-card__stem {
  margin-top: 9rpx;
  font-size: 31rpx;
}

.ai-result {
  margin-top: 28rpx;
}

.wrong-review,
.ai-result {
  padding-right: 30rpx;
  padding-left: 30rpx;
}

.ai-result__header {
  padding-bottom: 24rpx;
}

.wrong-review__title,
.ai-result__brand {
  font-size: 30rpx;
}

.ai-result__source {
  margin-top: 10rpx;
  font-size: 20rpx;
}

.wrong-review__tag {
  font-size: 24rpx;
}

.answer-summary__text {
  font-size: 26rpx;
}

.ai-stream__paragraph {
  font-size: 24rpx;
  line-height: 56rpx;
}

.ai-section__title,
.ai-presentation__heading {
  color: #0b2347;
  font-size: 30rpx;
  line-height: 1.35;
  font-weight: 800;
}

.ai-presentation {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.ai-presentation__paragraph,
.ai-presentation__heading,
.ai-presentation__bullet-text {
  display: block;
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.ai-presentation__paragraph,
.ai-presentation__bullet,
.ai-presentation__bullet-mark,
.ai-presentation__bullet-text {
  color: #0b2347;
  font-size: 24rpx;
  line-height: 56rpx;
  font-weight: 400;
}

.ai-presentation__paragraph {
  white-space: pre-wrap;
}

.ai-presentation__paragraph + .ai-presentation__heading,
.ai-presentation__bullets + .ai-presentation__paragraph,
.ai-presentation__paragraph + .ai-presentation__paragraph {
  margin-top: 18rpx;
}

.ai-presentation__heading + .ai-presentation__bullets {
  margin-top: 8rpx;
}

.ai-presentation__bullets {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.ai-presentation__bullet {
  min-width: 0;
  display: flex;
  align-items: flex-start;
}

.ai-presentation__bullet-mark {
  width: 30rpx;
  flex: 0 0 auto;
  color: #0878EE;
  font-weight: 800;
}

.ai-presentation__bullet-text {
  flex: 1;
}

.ai-reference__title {
  font-size: 24rpx;
}

.follow-panel {
  padding-bottom: 26rpx;
}

.follow-panel__header {
  margin-bottom: 14rpx;
}

.follow-panel__title {
  font-size: 30rpx;
}

.follow-input {
  width: calc(100% + 14rpx);
  min-height: 124rpx;
  margin-left: -7rpx;
  padding-top: 20rpx;
  padding-bottom: 20rpx;
}

.ai-reference__hint,
.ai-reference__tags {
  display: none;
}

.wrong-review {
  padding-bottom: 36rpx;
}

.wrong-review__tag {
  padding-right: 12rpx;
  padding-left: 12rpx;
  gap: 6rpx;
}

.ai-result {
  padding-top: 36rpx;
  padding-bottom: 39rpx;
}

.ai-result__header {
  padding-bottom: 30rpx;
}

.ai-stream {
  padding-top: 30rpx;
}

.ai-presentation__paragraph {
  font-size: 27rpx;
  line-height: 56rpx;
  font-weight: 600;
}

.ai-presentation__paragraph + .ai-presentation__heading {
  margin-top: 48rpx;
}

.ai-presentation__heading + .ai-presentation__bullets {
  margin-top: 20rpx;
}

.ai-result .ai-stream > .ai-reference {
  margin-top: 19rpx;
}

.follow-input__send[disabled] {
  color: #ffffff !important;
  background: #0878EE !important;
  opacity: 1;
}

.follow-input__send :deep(.uv-icon) {
  opacity: 0;
}

.follow-input__send::before,
.follow-input__send::after {
  content: "";
  position: absolute;
  pointer-events: none;
}

.follow-input__send::before {
  top: 21rpx;
  left: 20rpx;
  width: 38rpx;
  height: 32rpx;
  background: #ffffff;
  clip-path: polygon(0 43%, 100% 0, 70% 100%, 51% 65%, 29% 82%, 35% 57%);
}

.follow-input__send::after {
  top: 36rpx;
  left: 30rpx;
  width: 25rpx;
  height: 2rpx;
  border: 0;
  border-radius: 999rpx;
  background: #0878EE;
  transform: rotate(-27deg);
  transform-origin: left center;
}

.ai-reference__icon {
  position: relative;
}

.ai-reference__icon :deep(.uv-icon) {
  opacity: 0;
}

.ai-reference__icon::before,
.ai-reference__icon::after {
  content: "";
  position: absolute;
  top: 14rpx;
  width: 17rpx;
  height: 24rpx;
  box-sizing: border-box;
  border: 2rpx solid #496684;
  background: transparent;
  pointer-events: none;
}

.ai-reference__icon::before {
  left: 8rpx;
  border-right-width: 1rpx;
  border-radius: 5rpx 1rpx 2rpx 5rpx;
  transform: skewY(6deg);
}

.ai-reference__icon::after {
  right: 8rpx;
  border-left-width: 1rpx;
  border-radius: 1rpx 5rpx 5rpx 2rpx;
  transform: skewY(-6deg);
}

.ai-page__bg::before {
  right: -30rpx;
  width: 280rpx;
  height: 300rpx;
}

.ai-page__bg::after {
  right: -100rpx;
  width: 260rpx;
  height: 360rpx;
}

.ai-presentation__bullet-mark {
  width: 40rpx;
}

.ai-reference__icon {
  width: 62rpx;
  height: 62rpx;
}

.ai-reference__icon::before,
.ai-reference__icon::after {
  top: 19rpx;
}

.ai-reference__icon::before {
  left: 13rpx;
}

.ai-reference__icon::after {
  right: 13rpx;
}

.follow-input__send {
  width: 73rpx;
  height: 73rpx;
  min-width: 73rpx;
  background: linear-gradient(135deg, #168BF2 0%, #0A67DA 100%);
}

.follow-input__send[disabled] {
  background: linear-gradient(135deg, #168BF2 0%, #0A67DA 100%) !important;
}

.follow-input__send::before {
  left: 18rpx;
}

.follow-input__send::after {
  left: 28rpx;
}

.ai-hero__drone-line--two::after {
  content: "";
  position: absolute;
  left: -7rpx;
  bottom: -11rpx;
  width: 17rpx;
  height: 12rpx;
  box-sizing: border-box;
  border: 2rpx solid #8EA4BA;
  border-radius: 3rpx 3rpx 6rpx 6rpx;
  pointer-events: none;
}
</style>
