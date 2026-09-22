<template>
  <view class="enterprise-students-page" :style="$appSafeAreaStyle">
    <image
      v-if="canViewStudentManagement"
      class="enterprise-home-hero"
      src="/static/enterprise-students/enterprise-home-hero-reference.png"
      mode="widthFix"
      aria-label="小技企业学员管理，企业管理，高效审核"
    />
    <image
      v-if="canViewStudentManagement"
      class="enterprise-home-scene"
      src="/static/enterprise-students/enterprise-home-scene-reference.png"
      mode="widthFix"
      aria-hidden="true"
    />

    <view v-if="canViewStudentManagement" class="students-content">
      <view class="students-hero sr-only">
        <text class="students-hero__title">小技企业学员管理</text>
        <text class="students-hero__subtitle">企业管理 · 高效审核</text>
      </view>

      <view class="filter-card">
        <view class="filter-section">
          <view class="filter-title">
            <uv-icon name="account" color="#0868F4" size="42rpx" />
            <text>学员名称筛选</text>
          </view>
          <view class="filter-field">
            <uv-icon name="search" color="#8f909d" size="40rpx" />
            <input
              v-model="keyword"
              class="filter-field__input"
              maxlength="20"
              placeholder="请输入学员昵称或手机号"
              placeholder-class="filter-field__placeholder"
            />
          </view>
        </view>

        <view class="filter-divider" />

        <view class="filter-section">
          <view class="filter-title">
            <uv-icon name="calendar" color="#0868F4" size="42rpx" />
            <text>申请时间筛选</text>
          </view>
          <view class="filter-field" @tap="openDatePicker">
            <uv-icon name="calendar" color="#8f909d" size="40rpx" />
            <text class="filter-field__date">{{ dateFilterLabel }}</text>
            <uv-icon name="arrow-down" color="#8f909d" size="24rpx" />
          </view>
        </view>
      </view>

      <view class="applications-panel">
        <view class="applications-heading">
          <view class="applications-heading__accent" />
          <text>加入申请</text>
        </view>

        <view class="students-list">
          <template v-if="!loading">
            <view
              v-for="student in filteredStudents"
              :key="student.id"
              class="student-card"
              :class="`student-card--${student.status}`"
            >
              <image
                class="student-avatar"
                src="/static/enterprise-students/enterprise-home-avatar-reference.png"
                mode="aspectFill"
              />
              <view class="student-info">
                <text class="student-name">{{ student.name }}</text>
                <text class="student-phone">{{ student.phone }}</text>
                <view class="student-time">
                  <text>申请时间：{{ student.appliedAt.slice(0, 16) }}</text>
                </view>
              </view>
              <view class="student-actions">
                <text class="audit-state-label" :class="`audit-state-label--${student.status}`">
                  {{ statusLabelMap[student.status] }}
                </text>
                <view v-if="student.status === 'pending'" class="audit-buttons">
                  <button
                    class="audit-button audit-button--agree"
                    :disabled="actionLoadingId === student.id"
                    @tap="approveStudent(student.id)"
                  >
                    <uv-icon name="checkmark" color="#ffffff" size="22rpx" bold />
                    <text>{{ actionLoadingId === student.id ? '处理中' : '同意' }}</text>
                  </button>
                  <button
                    class="audit-button audit-button--reject"
                    :disabled="actionLoadingId === student.id"
                    @tap="rejectStudent(student.id)"
                  >
                    <uv-icon name="close" color="#ff241b" size="22rpx" bold />
                    <text>{{ actionLoadingId === student.id ? '处理中' : '拒绝' }}</text>
                  </button>
                </view>
                <view v-else class="audit-status" :class="`audit-status--${student.status}`">
                  <uv-icon
                    :name="student.status === 'approved' ? 'checkmark' : 'close'"
                    :color="student.status === 'approved' ? '#ffffff' : '#aaa7a5'"
                    size="25rpx"
                    bold
                  />
                </view>
              </view>
            </view>

            <view v-if="filteredStudents.length === 0" class="empty-state">
              <text>暂无加入申请</text>
            </view>
          </template>
        </view>
      </view>
    </view>

    <SelfTestLoadingOverlay
      :show="canViewStudentManagement && loading"
      title="学员审核列表加载中"
      message="正在同步学员加入申请，请稍候。"
    />

    <view v-if="canViewStudentManagement && datePickerVisible" class="date-picker-mask" @tap="closeDatePicker" @touchmove.stop.prevent>
      <view class="date-picker-panel" @tap.stop @touchmove.stop>
        <view class="date-picker-header">
          <text class="date-picker-header__title">申请时间筛选</text>
          <button class="date-picker-header__clear" @tap="clearDateFilter">清空</button>
        </view>

        <view class="date-range-row">
          <view
            class="date-range-picker"
            :class="{ 'date-range-picker--active': activeDateField === 'start' }"
            @tap="switchDateField('start')"
          >
            <view class="date-range-field">
              <text class="date-range-field__label">开始时间</text>
              <text class="date-range-field__value" :class="{ 'date-range-field__value--placeholder': !rangeFieldValue('start') }">
                {{ rangeFieldValue('start') || '点击选择' }}
              </text>
            </view>
          </view>

          <text class="date-range-separator">至</text>

          <view
            class="date-range-picker"
            :class="{ 'date-range-picker--active': activeDateField === 'end' }"
            @tap="switchDateField('end')"
          >
            <view class="date-range-field">
              <text class="date-range-field__label">结束时间</text>
              <text class="date-range-field__value" :class="{ 'date-range-field__value--placeholder': !rangeFieldValue('end') }">
                {{ rangeFieldValue('end') || '点击选择' }}
              </text>
            </view>
          </view>
        </view>

        <picker-view
          class="date-inline-picker"
          indicator-style="height: 72rpx;"
          mask-style="background: transparent;"
          :value="pickerValue"
          @change="handlePickerViewChange"
        >
          <picker-view-column v-for="(column, columnIndex) in datePickerRange" :key="columnIndex">
            <view v-for="item in column" :key="item" class="date-inline-picker__item">
              <text>{{ item }}</text>
            </view>
          </picker-view-column>
        </picker-view>

        <button class="date-picker-confirm" @tap="confirmDateFilter">确定</button>
      </view>
    </view>
    <HomeProfileTabBar class="enterprise-home-tabbar" active="home" />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import HomeProfileTabBar from '@/components/HomeProfileTabBar.vue'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import { auditCompanyStudent, fetchCompanyStudentAudits, type CompanyStudentAuditStatus } from '@/services/customerAuth'
import { appState, requireLogin } from '@/stores/appState'

type StudentApply = {
  id: number
  name: string
  phone: string
  phoneKeyword: string
  appliedAt: string
  status: StudentApplyStatus
}

type StudentApplyStatus = 'pending' | 'approved' | 'rejected'
type DateField = 'start' | 'end'
type DateDraft = {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  second: number
}

const statusOrder: Record<StudentApplyStatus, number> = {
  pending: 0,
  approved: 1,
  rejected: 2
}

const statusLabelMap: Record<StudentApplyStatus, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已拒绝'
}

const keyword = ref('')
const startAt = ref('')
const endAt = ref('')
const draftStartAt = ref('')
const draftEndAt = ref('')
const activeDateField = ref<DateField>('start')
const datePickerVisible = ref(false)
const pickerValue = ref<number[]>([])
const students = ref<StudentApply[]>([])
const loading = ref(false)
const actionLoadingId = ref<number | null>(null)
const canViewStudentManagement = computed(() =>
  appState.loginIdentity === 'enterprise' && appState.userSession?.hasWtPost === true
)

const yearOptions = createRange(2020, new Date().getFullYear() + 1)
const hourOptions = createRange(0, 23)
const minuteOptions = createRange(0, 59)
const secondOptions = createRange(0, 59)
const datePickerRange = [
  yearOptions.map((item) => `${item}年`),
  createRange(1, 12).map((item) => `${item}月`),
  createRange(1, 31).map((item) => `${item}日`),
  hourOptions.map((item) => `${item}时`),
  minuteOptions.map((item) => `${item}分`),
  secondOptions.map((item) => `${item}秒`)
]

const dateFilterLabel = computed(() => {
  if (!startAt.value && !endAt.value) {
    return '请选择申请开始时间 ~ 请选择申请结束时间'
  }
  return `${startAt.value ? startAt.value.slice(0, 10) : '开始日期'}  ~  ${endAt.value ? endAt.value.slice(0, 10) : '结束日期'}`
})

const filteredStudents = computed(() => {
  const value = keyword.value.trim()
  const result = value
    ? students.value.filter((item) => item.name.includes(value) || item.phone.includes(value) || item.phoneKeyword.includes(value))
    : students.value

  const startTime = startAt.value ? parseDateTime(startAt.value).getTime() : null
  const endTime = endAt.value ? parseDateTime(endAt.value).getTime() : null

  return result.filter((item) => {
    const itemTime = parseDateTime(item.appliedAt).getTime()
    if (startTime !== null && itemTime < startTime) {
      return false
    }
    if (endTime !== null && itemTime > endTime) {
      return false
    }
    return true
  }).sort((left, right) => {
    const statusDiff = statusOrder[left.status] - statusOrder[right.status]
    if (statusDiff !== 0) {
      return statusDiff
    }
    return right.appliedAt.localeCompare(left.appliedAt)
  })
})

onShow(() => {
  if (!requireLogin()) {
    return
  }
  if (appState.loginIdentity !== 'enterprise') {
    uni.reLaunch({ url: '/pages/home' })
    return
  }
  if (!canViewStudentManagement.value) {
    resetStudents()
    return
  }
  void loadStudents()
})

async function approveStudent(id: number) {
  await auditStudent(id, 2, '已审核')
}

async function rejectStudent(id: number) {
  await auditStudent(id, 3, '已拒绝')
}

async function loadStudents() {
  if (!canViewStudentManagement.value) {
    resetStudents()
    return
  }

  loading.value = true
  try {
    const data = await fetchCompanyStudentAudits()
    students.value = Array.isArray(data.list) ? data.list.map(mapStudentAuditItem) : []
  } catch {
    students.value = []
  } finally {
    loading.value = false
  }
}

async function auditStudent(id: number, auditStatus: 2 | 3, successTitle: string) {
  if (!canViewStudentManagement.value) {
    return
  }

  if (actionLoadingId.value !== null) {
    return
  }
  actionLoadingId.value = id
  try {
    await auditCompanyStudent({ id, auditStatus })
    await loadStudents()
    uni.showToast({ title: successTitle, icon: 'success' })
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '审核处理失败，请稍后重试',
      icon: 'none'
    })
  } finally {
    actionLoadingId.value = null
  }
}

function resetStudents() {
  students.value = []
  loading.value = false
  actionLoadingId.value = null
  datePickerVisible.value = false
}

function createRange(start: number, end: number) {
  return Array.from({ length: end - start + 1 }, (_, index) => start + index)
}

function createDateDraft(value = ''): DateDraft {
  const date = value ? parseDateTime(value) : new Date()
  return {
    year: date.getFullYear(),
    month: date.getMonth() + 1,
    day: date.getDate(),
    hour: date.getHours(),
    minute: date.getMinutes(),
    second: date.getSeconds()
  }
}

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate()
}

function formatDateDraft(draft: DateDraft) {
  const pad = (value: number) => `${value}`.padStart(2, '0')
  return `${draft.year}-${pad(draft.month)}-${pad(draft.day)} ${pad(draft.hour)}:${pad(draft.minute)}:${pad(draft.second)}`
}

function parseDateTime(value: string) {
  const normalized = value.length === 16 ? `${value}:00` : value
  const [datePart, timePart = '00:00:00'] = normalized.split(' ')
  const [year, month, day] = datePart.split('-').map(Number)
  const [hour = 0, minute = 0, second = 0] = timePart.split(':').map(Number)
  return new Date(year, month - 1, day, hour, minute, second)
}

function openDatePicker() {
  draftStartAt.value = startAt.value
  draftEndAt.value = endAt.value
  activeDateField.value = startAt.value && !endAt.value ? 'end' : 'start'
  syncPickerValue()
  datePickerVisible.value = true
}

function closeDatePicker() {
  datePickerVisible.value = false
}

function switchDateField(field: DateField) {
  activeDateField.value = field
  syncPickerValue()
}

function rangeFieldValue(field: DateField) {
  return field === 'start' ? draftStartAt.value : draftEndAt.value
}

function clearDateFilter() {
  if (activeDateField.value === 'start') {
    startAt.value = ''
    draftStartAt.value = ''
    syncPickerValue()
    return
  }

  endAt.value = ''
  draftEndAt.value = ''
  syncPickerValue()
}

function resolvePickerIndexes(field: DateField) {
  const draft = createDateDraft(field === 'start' ? draftStartAt.value : draftEndAt.value)
  return [
    Math.max(yearOptions.indexOf(draft.year), 0),
    draft.month - 1,
    draft.day - 1,
    draft.hour,
    draft.minute,
    draft.second
  ]
}

function syncPickerValue() {
  pickerValue.value = resolvePickerIndexes(activeDateField.value)
}

function handlePickerViewChange(event: { detail: { value: number[] } }) {
  const indexes = event.detail.value
  const year = yearOptions[indexes[0]] || yearOptions[0]
  const month = (indexes[1] || 0) + 1
  const day = Math.min((indexes[2] || 0) + 1, getDaysInMonth(year, month))
  const nextIndexes = [
    Math.max(yearOptions.indexOf(year), 0),
    month - 1,
    day - 1,
    indexes[3] || 0,
    indexes[4] || 0,
    indexes[5] || 0
  ]
  const value = formatDateDraft({
    year,
    month,
    day,
    hour: indexes[3] || 0,
    minute: indexes[4] || 0,
    second: indexes[5] || 0
  })

  pickerValue.value = nextIndexes

  if (activeDateField.value === 'start') {
    draftStartAt.value = value
    return
  }
  draftEndAt.value = value
}

function confirmDateFilter() {
  if (draftStartAt.value && draftEndAt.value && parseDateTime(draftStartAt.value).getTime() > parseDateTime(draftEndAt.value).getTime()) {
    uni.showToast({ title: '开始时间不能晚于结束时间', icon: 'none' })
    return
  }

  startAt.value = draftStartAt.value
  endAt.value = draftEndAt.value
  datePickerVisible.value = false
}

function mapStudentAuditItem(item: CompanyStudentAuditStatus): StudentApply {
  return {
    id: Number(item.id),
    name: item.studentName || '未命名学员',
    phone: maskPhone(item.studentPhone || ''),
    phoneKeyword: item.studentPhone || '',
    appliedAt: normalizeDateTime(item.applyTime),
    status: mapStudentStatus(item.auditStatus)
  }
}

function mapStudentStatus(auditStatus: number): StudentApplyStatus {
  if (auditStatus === 2) {
    return 'approved'
  }
  if (auditStatus === 3) {
    return 'rejected'
  }
  return 'pending'
}

function normalizeDateTime(value?: string | number) {
  if (!value) {
    return ''
  }
  if (typeof value === 'number') {
    return formatDate(new Date(value))
  }
  return value.replace('T', ' ').slice(0, 19)
}

function formatDate(date: Date) {
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  const pad = (value: number) => `${value}`.padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function maskPhone(phone: string) {
  if (!phone) {
    return ''
  }
  if (phone.length < 7) {
    return phone
  }
  return `${phone.slice(0, 3)}****${phone.slice(-4)}`
}
</script>

<style scoped lang="scss">
page {
  min-height: 100%;
  background: #F7FAFE;
}

button::after {
  border: 0;
}

.enterprise-students-page {
  position: relative;
  box-sizing: border-box;
  width: 100%;
  max-width: 430px;
  min-height: 100vh;
  margin: 0 auto;
  overflow-x: hidden;
  background: #F7FAFE;
  color: #0a1b42;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}

.enterprise-home-hero,
.enterprise-home-scene {
  position: absolute;
  z-index: 0;
  left: 0;
  display: block;
  width: 100%;
  height: auto;
  pointer-events: none;
}

.enterprise-home-hero {
  top: calc(var(--app-safe-area-top-extra) - 18rpx);
}

.enterprise-home-scene {
  top: calc(892rpx + var(--app-safe-area-top-extra));
}

.students-content {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  min-height: 100vh;
  padding: calc(232rpx + var(--app-safe-area-top-extra)) 27rpx calc(env(safe-area-inset-bottom) + 124rpx) 23rpx;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}

.filter-card,
.applications-panel {
  box-sizing: border-box;
  border: 1rpx solid rgba(78, 108, 138, 0.1);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 9rpx 23rpx rgba(24, 64, 108, 0.1);
  backdrop-filter: blur(3rpx);
}

.filter-card {
  min-height: 374rpx;
  padding: 26rpx;
  border-radius: 26rpx;
}

.filter-title,
.applications-heading {
  display: flex;
  align-items: center;
}

.filter-title {
  gap: 16rpx;
  color: #091b43;
  font-size: 29rpx;
  line-height: 38rpx;
  font-weight: 800;
}

.filter-title text,
.filter-field__date,
.student-name,
.student-phone,
.student-time text,
.applications-heading text,
.empty-state text {
  display: block;
}

.filter-field {
  display: flex;
  box-sizing: border-box;
  height: 75rpx;
  margin-top: 20rpx;
  padding: 0 23rpx;
  align-items: center;
  gap: 19rpx;
  border: 2rpx solid #D8E4F0;
  border-radius: 14rpx;
  background: rgba(255, 255, 255, 0.76);
}

.filter-field__input {
  min-width: 0;
  height: 73rpx;
  flex: 1;
  color: #3a3440;
  font-size: 25rpx;
  line-height: 73rpx;
}

.filter-field__placeholder,
.filter-field__date {
  color: #8f909f;
  font-size: 24rpx;
  font-weight: 400;
}

.filter-field__date {
  min-width: 0;
  overflow: hidden;
  flex: 1;
  line-height: 73rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.filter-divider {
  height: 1rpx;
  margin: 33rpx 0 27rpx;
  background: repeating-linear-gradient(90deg, #DFE9F4 0 11rpx, transparent 11rpx 20rpx);
}

.applications-panel {
  min-height: 264rpx;
  margin-top: 16rpx;
  padding: 19rpx 17rpx 22rpx 18rpx;
  border-radius: 26rpx;
}

.applications-heading {
  height: 42rpx;
  gap: 15rpx;
  color: #091b43;
  font-size: 28rpx;
  line-height: 42rpx;
  font-weight: 800;
  margin-left: 10rpx;
}

.applications-heading__accent {
  width: 5rpx;
  height: 29rpx;
  flex: 0 0 auto;
  border-radius: 99rpx;
  background: #0868F4;
}

.students-list {
  display: flex;
  flex-direction: column;
  gap: 13rpx;
  margin-top: 17rpx;
}

.student-card {
  position: relative;
  box-sizing: border-box;
  min-height: 160rpx;
  overflow: hidden;
  border: 1rpx solid rgba(85, 113, 142, 0.11);
  border-radius: 20rpx;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 7rpx 18rpx rgba(26, 64, 105, 0.09);
}

.student-avatar {
  position: absolute;
  top: 24rpx;
  left: 8rpx;
  display: block;
  width: 106rpx;
  height: 106rpx;
  border-radius: 50%;
}

.student-info {
  position: absolute;
  top: 22rpx;
  left: 128rpx;
  width: 250rpx;
  min-width: 0;
}

.student-name {
  max-width: 160rpx;
  overflow: hidden;
  color: #081b42;
  font-size: 29rpx;
  line-height: 36rpx;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.student-phone {
  margin-top: 7rpx;
  color: #5e6377;
  font-size: 24rpx;
  line-height: 31rpx;
  font-weight: 400;
}

.student-time {
  margin-top: 7rpx;
  color: #696d7e;
  font-size: 21rpx;
  line-height: 28rpx;
  white-space: nowrap;
}

.student-time text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.student-actions {
  position: absolute;
  z-index: 2;
  top: 25rpx;
  right: 17rpx;
  width: 230rpx;
}

.audit-state-label {
  position: absolute;
  top: 0;
  left: -109rpx;
  display: block;
  box-sizing: border-box;
  width: max-content;
  height: 38rpx;
  margin-left: 0;
  padding: 0 9rpx;
  border: 1rpx solid #D4E8FC;
  border-radius: 10rpx;
  background: #F2F7FC;
  color: #005BD8;
  font-size: 21rpx;
  line-height: 36rpx;
  font-weight: 500;
}

.audit-state-label--approved,
.audit-state-label--rejected {
  right: 0;
  left: auto;
}

.audit-state-label--rejected {
  border-color: #DFE9F4;
  background: #f8fbff;
  color: #6f8098;
}

.audit-buttons {
  position: absolute;
  top: 31rpx;
  left: 0;
  display: grid;
  width: 100%;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 11rpx;
  margin-top: 0;
}

.audit-button {
  display: flex;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  height: 58rpx;
  margin: 0;
  padding: 0 8rpx;
  align-items: center;
  justify-content: center;
  gap: 7rpx;
  border-radius: 13rpx;
  font-size: 23rpx;
  line-height: 56rpx;
  font-weight: 500;
}

.audit-button text {
  display: block;
  overflow: hidden;
  line-height: 56rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audit-button--agree {
  border: 1rpx solid #0868F4;
  background: #0868F4;
  color: #ffffff;
  box-shadow: 0 7rpx 15rpx rgba(8, 104, 244, 0.2);
}

.audit-button--reject {
  border: 2rpx solid #ff241b;
  background: #ffffff;
  color: #ff241b;
}

.audit-button :deep(.uv-icon) {
  display: flex;
  box-sizing: border-box;
  width: 26rpx;
  height: 26rpx;
  align-items: center;
  justify-content: center;
  border: 2rpx solid currentColor;
  border-radius: 50%;
}

.audit-status {
  display: flex;
  width: 48rpx;
  height: 48rpx;
  margin: 15rpx 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.audit-status--approved {
  background: #0868F4;
}

.audit-status--rejected {
  border: 2rpx solid #aaa7a5;
}

.empty-state {
  box-sizing: border-box;
  min-height: 132rpx;
  padding: 33rpx 20rpx;
  color: #898995;
  font-size: 24rpx;
  line-height: 32rpx;
  text-align: center;
}

.date-picker-mask {
  position: fixed;
  z-index: 999;
  inset: 0;
  display: flex;
  align-items: flex-end;
  background: rgba(13, 31, 54, 0.38);
}

.date-picker-panel {
  box-sizing: border-box;
  width: 100%;
  padding: 28rpx 28rpx calc(env(safe-area-inset-bottom) + 28rpx);
  border-radius: 28rpx 28rpx 0 0;
  background: #FFFFFF;
  box-shadow: 0 -20rpx 48rpx rgba(23, 59, 100, 0.16);
}

.date-picker-header {
  display: flex;
  height: 58rpx;
  align-items: center;
  justify-content: space-between;
}

.date-picker-header__title {
  color: #0A2146;
  font-size: 31rpx;
  font-weight: 800;
}

.date-picker-header__clear {
  width: 104rpx;
  height: 54rpx;
  margin: 0;
  padding: 0;
  border-radius: 12rpx;
  background: rgba(8, 120, 238, 0.08);
  color: #0878EE;
  font-size: 24rpx;
  line-height: 54rpx;
}

.date-range-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 42rpx minmax(0, 1fr);
  gap: 12rpx;
  margin-top: 30rpx;
  align-items: end;
}

.date-range-field {
  min-width: 0;
  padding-bottom: 14rpx;
  border-bottom: 2rpx solid #D2E0ED;
}

.date-range-picker--active .date-range-field {
  border-bottom-color: #0878EE;
}

.date-range-field__label,
.date-range-field__value,
.date-range-separator {
  display: block;
}

.date-range-field__label {
  color: #657A91;
  font-size: 23rpx;
}

.date-range-picker--active .date-range-field__label {
  color: #0878EE;
}

.date-range-field__value {
  min-height: 38rpx;
  margin-top: 12rpx;
  overflow: hidden;
  color: #0A2146;
  font-size: 21rpx;
  line-height: 38rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.date-range-field__value--placeholder {
  color: #8ea4ba;
}

.date-range-separator {
  height: 52rpx;
  color: #657A91;
  font-size: 27rpx;
  line-height: 52rpx;
  text-align: center;
}

.date-inline-picker {
  width: 100%;
  height: 216rpx;
  margin-top: 8rpx;
  overflow: hidden;
}

.date-inline-picker__item {
  display: flex;
  box-sizing: border-box;
  height: var(--picker-view-column-indicator-height, 72rpx) !important;
  align-items: center;
  justify-content: center;
  color: #0A2146;
  font-size: 23rpx;
  line-height: var(--picker-view-column-indicator-height, 72rpx) !important;
  text-align: center;
}

.date-inline-picker__item text {
  display: block;
  width: 100%;
  text-align: center;
}

.date-picker-confirm {
  width: 100%;
  height: 76rpx;
  margin: 24rpx 0 0;
  padding: 0;
  border-radius: 15rpx;
  background: #0868F4;
  color: #ffffff;
  font-size: 28rpx;
  line-height: 76rpx;
  box-shadow: 0 10rpx 22rpx rgba(8, 120, 238, 0.2);
}

@media (max-width: 370px) {
  .filter-field__placeholder,
  .filter-field__date {
    font-size: 22rpx;
  }

  .student-actions {
    width: 224rpx;
  }
}

</style>
