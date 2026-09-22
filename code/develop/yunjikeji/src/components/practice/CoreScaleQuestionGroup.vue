<template>
  <view class="core-scale-card" :class="{ 'core-scale-card--supplement': variant === 'supplement' }">
    <view class="core-scale-card__intro">
      <image
        class="core-scale-card__owl"
        src="/static/brand/ai-assistant-logo.png"
        mode="aspectFit"
        aria-hidden="true"
      />
      <view class="core-scale-card__intro-copy">
        <text class="core-scale-card__title">{{ title }}</text>
      </view>
    </view>

    <view class="core-scale-guide">
      <view class="core-scale-guide__title">
        <view class="core-scale-guide__mark" aria-hidden="true"></view>
        <text>{{ guideText }}</text>
      </view>
      <view class="core-scale-guide__options">
        <view v-for="option in scaleOptions" :key="option.number" class="core-scale-guide__option">
          <text class="core-scale-guide__number">{{ option.number }}</text>
          <text class="core-scale-guide__label">{{ option.label }}</text>
        </view>
      </view>
    </view>

    <view class="core-scale-questions">
      <view v-for="item in displayQuestions" :key="item.question.id" class="core-scale-question">
        <view v-if="item.showDimension" class="core-scale-dimension">
          <text class="core-scale-dimension__title">{{ item.dimension }}</text>
          <view class="core-scale-dimension__line" aria-hidden="true"></view>
        </view>

        <text class="core-scale-question__stem">
          <text class="core-scale-question__number">{{ item.question.index + 1 }}.</text>
          <text>{{ displayStem(item.question) }}</text>
        </text>

        <view class="core-scale-question__options">
          <button
            v-for="(option, optionIndex) in item.question.options"
            :key="option.id"
            class="core-scale-option"
            :class="{ 'core-scale-option--selected': isSelected(item.question, option) }"
            :aria-label="`${item.question.index + 1}题，${option.content}`"
            @tap="selectOption(item.question.id, option.id)"
          >
            <view class="core-scale-option__circle">
              <text>{{ optionNumber(option, optionIndex) }}</text>
            </view>
          </button>
        </view>

        <view v-if="showEndpoints" class="core-scale-question__endpoints" aria-hidden="true">
          <text>非常不同意</text>
          <text>非常同意</text>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AssessmentOption, AssessmentQuestion } from '@/services/assessment'

const props = defineProps<{
  questions: AssessmentQuestion[]
  answers: Record<string, string[]>
  groupStartIndex: number
  variant?: 'core' | 'supplement'
  title?: string
  guideText?: string
  sectionTitle?: string
  showEndpoints?: boolean
  stemPrefix?: string
  stripStemBrackets?: boolean
}>()

const variant = computed(() => props.variant || 'core')
const title = computed(() => props.title || '核心量表')
const guideText = computed(() => props.guideText || '请选择最符合你当前感受的数字')
const showEndpoints = computed(() => props.showEndpoints !== false)

const emit = defineEmits<{
  select: [questionId: string, optionId: string]
}>()

const dimensionByQuestionIndex: Record<number, string> = {
  5: '行业认知',
  6: '行业认知',
  7: '职业动机',
  8: '职业动机',
  9: '自我效能',
  10: '自我效能',
  11: '学习准备',
  12: '学习准备',
  13: '现实推进可行性',
  14: '现实推进可行性'
}

const fallbackDimensions = ['行业认知', '行业认知', '职业动机', '职业动机', '自我效能', '自我效能', '学习准备', '学习准备', '现实推进可行性', '现实推进可行性']

const parseScaleOption = (option: AssessmentOption, fallbackIndex: number) => {
  const content = option.content.trim()
  const match = content.match(/^(\d+)\s*(.*)$/)
  return {
    number: match?.[1] || String(fallbackIndex + 1),
    label: match?.[2] || content
  }
}

const scaleOptions = computed(() => (props.questions[0]?.options || [])
  .slice(0, variant.value === 'supplement' ? 3 : 5)
  .map(parseScaleOption))

const resolveDimension = (question: AssessmentQuestion) => {
  const mapped = dimensionByQuestionIndex[question.index]
  if (mapped) {
    return mapped
  }
  return fallbackDimensions[question.index - props.groupStartIndex] || '核心量表'
}

const displayQuestions = computed(() => {
  let previousDimension = ''
  return props.questions.map((question) => {
    const dimension = variant.value === 'supplement'
      ? props.sectionTitle || '补充模块'
      : resolveDimension(question)
    const showDimension = variant.value === 'supplement'
      ? previousDimension === ''
      : dimension !== previousDimension
    previousDimension = dimension
    return { question, dimension, showDimension }
  })
})

const displayStem = (question: AssessmentQuestion) => {
  let stem = question.stem || question.title
  if (props.stemPrefix && stem.startsWith(props.stemPrefix)) {
    stem = stem.slice(props.stemPrefix.length).trim()
  }
  if (props.stripStemBrackets && stem.startsWith('【') && stem.endsWith('】')) {
    stem = stem.slice(1, -1).trim()
  }
  return stem
}

const selectedIds = (question: AssessmentQuestion) => props.answers[question.id] || []

const isSelected = (question: AssessmentQuestion, option: AssessmentOption) => {
  const selected = selectedIds(question)
  return selected.includes(option.id) || selected.includes(option.label)
}

const optionNumber = (option: AssessmentOption, fallbackIndex: number) => {
  const match = option.content.trim().match(/^(\d+)/)
  return match?.[1] || String(fallbackIndex + 1)
}

const selectOption = (questionId: string, optionId: string) => emit('select', questionId, optionId)
</script>

<style lang="scss" scoped>
.core-scale-card {
  box-sizing: border-box;
  padding: 38rpx 30rpx 30rpx;
  border: 2rpx solid #DCE7F2;
  border-radius: 24rpx;
  background: rgba(255, 255, 255, .92);
  box-shadow: 0 12rpx 28rpx rgba(18, 61, 108, .08);
  color: #0a1d3b;
}

.core-scale-card--supplement {
  padding-top: 34rpx;
}

.core-scale-card__intro {
  display: flex;
  align-items: center;
  min-height: 84rpx;
}

.core-scale-card__owl {
  width: 82rpx;
  height: 82rpx;
  flex: 0 0 82rpx;
  margin-right: 25rpx;
  border-radius: 50%;
}

.core-scale-card__intro-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.core-scale-card__title {
  color: #071b3a;
  font-size: 42rpx;
  line-height: 1.15;
  font-weight: 700;
}

.core-scale-guide {
  box-sizing: border-box;
  margin-top: 28rpx;
  padding: 20rpx 19rpx 19rpx;
  border: 2rpx solid #DCE7F2;
  border-radius: 14rpx;
  background: #F2F7FC;
}

.core-scale-guide__title {
  display: flex;
  align-items: center;
  color: #0a2146;
  font-size: 26rpx;
  line-height: 1.3;
  font-weight: 500;
}

.core-scale-guide__mark {
  width: 5rpx;
  height: 25rpx;
  flex: 0 0 5rpx;
  margin-right: 13rpx;
  border-radius: 1rpx;
  background: #167EE8;
}

.core-scale-guide__options {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6rpx;
  margin-top: 18rpx;
}

.core-scale-card--supplement .core-scale-guide__options,
.core-scale-card--supplement .core-scale-question__options {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.core-scale-guide__option {
  min-width: 0;
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 7rpx;
  white-space: nowrap;
}

.core-scale-guide__number {
  color: #273847;
  font-size: 27rpx;
  line-height: 1.2;
  font-weight: 700;
}

.core-scale-guide__label {
  min-width: 0;
  overflow: hidden;
  color: #344761;
  font-size: 22rpx;
  line-height: 1.2;
  font-weight: 500;
  text-overflow: ellipsis;
}

.core-scale-questions {
  margin-top: 30rpx;
}

.core-scale-question {
  padding: 0 0 26rpx;
  border-bottom: 2rpx dashed #DCE7F2;
}

.core-scale-question + .core-scale-question {
  padding-top: 27rpx;
}

.core-scale-question:last-child {
  border-bottom: 0;
  padding-bottom: 23rpx;
}

.core-scale-dimension {
  display: flex;
  align-items: center;
  gap: 14rpx;
  margin-bottom: 23rpx;
}

.core-scale-dimension__title {
  position: relative;
  flex: 0 0 auto;
  padding-left: 16rpx;
  color: #0b345a;
  font-size: 27rpx;
  line-height: 1.25;
  font-weight: 700;
}

.core-scale-dimension__title::before {
  content: '';
  position: absolute;
  top: 1rpx;
  bottom: 1rpx;
  left: 0;
  width: 5rpx;
  border-radius: 1rpx;
  background: #167EE8;
}

.core-scale-dimension__line {
  height: 2rpx;
  flex: 1;
  background: #dce7f2;
}

.core-scale-question__stem {
  display: block;
  color: #0b1d3b;
  font-size: 27rpx;
  line-height: 1.48;
  font-weight: 500;
}

.core-scale-card--supplement .core-scale-question__stem {
  font-size: 27rpx;
}

.core-scale-question__number {
  margin-right: 10rpx;
  font-weight: 700;
}

.core-scale-question__options {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10rpx;
  margin-top: 22rpx;
}

.core-scale-option {
  width: 100%;
  height: 70rpx;
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 50%;
  background: transparent;
}

.core-scale-option::after {
  border: 0;
}

.core-scale-option__circle {
  box-sizing: border-box;
  width: 64rpx;
  height: 64rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2rpx solid #d8e4f0;
  border-radius: 50%;
  background: #FFFFFF;
  color: #0c1e3a;
  font-size: 27rpx;
  line-height: 1;
  font-weight: 600;
}

.core-scale-option--selected .core-scale-option__circle {
  border-color: #167EE8;
  background: #E9F3FF;
  box-shadow: inset 0 0 0 7rpx #E9F3FF, inset 0 0 0 13rpx #167EE8;
  color: #167EE8;
}

.core-scale-question__endpoints {
  display: flex;
  justify-content: space-between;
  margin: 8rpx 28rpx 0;
  color: #6f8098;
  font-size: 22rpx;
  line-height: 1.2;
  font-weight: 500;
}

@media screen and (max-width: 360px) {
  .core-scale-card {
    padding-right: 22rpx;
    padding-left: 22rpx;
  }

  .core-scale-guide__option {
    gap: 3rpx;
  }

  .core-scale-guide__number,
  .core-scale-guide__label {
    font-size: 19rpx;
  }

  .core-scale-question__stem {
    font-size: 25rpx;
  }

  .core-scale-card--supplement .core-scale-question__stem {
    font-size: 25rpx;
  }
}
</style>
