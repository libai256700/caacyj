<template>
  <view class="enterprise-register-page" :style="$appSafeAreaStyle">
    <view class="enterprise-register-page__content">
      <view class="register-header">
        <button class="register-header__back" @tap="goBack">
          <uv-icon name="arrow-left" color="#122942" size="44rpx" />
        </button>
        <text class="register-header__title">企业注册</text>
      </view>

      <view class="register-card">
        <view class="register-section-title">
          <view class="register-section-title__accent" />
          <text class="register-section-title__text">基础信息</text>
        </view>

        <view class="register-field">
          <text class="register-field__label">企业名称</text>
          <input
            v-model="form.enterpriseName"
            class="register-field__input"
            maxlength="60"
            placeholder="请输入企业名称"
            placeholder-class="register-field__placeholder"
          />
        </view>

        <view class="register-field">
          <text class="register-field__label">统一社会信用代码</text>
          <input
            v-model="form.unifiedSocialCreditCode"
            class="register-field__input"
            maxlength="18"
            placeholder="请输入统一社会信用代码"
            placeholder-class="register-field__placeholder"
          />
        </view>

        <view class="register-field">
          <text class="register-field__label">法人姓名</text>
          <input
            v-model="form.legalPersonName"
            class="register-field__input"
            maxlength="20"
            placeholder="请输入法人姓名"
            placeholder-class="register-field__placeholder"
          />
        </view>

        <view class="register-field">
          <text class="register-field__label">法人身份证号</text>
          <input
            v-model="form.legalPersonId"
            class="register-field__input"
            maxlength="18"
            placeholder="请输入法人身份证号"
            placeholder-class="register-field__placeholder"
          />
        </view>

        <view class="register-field">
          <text class="register-field__label">联系人姓名</text>
          <input
            v-model="form.contactName"
            class="register-field__input"
            maxlength="20"
            placeholder="请输入联系人姓名"
            placeholder-class="register-field__placeholder"
          />
        </view>

        <view class="register-field">
          <text class="register-field__label">联系人手机号</text>
          <input
            v-model="form.contactPhone"
            class="register-field__input"
            type="number"
            maxlength="11"
            placeholder="请输入联系人手机号"
            placeholder-class="register-field__placeholder"
          />
        </view>
      </view>

      <view class="register-card register-card--upload">
        <view class="register-section-title">
          <view class="register-section-title__accent" />
          <text class="register-section-title__text">营业执照上传</text>
        </view>

        <view class="license-upload">
          <view class="license-preview">
            <view class="license-preview__paper" :class="{ 'license-preview__paper--image': Boolean(licenseFilePath) }">
              <image
                v-if="licenseFilePath"
                :src="licenseFilePath"
                class="license-preview__image"
                mode="aspectFit"
              />
              <image
                v-else
                src="/static/enterprise-register/business-license-placeholder.png"
                class="license-preview__placeholder"
                mode="aspectFit"
              />
            </view>
            <view v-if="licenseUploaded" class="license-preview__check">
              <view class="license-preview__check-mark" />
            </view>
          </view>

          <view class="license-details">
            <view class="license-meta">
              <text class="license-meta__title">营业执照</text>
              <text class="license-preview__name">{{ licenseFileName }}</text>
            </view>

            <view class="license-actions">
              <button class="license-actions__button license-actions__button--camera" @tap="chooseLicense('camera')">
                <uv-icon name="camera" color="#167EE8" size="31rpx" />
                <text class="license-actions__text">拍照上传</text>
              </button>
              <button class="license-actions__button license-actions__button--album" @tap="chooseLicense('album')">
                <uv-icon name="photo" color="#167EE8" size="31rpx" />
                <text class="license-actions__text">相册上传</text>
              </button>
            </view>
          </view>
        </view>
      </view>

      <button class="register-submit" :loading="submitting" :disabled="submitting" @tap="submitRegistration">
        {{ submitting ? '提交中...' : '提交审核' }}
      </button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { reactive, computed, ref } from 'vue'
import { appState, clearUserSession, setEnterpriseRegistration } from '@/stores/appState'
import {
  saveEnterpriseAudit,
  saveEnterpriseAuditForm,
  submitEnterpriseAudit,
  submitEnterpriseAuditForm,
  uploadEnterpriseLicenseImage
} from '@/services/customerAuth'

type UploadSource = 'camera' | 'album'
type SelectedLicenseFile = File | Blob | null

const form = reactive({
  enterpriseName: '',
  unifiedSocialCreditCode: '',
  legalPersonName: '',
  legalPersonId: '',
  contactName: '',
  contactPhone: '',
  licenseFileName: ''
})

const licenseUploaded = computed(() => Boolean(form.licenseFileName))
const licenseFileName = computed(() => form.licenseFileName || '营业执照.jpg')
const licenseFilePath = ref('')
const licenseRawFile = ref<SelectedLicenseFile>(null)
const uploadedLicenseUrl = ref('')
const submitting = ref(false)

const goBack = () => {
  clearUserSession()
  uni.reLaunch({
    url: '/pages/auth/login?identity=enterprise'
  })
}

const chooseLicense = (source: UploadSource) => {
  uni.chooseImage({
    count: 1,
    sourceType: [source],
    success: (result) => {
      const tempFiles = Array.isArray(result.tempFiles)
        ? result.tempFiles
        : result.tempFiles
          ? [result.tempFiles]
          : []
      const file = tempFiles[0] as ({ name?: string; path?: string } & SelectedLicenseFile) | undefined
      const path = file?.path || result.tempFilePaths?.[0] || ''
      const segments = path.split(/[\\/]/)
      licenseFilePath.value = path
      licenseRawFile.value = file || null
      uploadedLicenseUrl.value = ''
      form.licenseFileName = file?.name || segments[segments.length - 1] || '营业执照.jpg'
      uni.showToast({
        title: '已选择图片',
        icon: 'success'
      })
    },
    fail: () => {
      uni.showToast({
        title: source === 'camera' ? '未完成拍照上传' : '未选择相册图片',
        icon: 'none'
      })
    }
  })
}

const validateForm = () => {
  const fields = [
    { value: form.enterpriseName, message: '请输入企业名称' },
    { value: form.unifiedSocialCreditCode, message: '请输入统一社会信用代码' },
    { value: form.legalPersonName, message: '请输入法人姓名' },
    { value: form.legalPersonId, message: '请输入法人身份证号' },
    { value: form.contactName, message: '请输入联系人姓名' },
    { value: form.contactPhone, message: '请输入联系人手机号' }
  ]

  const emptyField = fields.find((item) => !item.value.trim())
  if (emptyField) {
    uni.showToast({
      title: emptyField.message,
      icon: 'none'
    })
    return false
  }

  if (!/^1\d{10}$/.test(form.contactPhone.trim())) {
    uni.showToast({
      title: '请输入正确的联系人手机号',
      icon: 'none'
    })
    return false
  }

  if (!form.licenseFileName) {
    uni.showToast({
      title: '请上传营业执照',
      icon: 'none'
    })
    return false
  }

  return true
}

const submitRegistration = async () => {
  if (!validateForm()) {
    return
  }

  if (submitting.value) {
    return
  }

  submitting.value = true
  try {
    const companyAccountFrontId = appState.userSession?.userId
    if (!companyAccountFrontId) {
      throw new Error('登录状态已过期，请重新登录')
    }

    const licenseUrl = uploadedLicenseUrl.value || await ensureLicenseUploaded()

    const auditPayload = {
      name: form.enterpriseName.trim(),
      creditCode: form.unifiedSocialCreditCode.trim().toUpperCase(),
      legalPerson: form.legalPersonName.trim(),
      legalPersonId: form.legalPersonId.trim(),
      contactName: form.contactName.trim(),
      contactMobile: form.contactPhone.trim(),
      attachments: [
        {
          filePath: licenseUrl,
          fileName: form.licenseFileName,
          fileType: 'business_license'
        }
      ]
    }

    await submitEnterpriseAuditCompat(async () => {
      await saveEnterpriseAudit(auditPayload)
      await submitEnterpriseAudit({ companyAccountFrontId })
    }, async () => {
      await saveEnterpriseAuditForm(auditPayload)
      await submitEnterpriseAuditForm({ companyAccountFrontId })
    })
  } catch (error) {
    submitting.value = false
    uni.showToast({
      title: error instanceof Error ? error.message : '提交审核失败，请稍后重试',
      icon: 'none'
    })
    return
  }

  setEnterpriseRegistration({
    enterpriseName: form.enterpriseName.trim(),
    legalPersonName: form.legalPersonName.trim(),
    legalPersonId: form.legalPersonId.trim(),
    contactName: form.contactName.trim(),
    contactPhone: form.contactPhone.trim(),
    unifiedSocialCreditCode: form.unifiedSocialCreditCode.trim().toUpperCase(),
    licenseFileName: form.licenseFileName
  })

  uni.redirectTo({
    url: '/pages/enterprise/review?status=reviewing'
  })
}

async function ensureLicenseUploaded() {
  if (uploadedLicenseUrl.value) {
    return uploadedLicenseUrl.value
  }
  if (!licenseFilePath.value) {
    throw new Error('请重新上传营业执照')
  }

  uploadedLicenseUrl.value = await uploadEnterpriseLicenseImage(
    licenseFilePath.value,
    form.licenseFileName || 'business-license.jpg',
    licenseRawFile.value
  )
  return uploadedLicenseUrl.value
}

async function submitEnterpriseAuditCompat(
  submitJson: () => Promise<void>,
  submitForm: () => Promise<void>
) {
  try {
    await submitJson()
  } catch (error) {
    const message = error instanceof Error ? error.message : ''
    if (
      message.includes('Content type') ||
      message.includes('not supported') ||
      message.includes('415')
    ) {
      await submitForm()
      return
    }
    throw error
  }
}
</script>

<style lang="scss">
page {
  min-height: 100%;
  background: #F8FBFF;
}

button::after {
  border: 0;
}

.enterprise-register-page {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background: #F8FBFF;
  color: #122942;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}

.enterprise-register-page::before,
.enterprise-register-page::after {
  content: '';
  position: absolute;
  left: 0;
  z-index: 0;
  width: 750rpx;
  pointer-events: none;
}

.enterprise-register-page::before {
  top: 0;
  height: 180rpx;
  background: url('../../static/enterprise-review/route-top.png') center / 100% 100% no-repeat;
  opacity: 0.68;
}

.enterprise-register-page::after {
  bottom: 0;
  height: 272rpx;
  background: url('../../static/enterprise-review/route-bottom.png') center / 100% 100% no-repeat;
  opacity: 0.62;
}

.enterprise-register-page__content {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  min-height: calc(1622rpx + var(--app-safe-area-top) + env(safe-area-inset-bottom));
  padding: var(--app-safe-area-top) 32rpx calc(75rpx + env(safe-area-inset-bottom));
}

.register-header {
  position: relative;
  display: flex;
  align-items: center;
  height: var(--app-page-header-height);
}

.register-header__back {
  position: absolute;
  left: 0;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  box-sizing: border-box;
  width: 72rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0 0 0 8rpx;
  line-height: 1;
  background: transparent;
}

.register-header__title {
  display: block;
  width: 100%;
  color: #122942;
  font-size: 42rpx;
  line-height: 1;
  font-weight: 700;
  text-align: center;
}

.register-card {
  box-sizing: border-box;
  width: 100%;
  height: 808rpx;
  padding: 37rpx 32rpx 40rpx;
  border-radius: 22rpx;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 11rpx 27rpx rgba(24, 74, 128, 0.11);
}

.register-card + .register-card {
  margin-top: 34rpx;
}

.register-card--upload {
  height: 376rpx;
  padding-bottom: 45rpx;
}

.register-section-title {
  display: flex;
  align-items: center;
  height: 36rpx;
  margin-bottom: 27rpx;
}

.register-card--upload .register-section-title {
  margin-bottom: 34rpx;
}

.register-section-title__accent {
  flex: 0 0 8rpx;
  width: 8rpx;
  height: 32rpx;
  margin-right: 16rpx;
  background: #168BF2;
}

.register-section-title__text {
  color: #122942;
  font-size: 30rpx;
  line-height: 36rpx;
  font-weight: 700;
}

.register-field {
  display: grid;
  grid-template-columns: 190rpx 20rpx minmax(0, 1fr);
  align-items: center;
  height: 78rpx;
}

.register-field + .register-field {
  margin-top: 40rpx;
}

.register-field__label {
  grid-column: 1;
  color: #122942;
  font-size: 26rpx;
  line-height: 1;
  font-weight: 500;
  white-space: nowrap;
}

.register-field__input {
  grid-column: 3;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  height: 78rpx;
  padding: 0 21rpx;
  border: 2rpx solid #d7d7d8;
  border-radius: 11rpx;
  background: rgba(255, 255, 255, 0.82);
  color: #122942;
  font-size: 24rpx;
  line-height: 78rpx;
  font-weight: 400;
}

.register-field__placeholder {
  color: #b8b8bb;
  font-weight: 400;
}

.license-upload {
  display: grid;
  grid-template-columns: 260rpx 32rpx minmax(0, 1fr);
  align-items: start;
  width: 100%;
  height: 224rpx;
}

.license-preview {
  position: relative;
  grid-column: 1;
  width: 260rpx;
  height: 224rpx;
}

.license-preview__paper {
  position: relative;
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border: 2rpx solid #d6d6d7;
  border-radius: 12rpx;
  background: #ffffff;
}

.license-preview__placeholder {
  position: absolute;
  left: 16rpx;
  top: 29rpx;
  width: 228rpx;
  height: 172rpx;
}

.license-preview__paper--image {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8rpx;
  background: #ffffff;
}

.license-preview__image {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  border-radius: 8rpx;
}

.license-preview__check {
  position: absolute;
  right: -10rpx;
  top: -10rpx;
  z-index: 2;
  width: 42rpx;
  height: 42rpx;
  border-radius: 50%;
  background: #168BF2;
  box-shadow: 0 6rpx 14rpx rgba(22, 126, 232, 0.24);
}

.license-preview__check-mark {
  box-sizing: border-box;
  width: 20rpx;
  height: 11rpx;
  margin: 12rpx 0 0 11rpx;
  border-left: 5rpx solid #ffffff;
  border-bottom: 5rpx solid #ffffff;
  transform: rotate(-45deg);
}

.license-details {
  grid-column: 3;
  box-sizing: border-box;
  min-width: 0;
  height: 224rpx;
  padding-top: 10rpx;
}

.license-meta__title {
  display: block;
  color: #122942;
  font-size: 28rpx;
  line-height: 36rpx;
  font-weight: 700;
}

.license-preview__name {
  display: block;
  max-width: 100%;
  margin-top: 16rpx;
  overflow: hidden;
  color: #122942;
  font-size: 25rpx;
  line-height: 32rpx;
  font-weight: 400;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.license-actions {
  display: flex;
  gap: 16rpx;
  width: 100%;
  margin-top: 36rpx;
}

.license-actions__button {
  display: flex;
  flex: 1 1 0;
  align-items: center;
  justify-content: center;
  gap: 10rpx;
  box-sizing: border-box;
  min-width: 0;
  height: 72rpx;
  margin: 0;
  padding: 0;
  border: 2rpx solid #167EE8;
  border-radius: 10rpx;
  background: #ffffff;
  color: #167EE8;
  line-height: 1;
}

.license-actions__text {
  color: #167EE8;
  font-size: 22rpx;
  line-height: 1;
  font-weight: 400;
  white-space: nowrap;
}

.register-submit {
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 100%;
  height: 92rpx;
  margin: 90rpx 0 0;
  padding: 0;
  border-radius: 14rpx;
  background: #167EE8;
  color: #ffffff;
  font-size: 34rpx;
  line-height: 92rpx;
  font-weight: 700;
  letter-spacing: 0;
  box-shadow: 0 10rpx 19rpx rgba(8, 104, 244, 0.13);
}

.register-submit[disabled] {
  opacity: 0.72;
}
</style>
