<template>
  <view class="login-page" :style="$appSafeAreaStyle">
    <view class="login-hero">
      <view class="login-hero__content">
        <text class="login-hero__brand">小技</text>
        <text class="login-hero__title">无人机职教与飞行成长</text>
      </view>
      <view class="login-hero__mascot-wrap">
        <image class="login-hero__mascot" :src="mascotUrl" mode="aspectFit" />
      </view>
    </view>

    <view
      class="login-content"
      :class="[`login-content--${loginRole}`, `login-content--method-${loginMethod}`]"
    >
      <view class="login-role-tabs">
        <button
          class="login-role-tabs__item"
          :class="{ 'login-role-tabs__item--active': loginRole === 'student' }"
          @tap="selectLoginRole('student')"
        >
          学员登录
        </button>
        <button
          class="login-role-tabs__item"
          :class="{ 'login-role-tabs__item--active': loginRole === 'enterprise' }"
          @tap="selectLoginRole('enterprise')"
        >
          <text>企业登录</text>
          <uv-icon class="login-role-tabs__arrow" name="arrow-right" color="#F28A18" size="34rpx" />
        </button>
      </view>

      <view class="login-panel">
        <view class="login-method-switch" role="tablist" aria-label="登录方式">
          <button
            class="login-method-switch__item"
            :class="{ 'login-method-switch__item--active': loginMethod === 'univerify' }"
            :disabled="loginLoading"
            @tap="selectLoginMethod('univerify')"
          >
            其他手机号码登录
          </button>
          <button
            class="login-method-switch__item"
            :class="{ 'login-method-switch__item--active': loginMethod === 'sms' }"
            :disabled="loginLoading"
            @tap="selectLoginMethod('sms')"
          >
            短信验证码登录
          </button>
        </view>

        <view v-if="loginMethod === 'univerify'" class="login-one-click-panel">
          <view class="login-one-click-panel__icon">
            <uv-icon name="phone" color="#168BF2" size="48rpx" />
          </view>
          <view class="login-one-click-panel__details">
            <text class="login-one-click-panel__title">本机号码一键登录</text>
            <text
              class="login-one-click-panel__number"
              :class="{ 'login-one-click-panel__number--pending': !hasOneClickPhone }"
            >
              {{ oneClickPhoneLabel }}
            </text>
            <text class="login-one-click-panel__description">中国移动认证服务</text>
          </view>
          <button
            class="login-one-click-panel__submit"
            :disabled="loginLoading || isUniverifyPreparing"
            @tap="handleUniverifyLogin"
          >
            <text>{{ oneClickLoginLabel }}</text>
            <uv-icon
              v-if="!loginLoading"
              class="login-one-click-panel__submit-arrow"
              name="arrow-right"
              color="#F28A18"
              size="44rpx"
            />
          </button>
        </view>

        <view v-else class="login-form">
          <view class="login-field-group">
            <text class="login-field__label">账号</text>
            <view class="login-field login-field--phone">
              <view class="login-field__icon login-field__icon--phone">
                <uv-icon name="phone" color="#168BF2" size="42rpx" />
              </view>
              <input
                v-model="phone"
                class="login-field__input"
                :class="{ 'login-field__input--filled': phone.length > 0 }"
                type="number"
                maxlength="11"
                placeholder="请输入手机号"
                placeholder-class="login-field__placeholder"
                :disabled="loginLoading"
              />
            </view>
          </view>

          <view class="login-field-group login-field-group--password">
            <text class="login-field__label">验证码</text>
            <view class="login-field login-field--code">
              <view class="login-field__icon login-field__icon--shield">
                <view class="login-field__shield-mark" />
              </view>
              <input
                v-model="verifyCode"
                class="login-field__input"
                :class="{ 'login-field__input--filled': verifyCode.length > 0 }"
                type="number"
                maxlength="6"
                placeholder="请输入验证码"
                placeholder-class="login-field__placeholder"
                :disabled="loginLoading"
              />
              <view
                class="login-field__get-code"
                :class="{
                  'login-field__get-code--disabled': codeCountdown > 0 || loginLoading,
                  'login-field__get-code--countdown': codeCountdown > 0
                }"
                @tap="requestVerifyCode"
              >
                {{ codeCountdown > 0 ? `${codeCountdown}s` : '获取验证码' }}
              </view>
            </view>
          </view>

          <button
            class="login-submit"
            :class="{ 'login-submit--loading': loginLoading }"
            :disabled="loginLoading"
            @tap="handleLogin"
          >
            <text class="login-submit__label">
              {{ loginLoading ? '登录中...' : '登录 / 注册' }}
            </text>
          </button>
        </view>
      </view>

      <view class="login-agreement" @tap="toggleAgreement">
        <view class="login-agreement__check" :class="{ 'login-agreement__check--active': agreed }">
          <text v-if="agreed" class="login-agreement__tick">✓</text>
        </view>
        <text class="login-agreement__text">我已阅读并同意</text>
        <text id="auth-user-agreement-link" class="login-agreement__link" @tap.stop="openAgreement('user')">用户服务协议</text>
        <text class="login-agreement__text">和</text>
        <text id="auth-privacy-agreement-link" class="login-agreement__link" @tap.stop="openAgreement('privacy')">隐私政策</text>
      </view>

      <text class="login-icp">ICP/SP 备案信息</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import {
  type CompanyAuthResponse,
  type CustomerAuthResponse,
  fetchCurrentCustomer,
  fetchCurrentStudentAudit,
  fetchCompanyPostCodes,
  loginCustomer,
  loginOrRegisterCompany,
  refreshCompanyToken,
  refreshCustomerToken,
  sendLoginSmsCode,
  toCompanySessionPayload,
  toStudentSessionPayload
} from '@/services/customerAuth'
import {
  appState,
  consumeLoginRedirect,
  getLastAuthenticatedPhone,
  markOrganizationBindingApproved,
  setActiveTab,
  setLoginIdentity,
  setUserSession,
  type EnterpriseReviewStatus,
  type LoginIdentity,
  type UserSessionPayload
} from '@/stores/appState'
import mascotUrl from '@/static/brand/ai-assistant-logo.png'
import {
  prepareUniverify,
  waitForUniverifyRecovery,
  waitForUniverifyStability
} from '@/utils/univerify'

const phone = ref('')
const verifyCode = ref('')
const lastAuthenticatedPhone = ref(getLastAuthenticatedPhone())
const loginRole = ref<'student' | 'enterprise'>('student')
type LoginMethod = 'univerify' | 'sms'
const loginMethod = ref<LoginMethod>('univerify')
const agreed = ref(false)
const loginLoading = ref(false)
const codeCountdown = ref(0)
const univerifyAvailable = ref(false)
const univerifyUnavailableMessage = ref('当前设备暂不支持一键登录，请使用短信登录')
type UniverifyPreparationState = 'idle' | 'preparing' | 'ready' | 'unavailable'
const univerifyPreparationState = ref<UniverifyPreparationState>('idle')
let univerifyPreparedAt: number | undefined
let countdownTimer: ReturnType<typeof setInterval> | null = null

type EnterpriseSessionPayload = UserSessionPayload & {
  hasWtPost?: boolean
}

onLoad((options) => {
  const identity = typeof options?.identity === 'string' ? options.identity : appState.loginIdentity
  if (identity === 'student' || identity === 'enterprise') {
    loginRole.value = identity
    setLoginIdentity(identity as LoginIdentity)
  }
})

const normalizePhone = (value: string) => value.replace(/\D/g, '').slice(0, 11)
const oneClickPhone = computed(() => {
  const enteredPhone = normalizePhone(phone.value)
  return /^1\d{10}$/.test(enteredPhone) ? enteredPhone : lastAuthenticatedPhone.value
})
const hasOneClickPhone = computed(() => /^1\d{10}$/.test(oneClickPhone.value))
const oneClickPhoneLabel = computed(() => hasOneClickPhone.value
  ? `${oneClickPhone.value.slice(0, 3)}****${oneClickPhone.value.slice(-4)}`
  : '本机号码待授权')
const isUniverifyPreparing = computed(() => univerifyPreparationState.value === 'preparing')
const oneClickLoginLabel = computed(() => {
  if (loginLoading.value) {
    return '登录中...'
  }
  return isUniverifyPreparing.value ? '正在准备一键登录...' : '本机号码一键登录'
})

const selectLoginRole = (role: LoginIdentity) => {
  loginRole.value = role
  setLoginIdentity(role)
}

const selectLoginMethod = (method: LoginMethod) => {
  if (!loginLoading.value) {
    loginMethod.value = method
  }
}

const normalizeErrorMessage = (message: string) => {
  const trimmedMessage = message.trim()

  if (!trimmedMessage) {
    return '登录失败，请稍后重试'
  }

  if (trimmedMessage === '请输入登录密码。' || trimmedMessage === 'Password is required.') {
    return '请输入验证码'
  }

  if (trimmedMessage === '登录密码长度需为 6-32 位。' || trimmedMessage === 'Password length must be 6 to 32 characters.') {
    return '请输入 6 位验证码'
  }

  if (trimmedMessage === '短信验证码必须为 6 位数字') {
    return '请输入 6 位验证码'
  }

  if (trimmedMessage === '手机号格式不正确。' || trimmedMessage === 'Mobile number is invalid.') {
    return '请输入正确的手机号账号'
  }

  if (trimmedMessage === '手机号账号或密码错误。' || trimmedMessage === 'Mobile account or password is incorrect.') {
    return '手机号或验证码错误'
  }

  if (trimmedMessage === '登录服务暂未完成配置，请稍后重试。' || trimmedMessage === 'Database datasource is not configured for login.') {
    return '登录服务暂未完成配置，请稍后重试'
  }

  if (trimmedMessage.toLowerCase().includes('resource exhausted')) {
    return '一键登录云服务资源不足，请检查 uniCloud 服务空间额度或欠费状态'
  }

  if (trimmedMessage === '一键登录请求校验失败') {
    return '一键登录服务配置不一致，请检查 uniCloud 与后端共享密钥'
  }

  return trimmedMessage
}

const getErrorMessage = (error: unknown, fallbackMessage: string) => {
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const message = (error as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) {
      return message
    }
  }

  return fallbackMessage
}

const validatePhone = () => {
  phone.value = normalizePhone(phone.value)

  if (!/^1\d{10}$/.test(phone.value)) {
    uni.showToast({
      title: '请输入正确的手机号账号',
      icon: 'none'
    })
    return false
  }

  return true
}

const validateVerifyCode = () => {
  verifyCode.value = verifyCode.value.replace(/\D/g, '').slice(0, 6)

  if (!verifyCode.value.trim()) {
    uni.showToast({
      title: '请输入验证码',
      icon: 'none'
    })
    return false
  }

  if (!/^\d{6}$/.test(verifyCode.value)) {
    uni.showToast({
      title: '请输入 6 位验证码',
      icon: 'none'
    })
    return false
  }

  return true
}

const toggleAgreement = () => {
  agreed.value = !agreed.value
}

const openAgreement = (type: 'user' | 'privacy') => {
  uni.navigateTo({
    url: `/pages/auth/agreement?type=${type}`
  })
}

onShow(() => {
  if (appState.userSession) {
    void redirectAfterLogin()
    return
  }

  void prepareUniverifyLogin()
})

const prepareUniverifyLogin = (options: { force?: boolean } = {}): Promise<boolean> => {
  // #ifdef APP-PLUS
  if (!options.force && univerifyPreparationState.value === 'ready') {
    return Promise.resolve(true)
  }

  univerifyPreparationState.value = 'preparing'
  univerifyAvailable.value = false
  univerifyUnavailableMessage.value = ''

  return prepareUniverify(options).then((result) => {
    univerifyPreparationState.value = result.available ? 'ready' : 'unavailable'
    univerifyAvailable.value = result.available
    univerifyPreparedAt = result.preparedAt
    univerifyUnavailableMessage.value = result.available
      ? ''
      : result.reason === 'network'
        ? '未检测到可用运营商网络，请确认 SIM 卡已入网并开启移动数据，或使用短信登录'
        : '当前设备暂不支持一键登录，请使用短信登录'

    console.info('[univerify] pre-login completed', {
      available: result.available,
      reason: result.reason
    })
    return result.available
  })
  // #endif

  // #ifndef APP-PLUS
  univerifyPreparationState.value = 'unavailable'
  univerifyAvailable.value = false
  return Promise.resolve(false)
  // #endif
}

type UniverifyAuthorizationResult = {
  openid: string
  accessToken: string
}

type UniverifyCloudLoginResult = {
  role: LoginIdentity
  session: CustomerAuthResponse | CompanyAuthResponse
}

type UniverifyLoginStage = 'authorization' | 'cloud-function' | 'session-refresh' | 'redirect'

const UNIVERIFY_CANCELLED_ERROR_NAME = 'UniverifyCancelledError'

const createUniverifyCancelledError = () => {
  const error = new Error('Univerify authorization cancelled')
  error.name = UNIVERIFY_CANCELLED_ERROR_NAME
  return error
}

const isUniverifyCancelledError = (error: unknown) =>
  error instanceof Error && error.name === UNIVERIFY_CANCELLED_ERROR_NAME

const readUniverifyErrorField = (error: unknown, keys: string[]) => {
  if (typeof error !== 'object' || error === null) {
    return undefined
  }

  const source = error as Record<string, unknown>
  for (const key of keys) {
    const value = source[key]
    if (typeof value === 'string' || typeof value === 'number') {
      return value
    }
  }

  return undefined
}

const logUniverifyError = (stage: UniverifyLoginStage, error: unknown) => {
  console.error('[univerify] login failed', {
    stage,
    code: readUniverifyErrorField(error, ['errCode', 'code']),
    message: readUniverifyErrorField(error, ['errMsg', 'message'])
  })
}

const getUniverifyErrorCode = (error: unknown) => {
  const rawCode = readUniverifyErrorField(error, ['errCode', 'code'])
  const code = Number(rawCode)
  return Number.isFinite(code) ? code : undefined
}

const isUniverifyNetworkEnvironmentError = (error: unknown) => getUniverifyErrorCode(error) === 30001

const handleUniverifyLogin = async () => {
  if (!agreed.value) {
    uni.showToast({ title: '请先同意用户协议和隐私协议', icon: 'none' })
    return
  }

  if (loginLoading.value) {
    return
  }

  // #ifdef APP-PLUS
  loginLoading.value = true
  let stage: UniverifyLoginStage = 'authorization'
  console.info('[univerify] login started', { role: loginRole.value })
  try {
    const isPrepared = await prepareUniverifyLogin()
    if (!isPrepared) {
      loginMethod.value = 'sms'
      uni.showToast({ title: univerifyUnavailableMessage.value, icon: 'none' })
      return
    }
    await waitForUniverifyStability(univerifyPreparedAt)

    let authorization: UniverifyAuthorizationResult
    try {
      authorization = await requestUniverifyAuthorization()
    } catch (error) {
      if (!isUniverifyNetworkEnvironmentError(error)) {
        throw error
      }

      // The carrier bridge can briefly report 30001 after a cold app start,
      // even when the first pre-login callback succeeded. Refresh once before
      // treating it as an unavailable login method.
      console.info('[univerify] retrying authorization after network preparation')
      uni.closeAuthView()
      await waitForUniverifyRecovery()
      const recovered = await prepareUniverifyLogin({ force: true })
      if (!recovered) {
        throw error
      }
      await waitForUniverifyStability(univerifyPreparedAt)
      authorization = await requestUniverifyAuthorization()
    }

    console.info('[univerify] authorization succeeded', {
      hasOpenid: Boolean(authorization.openid),
      hasAccessToken: Boolean(authorization.accessToken)
    })
    stage = 'cloud-function'
    const cloudResult = await uniCloud.callFunction({
      name: 'yj-univerify-login',
      data: {
        accessToken: authorization.accessToken,
        openid: authorization.openid,
        role: loginRole.value
      }
    })
    const result = cloudResult.result as UniverifyCloudLoginResult
    if (!result?.session || result.role !== loginRole.value) {
      throw new Error('一键登录结果无效，请改用短信登录')
    }

    console.info('[univerify] cloud login succeeded', {
      roleMatches: result.role === loginRole.value,
      hasSession: Boolean(result.session)
    })
    stage = 'session-refresh'
    const session = result.role === 'enterprise'
      ? await completeUniverifyEnterpriseLogin(result.session as CompanyAuthResponse)
      : await completeUniverifyStudentLogin(result.session as CustomerAuthResponse)
    setUserSession(session)
    uni.closeAuthView()
    stage = 'redirect'
    await redirectAfterLogin()
  } catch (error) {
    if (isUniverifyCancelledError(error)) {
      uni.closeAuthView()
      console.info('[univerify] authorization cancelled')
      void prepareUniverifyLogin()
    } else if (isUniverifyNetworkEnvironmentError(error)) {
      uni.closeAuthView()
      loginMethod.value = 'sms'
      uni.showToast({
        title: '当前网络暂不支持一键登录，已切换至短信验证码登录',
        icon: 'none'
      })
      void prepareUniverifyLogin({ force: true })
    } else {
      logUniverifyError(stage, error)
      const message = normalizeErrorMessage(getErrorMessage(error, '一键登录失败，请使用短信登录'))
      // The auth page owns the current native window. Wait for it to finish closing
      // before showing a modal, otherwise Android destroys the modal with UniVerifyActivity.
      uni.closeAuthView()
      setTimeout(() => {
        uni.showModal({
          title: '一键登录错误',
          content: message,
          showCancel: false,
          complete: () => {
            void prepareUniverifyLogin()
          }
        })
      }, 300)
    }
  } finally {
    loginLoading.value = false
  }
  // #endif
}

const requestUniverifyAuthorization = () => new Promise<UniverifyAuthorizationResult>((resolve, reject) => {
  uni.login({
    provider: 'univerify',
    univerifyStyle: {
      fullScreen: true,
      backgroundColor: '#F5F9FF',
      authButton: {
        normalColor: '#168BF2',
        highlightColor: '#005BD8',
        textColor: '#FFFFFF',
        title: '本机号码一键登录',
        borderRadius: '24px'
      }
    },
    success: (response) => {
      const authResult = typeof response.authResult === 'object' && response.authResult
        ? response.authResult as Record<string, unknown>
        : {}
      console.info('[univerify] authorization callback', {
        authResultFields: Object.keys(authResult).sort()
      })
      const openid = typeof authResult.openid === 'string' ? authResult.openid : ''
      const accessToken = typeof authResult.access_token === 'string'
        ? authResult.access_token
        : typeof authResult.accessToken === 'string' ? authResult.accessToken : ''
      if (!openid || !accessToken) {
        reject(new Error('未获得运营商授权信息，请使用短信登录'))
        return
      }
      resolve({ openid, accessToken })
    },
    fail: (error) => {
      const errCode = Number(error?.errCode ?? error?.code)
      if ([30002, 30003].includes(errCode)) {
        reject(createUniverifyCancelledError())
        return
      }
      const rawCode = error?.errCode ?? error?.code
      const rawMessage = error?.errMsg ?? error?.message
      const detail = [rawCode, rawMessage]
        .filter((value) => value !== undefined && value !== null && String(value).trim())
        .map((value) => String(value).trim())
        .join(': ')
      console.warn('[univerify] authorization failed', {
        code: rawCode,
        message: rawMessage
      })
      const authorizationError = new Error(detail ? `一键登录授权失败（${detail}）` : '一键登录授权失败（未返回错误码）') as Error & {
        code?: string | number
      }
      authorizationError.code = rawCode
      reject(authorizationError)
    }
  })
})

async function completeUniverifyStudentLogin(data: CustomerAuthResponse): Promise<UserSessionPayload> {
  const loginSession = toStudentSessionPayload(data)
  setUserSession(loginSession)
  const refreshedSession = await refreshCustomerToken(loginSession.refreshToken || '')
  setUserSession(refreshedSession)
  const profile = await fetchCurrentCustomer()
  return {
    ...refreshedSession,
    userId: profile.customerId,
    mobile: profile.mobile || refreshedSession.mobile,
    nickname: profile.nickname || refreshedSession.nickname,
    tenantId: profile.tenantId || refreshedSession.tenantId
  }
}

async function completeUniverifyEnterpriseLogin(data: CompanyAuthResponse): Promise<EnterpriseSessionPayload> {
  const loginSession = toCompanySessionPayload(data)
  setUserSession(loginSession)
  let hasWtPost: boolean | undefined
  let wtTenantId: number | undefined
  try {
    const postCodesResult = await fetchCompanyPostCodes(loginSession.mobile)
    hasWtPost = Boolean(postCodesResult.hasWtPost)
    wtTenantId = postCodesResult.tenantId
  } catch {
    hasWtPost = undefined
  }

  const refreshedSession = await refreshCompanyToken(loginSession.refreshToken || '', hasWtPost ? wtTenantId : undefined)
  return {
    ...refreshedSession,
    tenantId: hasWtPost ? wtTenantId || refreshedSession.tenantId : refreshedSession.tenantId,
    auditStatus: loginSession.auditStatus,
    hasWtPost
  }
}

const requestVerifyCode = async () => {
  if (!validatePhone()) {
    return
  }

  if (codeCountdown.value > 0 || loginLoading.value) {
    return
  }

  loginLoading.value = true
  try {
    await sendLoginSmsCode(phone.value)
    codeCountdown.value = 60
    countdownTimer = setInterval(() => {
      codeCountdown.value -= 1
      if (codeCountdown.value <= 0 && countdownTimer) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
    }, 1000)

    uni.showToast({
      title: '验证码已发送',
      icon: 'none'
    })
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '验证码发送失败，请稍后重试',
      icon: 'none'
    })
  } finally {
    loginLoading.value = false
  }
}

const handleLogin = async () => {
  if (!validatePhone()) {
    return
  }

  if (!validateVerifyCode()) {
    return
  }

  if (!agreed.value) {
    uni.showToast({
      title: '请先同意用户协议和隐私协议',
      icon: 'none'
    })
    return
  }

  if (loginLoading.value) {
    return
  }

  loginLoading.value = true
  try {
    const session = loginRole.value === 'enterprise'
      ? await loginEnterprise(phone.value, verifyCode.value)
      : await loginStudent(phone.value, verifyCode.value)
    setUserSession(session)
    await redirectAfterLogin()
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '登录失败，请稍后重试',
      icon: 'none'
    })
  } finally {
    loginLoading.value = false
  }
}

async function loginStudent(mobile: string, code: string): Promise<UserSessionPayload> {
  const loginSession = await loginCustomer(mobile, code)
  setUserSession(loginSession)

  const refreshedSession = await refreshCustomerToken(loginSession.refreshToken || '')
  setUserSession(refreshedSession)

  const profile = await fetchCurrentCustomer()
  return {
    ...refreshedSession,
    userId: profile.customerId,
    mobile: profile.mobile || refreshedSession.mobile,
    nickname: profile.nickname || refreshedSession.nickname,
    tenantId: profile.tenantId || refreshedSession.tenantId
  }
}

async function loginEnterprise(mobile: string, code: string): Promise<UserSessionPayload> {
  const loginSession = await loginOrRegisterCompany(mobile, code)
  setUserSession(loginSession)
  let hasWtPost: boolean | undefined
  let wtTenantId: number | undefined
  try {
    const postCodesResult = await fetchCompanyPostCodes(mobile)
    hasWtPost = Boolean(postCodesResult.hasWtPost)
    wtTenantId = postCodesResult.tenantId
  } catch (error) {
    if (!appState.userSession) {
      throw error
    }
    hasWtPost = undefined
  }

  const refreshedSession = await refreshCompanyToken(loginSession.refreshToken || '', hasWtPost ? wtTenantId : undefined)
  return {
    ...refreshedSession,
    tenantId: hasWtPost ? wtTenantId || refreshedSession.tenantId : refreshedSession.tenantId,
    auditStatus: loginSession.auditStatus,
    hasWtPost
  } as EnterpriseSessionPayload
}

async function redirectAfterLogin(skipStudentAudit = false) {
  consumeLoginRedirect()

  if (loginRole.value === 'enterprise' && appState.userSession?.hasWtPost === false) {
    const auditStatus = Number(appState.userSession.auditStatus ?? 0)
    if (auditStatus !== 2) {
      uni.redirectTo({ url: resolveEnterpriseReviewRedirectUrl(auditStatus) })
      return
    }
  }

  if (loginRole.value !== 'enterprise' && !skipStudentAudit) {
    try {
      const audit = await fetchCurrentStudentAudit()
      if (Number(audit?.auditStatus) === 2) {
        markOrganizationBindingApproved('login')
      }
    } catch (error) {
      console.warn('load student audit after login failed', error)
    }
  }

  setActiveTab('practice')
  uni.reLaunch({
    url: loginRole.value === 'enterprise' ? '/pages/enterprise/students' : '/pages/home'
  })
}

function resolveEnterpriseReviewRedirectUrl(auditStatus: number) {
  if (auditStatus === 1 || auditStatus === 3) {
    return `/pages/enterprise/review?status=${resolveEnterpriseReviewStatus(auditStatus)}`
  }
  return '/pages/enterprise/register'
}

function resolveEnterpriseReviewStatus(auditStatus: number): EnterpriseReviewStatus {
  if (auditStatus === 1) {
    return 'reviewing'
  }
  if (auditStatus === 3) {
    return 'rejected'
  }
  return 'pending'
}
</script>

<style lang="scss" src="./login-v15.scss"></style>
