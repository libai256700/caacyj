<template>
  <view class="practice-topic-section">
    <view class="practice-topic-grid">
      <view
        v-for="topic in displayTopics"
        :key="topic.key"
        class="practice-topic"
        role="button"
        :aria-label="`${topic.index} ${topic.title}`"
        @tap="$emit('select', topic.source)"
      >
        <image
          class="practice-topic__skin"
          :src="topic.skinUrl"
          mode="scaleToFill"
          aria-hidden="true"
        />
        <view class="practice-topic__content">
          <text class="practice-topic__index">{{ topic.index }}</text>
          <text
            class="practice-topic__name"
            :class="{
              'practice-topic__name--compact': topic.compact,
              'practice-topic__name--long': topic.long
            }"
          >{{ topic.title }}</text>
        </view>
        <uv-icon class="practice-topic__arrow" name="arrow-right" color="#737373" size="40rpx" />
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PracticeTopic } from '@/services/practice'

type TopicStyle = {
  keys: string[]
  skinUrl: string
}

const props = defineProps<{
  topics: PracticeTopic[]
}>()

defineEmits<{
  select: [topic: PracticeTopic]
}>()

const topicStyles: TopicStyle[] = [
  { keys: ['overview', '概述', '基础知识'], skinUrl: '/static/exam-topics/cards/overview.png' },
  { keys: ['system_com', 'system', '系统组成', '系统介绍'], skinUrl: '/static/exam-topics/cards/system.png' },
  { keys: ['air_traffi', 'traffic', '空中交通', '交通管制'], skinUrl: '/static/exam-topics/cards/traffic.png' },
  { keys: ['flight_man', 'manual', '飞行手册'], skinUrl: '/static/exam-topics/cards/manual.png' },
  { keys: ['operation_', 'attention', '注意事项', '安全操作'], skinUrl: '/static/exam-topics/cards/attention.png' },
  { keys: ['meteorolog', 'weather', '气象', '天气'], skinUrl: '/static/exam-topics/cards/weather.png' },
  { keys: ['rotary_uav', 'rotor', '旋翼'], skinUrl: '/static/exam-topics/cards/rotor.png' },
  { keys: ['mission_pl', 'planning', '任务规划', '航线规划'], skinUrl: '/static/exam-topics/cards/planning.png' },
  { keys: ['flight_pri', 'performance', '飞行原理', '飞行性能'], skinUrl: '/static/exam-topics/cards/performance.png' },
  { keys: ['comprehens', 'qa', '问答', '综合题'], skinUrl: '/static/exam-topics/cards/qa.png' },
  { keys: ['instructor', 'teacher', '教员'], skinUrl: '/static/exam-topics/cards/teacher.png' }
]

const resolveTopicStyle = (topic: PracticeTopic, fallback: number) => {
  const haystack = `${topic.fieldType || ''} ${topic.categoryName || ''} ${topic.title || ''}`.toLowerCase()
  return topicStyles.find((style) => style.keys.some((key) => haystack.includes(key)))
    ?? topicStyles[fallback % topicStyles.length]
}

const resolveSortValue = (topic: PracticeTopic, fallback: number) => {
  if (typeof topic.sortNo === 'number' && Number.isFinite(topic.sortNo)) {
    return topic.sortNo
  }
  const index = Number.parseInt(String(topic.index || ''), 10)
  return Number.isFinite(index) ? index : fallback
}

const displayTopics = computed(() => {
  const activeTopics = props.topics
    .filter((topic) => topic.categoryStatus !== false)
    .map((source, sourceIndex) => ({ source, sourceIndex }))
    .sort((left, right) =>
      resolveSortValue(left.source, left.sourceIndex + 1) - resolveSortValue(right.source, right.sourceIndex + 1)
      || left.sourceIndex - right.sourceIndex
    )

  return activeTopics.map(({ source, sourceIndex }, displayIndex) => {
    const title = source.categoryName || source.title || source.id
    const rawIndex = String(source.index || '').trim()
    const index = rawIndex
      ? (/^\d+$/.test(rawIndex) ? rawIndex.padStart(2, '0') : rawIndex)
      : String(displayIndex + 1).padStart(2, '0')
    return {
      source,
      key: `${source.id || source.fieldType || 'topic'}-${sourceIndex}`,
      index,
      title,
      skinUrl: resolveTopicStyle(source, displayIndex).skinUrl,
      compact: title.length >= 8,
      long: title.length >= 13
    }
  })
})
</script>

<style lang="scss">
.practice-topic-section {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  height: 1184rpx;
  margin-top: 0;
  padding: 0;
  background: url('/static/exam-topics/practice-topics-grid-reference.png') center top / 100% 100% no-repeat;
}

.practice-topic-grid {
  position: absolute;
  inset: 0;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-rows: 192rpx 191rpx 190rpx 164rpx 177rpx 158rpx;
  gap: 17rpx 19rpx;
  padding: 0 24rpx 0 21rpx;
}

.practice-topic {
  position: relative;
  box-sizing: border-box;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  display: flex;
  align-items: center;
  padding: 0;
  background: transparent;
}

.practice-topic__skin {
  position: absolute;
  z-index: 0;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  opacity: 0;
  pointer-events: none;
}

.practice-topic__content {
  position: relative;
  z-index: 1;
  min-width: 0;
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 8rpx;
  opacity: 0;
}

.practice-topic__index,
.practice-topic__name {
  display: block;
  letter-spacing: 0;
}

.practice-topic__index {
  flex: 0 0 auto;
  color: #0878EE;
  font-family: "Arial Narrow", Arial, sans-serif;
  font-size: 36rpx;
  line-height: 1.12;
  font-weight: 600;
}

.practice-topic__name {
  min-width: 0;
  overflow: hidden;
  color: #08264e;
  font-size: 26rpx;
  line-height: 1.28;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.practice-topic__name--compact {
  font-size: 22rpx;
  line-height: 1.34;
}

.practice-topic__name--long {
  display: -webkit-box;
  overflow: hidden;
  font-size: 20rpx;
  line-height: 1.28;
  text-overflow: clip;
  white-space: normal;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.practice-topic__arrow {
  position: absolute;
  z-index: 2;
  top: 50%;
  right: 13rpx;
  margin-top: -20rpx;
  opacity: 0;
}
</style>
