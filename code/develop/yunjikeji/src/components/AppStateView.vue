<template>
  <view class="state-view" :class="`state-view--${status}`">
    <view v-if="showMark" class="state-view__mark">
      <view class="state-view__mark-core"></view>
    </view>
    <text class="state-view__title">{{ displayTitle }}</text>
    <text class="state-view__message">{{ displayMessage }}</text>
    <button v-if="status === 'error' && actionText" class="state-view__action" @tap="$emit('retry')">
      {{ actionText }}
    </button>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AppAsyncStatus } from '@/stores/appState'

const props = withDefaults(
  defineProps<{
    status: AppAsyncStatus
    title?: string
    message?: string
    actionText?: string
    showMark?: boolean
  }>(),
  {
    title: '',
    message: '',
    actionText: '',
    showMark: true
  }
)

defineEmits<{
  retry: []
}>()

const fallback = {
  ready: {
    title: '内容已就绪',
    message: '公共状态组件已接入当前页面。'
  },
  loading: {
    title: '正在加载',
    message: '请稍候，系统正在同步学习内容。'
  },
  empty: {
    title: '暂无内容',
    message: '当前模块还没有可展示的数据。'
  },
  error: {
    title: '加载失败',
    message: '当前模块暂时无法获取数据，请稍后重试。'
  }
}

const displayTitle = computed(() => props.title || fallback[props.status].title)
const displayMessage = computed(() => props.message || fallback[props.status].message)
</script>

<style lang="scss">
.state-view {
  box-sizing: border-box;
  width: 100%;
  padding: 42rpx 34rpx;
  border: 1rpx solid rgba(21, 94, 168, 0.1);
  border-radius: 30rpx;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18rpx 54rpx rgba(54, 90, 130, 0.12);
}

.state-view__mark {
  width: 78rpx;
  height: 78rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 26rpx;
  background: rgba(21, 94, 168, 0.1);
}

.state-view__mark-core {
  width: 30rpx;
  height: 30rpx;
  border-radius: 50%;
  background: #155ea8;
}

.state-view--loading .state-view__mark-core {
  background: #d38b21;
}

.state-view--empty .state-view__mark-core {
  background: #8c9aaa;
}

.state-view--error .state-view__mark-core {
  background: #c94d3f;
}

.state-view__title,
.state-view__message {
  display: block;
}

.state-view__title {
  margin-top: 28rpx;
  font-size: 32rpx;
  line-height: 1.25;
  font-weight: 750;
  color: #132b4b;
}

.state-view__message {
  margin-top: 14rpx;
  font-size: 26rpx;
  line-height: 1.5;
  color: #65758a;
}

.state-view__action {
  margin: 28rpx 0 0;
  height: 78rpx;
  border-radius: 999rpx;
  background: #155ea8;
  color: #ffffff;
  font-size: 26rpx;
  line-height: 78rpx;
}
</style>
