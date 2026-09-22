<template>
  <view v-if="visible && organization" class="organization-join-dialog" @touchmove.stop.prevent>
    <view class="organization-join-dialog__mask" />

    <view
      class="organization-join-dialog__panel"
      role="dialog"
      :aria-label="title"
      @tap.stop
    >
      <button class="organization-join-dialog__close" aria-label="关闭" @tap="close">
        <uv-icon name="close" size="31rpx" color="#8b8d8f" />
      </button>

      <view class="organization-join-dialog__hero">
        <image
          class="organization-join-dialog__hero-building"
          src="/static/profile-settings/profile-organization.svg"
          mode="aspectFit"
        />
        <view class="organization-join-dialog__hero-apply">
          <image src="/static/organization-bind/organization-apply.png" mode="aspectFit" />
        </view>
      </view>

      <text class="organization-join-dialog__title">{{ title }}</text>

      <view class="organization-join-dialog__organization">
        <view class="organization-join-dialog__organization-logo-frame">
          <image
            class="organization-join-dialog__organization-logo"
            :src="organization.iconUrl"
            mode="aspectFit"
            :aria-label="`${organization.name}标志`"
          />
        </view>
        <view class="organization-join-dialog__organization-copy">
          <text class="organization-join-dialog__organization-name">{{ organization.name }}</text>
          <view class="organization-join-dialog__organization-meta">
            <text>{{ organization.tag }}</text>
            <text class="organization-join-dialog__separator">|</text>
            <text class="organization-join-dialog__certification">已认证</text>
          </view>
        </view>
      </view>

      <text class="organization-join-dialog__confirmation">{{ confirmationText }}</text>

      <view class="organization-join-dialog__form">
        <view class="organization-join-dialog__field">
          <text class="organization-join-dialog__field-label">真实姓名</text>
          <input
            v-model="form.realName"
            class="organization-join-dialog__field-input"
            maxlength="20"
            placeholder="请输入真实姓名"
            placeholder-class="organization-join-dialog__field-placeholder"
          />
        </view>
        <view class="organization-join-dialog__field">
          <text class="organization-join-dialog__field-label">身份证号</text>
          <input
            v-model="form.idCard"
            class="organization-join-dialog__field-input"
            maxlength="18"
            placeholder="请输入身份证号"
            placeholder-class="organization-join-dialog__field-placeholder"
          />
        </view>
        <view class="organization-join-dialog__field organization-join-dialog__field--sex">
          <text class="organization-join-dialog__field-label">性别</text>
          <view class="organization-join-dialog__sex-options">
            <button
              v-for="option in sexOptions"
              :key="option"
              class="organization-join-dialog__sex-option"
              :class="{ 'organization-join-dialog__sex-option--selected': form.sex === option }"
              @tap="form.sex = option"
            >{{ option }}</button>
          </view>
        </view>
      </view>

      <view class="organization-join-dialog__notice">
        <image src="/static/profile-settings/settings-security.svg" mode="aspectFit" />
        <text>提交后将由企业管理员审核，审核通过后即可使用该组织提供的题库训练内容。</text>
      </view>

      <view class="organization-join-dialog__actions">
        <button class="organization-join-dialog__cancel" @tap="close">取消</button>
        <button class="organization-join-dialog__confirm" @tap="confirm">
          <image src="/static/organization-bind/organization-apply.png" mode="aspectFit" />
          <text>提交申请</text>
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { OrganizationSummary } from '@/services/organization'

const sexOptions = ['男', '女', '其他'] as const
type OrganizationJoinApplicationPayload = {
  realName: string
  idCard: string
  sex: string
}

const props = withDefaults(defineProps<{
  visible: boolean
  organization: OrganizationSummary | null
  title?: string
  confirmationText: string
}>(), {
  title: '申请加入组织'
})

const emit = defineEmits<{
  close: []
  confirm: [payload: OrganizationJoinApplicationPayload]
}>()

const form = reactive({ realName: '', idCard: '', sex: '' })

watch(() => props.visible, (visible) => {
  if (!visible) {
    form.realName = ''
    form.idCard = ''
    form.sex = ''
  }
})

function close() {
  emit('close')
}

function confirm() {
  const realName = form.realName.trim()
  const idCard = form.idCard.trim()
  if (!realName) {
    uni.showToast({ title: '请输入真实姓名', icon: 'none' })
    return
  }
  if (!/^[\u4e00-\u9fa5A-Za-z·\s]{2,20}$/.test(realName)) {
    uni.showToast({ title: '请输入正确的真实姓名', icon: 'none' })
    return
  }
  if (!/^[1-9]\d{16}[\dXx]$/.test(idCard)) {
    uni.showToast({ title: '请输入正确的身份证号', icon: 'none' })
    return
  }
  if (!form.sex) {
    uni.showToast({ title: '请选择性别', icon: 'none' })
    return
  }
  emit('confirm', { realName, idCard, sex: form.sex })
}
</script>

<style scoped lang="scss">
.organization-join-dialog {
  position: fixed;
  z-index: 1300;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  padding: 32rpx;
}

.organization-join-dialog__mask {
  position: absolute;
  inset: 0;
  background: rgba(15, 18, 20, 0.58);
  backdrop-filter: blur(1rpx);
}

.organization-join-dialog__panel {
  position: relative;
  box-sizing: border-box;
  width: min(620rpx, calc(100vw - 64rpx));
  padding: 29.5rpx 26rpx 22.5rpx;
  border-radius: 16rpx;
  background: #ffffff;
  box-shadow: 0 24rpx 64rpx rgba(0, 0, 0, 0.24);
  transform: translate(2.5rpx, 21.5rpx);
}

.organization-join-dialog__close,
.organization-join-dialog__cancel,
.organization-join-dialog__confirm {
  margin: 0;
  padding: 0;
}

.organization-join-dialog__close::after,
.organization-join-dialog__cancel::after,
.organization-join-dialog__confirm::after {
  border: 0;
}

.organization-join-dialog__close {
  position: absolute;
  top: 19rpx;
  right: 18rpx;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38rpx;
  height: 38rpx;
  border: 1rpx solid #e1e1df;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.78);
}

.organization-join-dialog__hero {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 110rpx;
  height: 110rpx;
  margin: 5rpx auto 0;
  border-radius: 50%;
  background: #E9F3FF;
  transform: translate(-5rpx, -2rpx);
}

.organization-join-dialog__hero-building {
  display: block;
  width: 62rpx;
  height: 70rpx;
  filter: hue-rotate(10deg) brightness(1.1);
  transform: translate(-5rpx, -5rpx) scale(1.27, 0.94);
}

.organization-join-dialog__hero-apply {
  position: absolute;
  right: 11rpx;
  bottom: 25rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 43rpx;
  height: 43rpx;
  border-radius: 50%;
  background: #E9F3FF;
}

.organization-join-dialog__hero-apply image {
  display: block;
  width: 35rpx;
  height: 35rpx;
  transform: translateX(2rpx) scale(1.08, 0.82);
  transform-origin: center bottom;
}

.organization-join-dialog__title,
.organization-join-dialog__organization-name,
.organization-join-dialog__confirmation,
.organization-join-dialog__notice text,
.organization-join-dialog__confirm text {
  display: block;
}

.organization-join-dialog__title {
  margin-top: 9rpx;
  color: #071c2f;
  font-size: 28rpx;
  line-height: 42rpx;
  font-weight: 500;
  text-align: center;
  transform: translate(-8rpx, -2rpx);
}

.organization-join-dialog__organization {
  display: grid;
  grid-template-columns: 72rpx minmax(0, 1fr);
  column-gap: 10rpx;
  align-items: center;
  height: 72rpx;
  margin-top: 9rpx;
}

.organization-join-dialog__organization-logo-frame {
  display: block;
  width: 72rpx;
  height: 72rpx;
  overflow: hidden;
}

.organization-join-dialog__organization-logo {
  display: block;
  width: 100rpx;
  height: 100rpx;
  transform: translate(-17rpx, -17rpx);
}

.organization-join-dialog__organization-copy {
  min-width: 0;
}

.organization-join-dialog__organization-name {
  overflow: hidden;
  color: #101821;
  font-size: 20.3rpx;
  line-height: 30rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
  transform: translate(3rpx, 1rpx);
}

.organization-join-dialog__organization-meta {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-top: 3rpx;
  color: #999999;
  font-size: 17rpx;
  line-height: 26rpx;
  white-space: nowrap;
  transform: translate(1rpx, 3rpx);
}

.organization-join-dialog__separator {
  color: #aaa8a6;
}

.organization-join-dialog__certification {
  color: #12aa58;
}

.organization-join-dialog__confirmation {
  margin-top: 16rpx;
  margin-left: 7rpx;
  overflow-wrap: anywhere;
  color: #1b252f;
  font-size: 19.1rpx;
  line-height: 30rpx;
  font-weight: 400;
  transform: translate(2rpx, -2rpx);
}

.organization-join-dialog__notice {
  display: grid;
  grid-template-columns: 42rpx minmax(0, 1fr);
  column-gap: 8rpx;
  align-items: center;
  box-sizing: border-box;
  min-height: 84rpx;
  margin-top: 18rpx;
  padding: 12rpx 3rpx 12rpx 17rpx;
  border-radius: 12rpx;
  background: #EAF4FF;
}

.organization-join-dialog__form {
  display: grid;
  gap: 12rpx;
  margin-top: 18rpx;
}

.organization-join-dialog__field {
  display: grid;
  grid-template-columns: 132rpx minmax(0, 1fr);
  align-items: center;
  min-height: 68rpx;
  border-bottom: 1rpx solid #E6EEF7;
}

.organization-join-dialog__field-label {
  color: #17212b;
  font-size: 19rpx;
}

.organization-join-dialog__field-input {
  min-width: 0;
  height: 60rpx;
  color: #17212b;
  font-size: 19rpx;
}

.organization-join-dialog__field-placeholder {
  color: #a9b3c2;
}

.organization-join-dialog__sex-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10rpx;
}

.organization-join-dialog__sex-option {
  height: 48rpx;
  margin: 0;
  padding: 0;
  border: 1rpx solid #dfe9f4;
  border-radius: 8rpx;
  background: #ffffff;
  color: #5c5d60;
  font-size: 18rpx;
  line-height: 46rpx;
}

.organization-join-dialog__sex-option::after {
  border: 0;
}

.organization-join-dialog__sex-option--selected {
  border-color: #0868F4;
  background: #eaf4ff;
  color: #005BD8;
}

.organization-join-dialog__notice image {
  display: block;
  width: 42rpx;
  height: 46rpx;
  transform: translate(-3rpx, -4rpx) scaleY(0.9);
}

.organization-join-dialog__notice text {
  color: #202b34;
  font-size: 15.5rpx;
  line-height: 27rpx;
  font-weight: 400;
  transform: translateY(-1rpx);
}

.organization-join-dialog__actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.12fr);
  gap: 24rpx;
  margin-top: 24rpx;
}

.organization-join-dialog__cancel,
.organization-join-dialog__confirm {
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  height: 60rpx;
  border-radius: 12rpx;
  font-size: 24rpx;
  line-height: 60rpx;
  font-weight: 500;
}

.organization-join-dialog__cancel {
  border: 1rpx solid #D8E4F0;
  background: #ffffff;
  color: #17212b;
}

.organization-join-dialog__confirm {
  gap: 9rpx;
  border: 0;
  background: #0868F4;
  color: #ffffff;
  box-shadow: 0 8rpx 18rpx rgba(0, 91, 216, 0.18);
}

.organization-join-dialog__confirm image {
  display: block;
  width: 28rpx;
  height: 28rpx;
  filter: brightness(0) invert(1);
}

.organization-join-dialog__confirm text {
  line-height: 1;
}
</style>
