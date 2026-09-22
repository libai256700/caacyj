<template>
  <view class="practice-record-page" :style="$appSafeAreaStyle" @tap="closePicker">
    <view class="practice-record-page__bg"></view>

    <view class="practice-record-page__content">
      <view class="practice-record-nav">
        <view class="practice-record-nav__back" @tap="goBack">
          <uv-icon name="arrow-left" color="#06224A" size="46rpx" />
        </view>
        <text class="practice-record-nav__title">练习记录</text>
        <view class="practice-record-nav__spacer"></view>
      </view>

      <view class="practice-record-filter">
        <view
          class="practice-record-filter__item"
          :class="{ 'practice-record-filter__item--open': pickerType === 'category' }"
          @tap.stop="toggleCategoryPicker"
        >
          <text class="practice-record-filter__label">练习分类</text>
          <view class="practice-record-filter__select">
            <text>{{ selectedCategoryLabel }}</text>
            <uv-icon name="arrow-down" color="#0A2146" size="34rpx" />
          </view>

          <view v-if="pickerType === 'category'" class="practice-record-dropdown">
            <view
              v-for="option in categoryOptions"
              :key="option.value"
              class="practice-record-dropdown__option"
              :class="{ 'practice-record-dropdown__option--active': option.value === selectedCategory }"
              @tap.stop="selectCategoryOption(option.value)"
            >
              <text>{{ option.label }}</text>
              <uv-icon
                v-if="option.value === selectedCategory"
                name="checkmark"
                color="#0878EE"
                size="30rpx"
              />
            </view>
          </view>
        </view>

        <view
          class="practice-record-filter__item"
          :class="{ 'practice-record-filter__item--open': pickerType === 'time' }"
          @tap.stop="toggleTimePicker"
        >
          <text class="practice-record-filter__label">练习时间</text>
          <view class="practice-record-filter__select">
            <text>{{ selectedTimeLabel }}</text>
            <uv-icon name="arrow-down" color="#0A2146" size="34rpx" />
          </view>

          <view v-if="pickerType === 'time'" class="practice-record-dropdown">
            <view
              v-for="option in timeOptions"
              :key="option.value"
              class="practice-record-dropdown__option"
              :class="{ 'practice-record-dropdown__option--active': option.value === selectedTime }"
              @tap.stop="selectTimeOption(option.value)"
            >
              <text>{{ option.label }}</text>
              <uv-icon
                v-if="option.value === selectedTime"
                name="checkmark"
                color="#0878EE"
                size="30rpx"
              />
            </view>
          </view>
        </view>
      </view>

      <view class="practice-record-list">
        <PracticeRecordCard
          v-for="record in filteredRecords"
          :key="record.id"
          :record="record"
        />

        <AppStateView
          v-if="!loadingRecords && !filteredRecords.length"
          status="empty"
          title="暂无练习记录"
          message="当前筛选条件下没有练习记录"
        />
      </view>
    </view>

    <SelfTestLoadingOverlay
      :show="loadingRecords"
      title="正在加载练习记录"
      message="请稍候，系统正在同步练习记录。"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppStateView from '@/components/AppStateView.vue'
import PracticeRecordCard from '@/components/practice/PracticeRecordCard.vue'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import { requireLogin } from '@/stores/appState'
import { fetchPracticeRecords, fetchPracticeTopics, type PracticeRecord, type PracticeTopic } from '@/services/practice'

type PracticeRecordOption = {
  label: string
  value: string
}

type PickerType = 'category' | 'time' | ''

const records = ref<PracticeRecord[]>([])
const categories = ref<PracticeTopic[]>([])
const loadingRecords = ref(false)

const timeOptions: PracticeRecordOption[] = [
  { label: '全部时间', value: 'all' },
  { label: '今日', value: 'today' },
  { label: '近7天', value: 'week' },
  { label: '近30天', value: 'month' }
]

const selectedCategory = ref('all')
const selectedTime = ref('all')
const pickerType = ref<PickerType>('')

const categoryOptions = computed<PracticeRecordOption[]>(() => {
  const options = new Map<string, string>()
  categories.value.forEach((category) => {
    const value = category.fieldType || category.id
    if (value) {
      options.set(value, category.categoryName || category.title || value)
    }
  })
  records.value.forEach((record) => {
    if (record.category) {
      options.set(record.category, record.categoryName || record.title || record.category)
    }
  })
  return [
    { label: '全部分类', value: 'all' },
    ...Array.from(options.entries()).map(([value, label]) => ({ label, value }))
  ]
})

const selectedCategoryLabel = computed(() => {
  return categoryOptions.value.find((item) => item.value === selectedCategory.value)?.label || '全部分类'
})

const selectedTimeLabel = computed(() => {
  return timeOptions.find((item) => item.value === selectedTime.value)?.label || '全部时间'
})

const filteredRecords = computed(() => {
  return records.value.filter((record) => {
    const categoryMatched = selectedCategory.value === 'all' || record.category === selectedCategory.value || record.categoryName === selectedCategory.value
    const timeMatched = selectedTime.value === 'all'
      || record.timeRange === selectedTime.value
      || (selectedTime.value === 'week' && record.timeRange === 'today')
      || (selectedTime.value === 'month' && (record.timeRange === 'today' || record.timeRange === 'week'))
    return categoryMatched && timeMatched
  })
})

const goBack = () => {
  uni.navigateBack({
    delta: 1,
    fail: () => {
      uni.reLaunch({
        url: '/pages/profile'
      })
    }
  })
}

const toggleCategoryPicker = () => {
  pickerType.value = pickerType.value === 'category' ? '' : 'category'
}

const toggleTimePicker = () => {
  pickerType.value = pickerType.value === 'time' ? '' : 'time'
}

const closePicker = () => {
  pickerType.value = ''
}

const selectCategoryOption = (value: string) => {
  selectedCategory.value = value
  closePicker()
}

const selectTimeOption = (value: string) => {
  selectedTime.value = value
  closePicker()
}

const loadRecords = async () => {
  if (loadingRecords.value) {
    return
  }
  loadingRecords.value = true
  try {
    const [nextCategories, nextRecords] = await Promise.all([
      fetchPracticeTopics(),
      fetchPracticeRecords()
    ])
    categories.value = nextCategories
    records.value = nextRecords
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '练习记录加载失败',
      icon: 'none'
    })
  } finally {
    loadingRecords.value = false
  }
}

onShow(async () => {
  if (requireLogin()) {
    await loadRecords()
  }
})
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #F8FBFF;
}

.practice-record-page {
  position: relative;
  min-height: 100vh;
  overflow-x: hidden;
  color: #0a2146;
  background: #F8FBFF;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}

.practice-record-page__bg {
  position: fixed;
  inset: 0;
  background:
    url('@/static/practice-record/contour-bottom-left.png') left -114rpx top -68rpx / 380rpx auto no-repeat,
    url('@/static/practice-record/contour-top-right.png') right -124rpx top -36rpx / 300rpx auto no-repeat,
    linear-gradient(rgba(254, 252, 247, 0.74), rgba(254, 252, 247, 0.74)),
    url('@/static/practice-start/paper-texture.jpg') center top / 320rpx 150rpx repeat;
}

.practice-record-page__content {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--app-safe-area-top) 43rpx calc(env(safe-area-inset-bottom) + 44rpx);
}

.practice-record-nav {
  position: relative;
  height: var(--app-page-header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.practice-record-nav__back,
.practice-record-nav__spacer {
  width: 54rpx;
  height: var(--app-page-header-height);
  display: flex;
  align-items: center;
  justify-content: flex-start;
  flex: 0 0 auto;
}

.practice-record-nav__title {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: block;
  color: #0a2146;
  font-size: 40rpx;
  line-height: 1.2;
  font-weight: 700;
  white-space: nowrap;
}

.practice-record-filter {
  position: relative;
  box-sizing: border-box;
  min-height: 151rpx;
  margin-top: 35rpx;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 72rpx;
  padding: 30rpx 34rpx;
  border: 1rpx solid rgba(222, 232, 242, 0.5);
  border-radius: 27rpx;
  background:
    linear-gradient(rgba(255, 255, 255, 0.74), rgba(255, 255, 255, 0.74)),
    url('@/static/practice-start/paper-texture.jpg') center / 320rpx 150rpx repeat;
  box-shadow:
    0 8rpx 20rpx rgba(26, 67, 115, 0.13),
    inset 0 1rpx 0 rgba(255, 255, 255, 0.92);
}

.practice-record-filter::after {
  content: "";
  position: absolute;
  left: 50%;
  top: 35rpx;
  bottom: 35rpx;
  width: 1rpx;
  background: #e5e6e6;
}

.practice-record-filter__item {
  position: relative;
  min-width: 0;
  z-index: 1;
}

.practice-record-filter__item--open {
  z-index: 12;
}

.practice-record-filter__label,
.practice-record-filter__select text {
  display: block;
}

.practice-record-filter__label {
  color: #0a2146;
  font-size: 26rpx;
  line-height: 32rpx;
  font-weight: 500;
}

.practice-record-filter__select {
  height: 45rpx;
  margin-top: 10rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12rpx;
  padding: 0;
  border: 0;
  background: transparent;
  color: #0878EE;
  font-size: 36rpx;
  line-height: 1;
  font-weight: 700;
}

.practice-record-filter__item--open .practice-record-filter__select {
  color: #0878EE;
}

.practice-record-filter__select text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.practice-record-dropdown {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 16rpx);
  overflow: hidden;
  border-radius: 12rpx;
  border: 1rpx solid #DCE8F5;
  background: rgba(255, 254, 251, 0.99);
  box-shadow: 0 16rpx 36rpx rgba(26, 67, 115, 0.17);
}

.practice-record-dropdown__option {
  box-sizing: border-box;
  min-height: 70rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12rpx;
  padding: 0 18rpx;
  color: #0a2146;
  font-size: 23rpx;
  line-height: 1.2;
  font-weight: 680;
  background: #ffffff;
}

.practice-record-dropdown__option + .practice-record-dropdown__option {
  border-top: 1rpx solid #E6EEF7;
}

.practice-record-dropdown__option--active {
  color: #0878EE;
  background: #F1F7FD;
}

.practice-record-dropdown__option text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.practice-record-list {
  display: flex;
  flex-direction: column;
  gap: 32rpx;
  margin-top: 32rpx;
}

@media (max-width: 360px) {
  .practice-record-page__content {
    padding-left: 39rpx;
    padding-right: 39rpx;
  }

  .practice-record-filter {
    column-gap: 64rpx;
    padding-left: 32rpx;
    padding-right: 32rpx;
  }

  .practice-record-filter__select {
    font-size: 33rpx;
  }

  .practice-record-dropdown__option {
    font-size: 21rpx;
    padding-left: 14rpx;
    padding-right: 14rpx;
  }
}
</style>
