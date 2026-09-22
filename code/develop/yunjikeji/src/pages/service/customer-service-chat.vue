<template>
  <view class="chat-page" :style="$appSafeAreaStyle">
    <view class="chat-header">
      <button class="chat-back" @tap="goBack" aria-label="返回">
        <text class="chat-back__icon">‹</text>
      </button>
      <view class="chat-title-wrap">
        <text class="chat-title">{{ chatTitle }}</text>
      </view>
    </view>

    <scroll-view
      class="message-scroll"
      scroll-y
      :scroll-into-view="scrollTarget"
      :scroll-with-animation="true"
      :show-scrollbar="false"
    >
      <view class="message-list">
        <view v-if="loadError && !messages.length" class="message-state message-state--error" @tap="loadConversation">
          <text>{{ WELCOME_MESSAGE }}</text>
        </view>

        <view v-else class="message-state">
          <text>{{ WELCOME_MESSAGE }}</text>
        </view>

        <view
          v-for="message in messages"
          :id="`message-${message.id}`"
          :key="message.id"
          class="message-row"
          :class="message.sender === 'student' ? 'message-row--student' : 'message-row--service'"
        >
          <view v-if="showLeadingIdentity(message)" class="message-identity" :class="messageIdentityClass(message)">
            <view class="message-identity__avatar">
              <image class="message-identity__avatar-image" src="/static/phone-bind/avatar-user.svg" mode="aspectFit" />
            </view>
            <text class="message-identity__label">{{ messageIdentityLabel(message) }}</text>
          </view>

          <view class="message-body">
            <view v-if="message.type === 'text'" class="message-bubble message-bubble--text">
              <text>{{ message.content }}</text>
            </view>

            <view v-else-if="message.type === 'image'" class="message-bubble message-bubble--media">
              <!-- #ifdef H5 -->
              <img
                class="image-message"
                :src="message.content"
                referrerpolicy="no-referrer"
                draggable="false"
                @click="previewImage(message.content)"
              />
              <!-- #endif -->
              <!-- #ifndef H5 -->
              <image
                class="image-message"
                :src="message.content"
                mode="aspectFill"
                referrer-policy="no-referrer"
                @tap="previewImage(message.content)"
              />
              <!-- #endif -->
            </view>

            <view v-else class="message-bubble message-bubble--media video-message">
              <video class="video-player" :src="message.content" controls object-fit="cover"></video>
            </view>
          </view>

          <view v-if="showTrailingIdentity(message)" class="message-identity message-identity--self">
            <view class="message-identity__avatar">
              <image class="message-identity__avatar-image" src="/static/phone-bind/avatar-user.svg" mode="aspectFit" />
            </view>
            <text class="message-identity__label">{{ messageIdentityLabel(message) }}</text>
          </view>
        </view>
        <view id="message-bottom" class="message-bottom"></view>
      </view>
    </scroll-view>

    <view
      class="composer"
      :class="{
        'composer--expanded': mediaPanelOpen,
        'composer--keyboard-open': keyboardOpen
      }"
    >
      <view class="composer-line">
        <button class="media-toggle" :class="{ 'media-toggle--open': mediaPanelOpen }" @tap="toggleMediaPanel" aria-label="打开附件">
          <text class="media-toggle__icon">＋</text>
        </button>
        <input
          v-model="draft"
          class="message-input"
          type="text"
          :adjust-position="false"
          confirm-type="send"
          placeholder="请输入消息..."
          placeholder-class="message-input__placeholder"
          @focus="closeMediaPanel"
          @confirm="sendText"
        />
        <view class="send-button" :class="{ 'send-button--disabled': !canSendText }" @tap="sendText">
          <text>{{ sending ? '发送中' : '发送' }}</text>
        </view>
      </view>

      <view v-if="mediaPanelOpen" class="media-panel">
        <view class="media-action" @tap="sendImage">
          <view class="media-action__icon media-action__icon--image"></view>
          <view>
            <text class="media-action__title">图片</text>
            <text class="media-action__desc">发送图片</text>
          </view>
        </view>
        <view class="media-action" @tap="sendVideo">
          <view class="media-action__icon media-action__icon--video"></view>
          <view>
            <text class="media-action__title">视频</text>
            <text class="media-action__desc">发送视频</text>
          </view>
        </view>
      </view>
    </view>
    <SelfTestLoadingOverlay
      :show="loading && !messages.length"
      title="客服消息加载中"
      message="正在同步客服消息，请稍候。"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import SelfTestLoadingOverlay from '@/components/practice/SelfTestLoadingOverlay.vue'
import { appState, requireLogin } from '@/stores/appState'
import {
  fetchCustomerServiceMessages,
  fetchCustomerServiceSession,
  fetchAllEnterpriseStudentMessages,
  sendCustomerServiceMediaMessage,
  sendCustomerServiceTextMessage,
  sendEnterpriseStudentMediaMessage,
  sendEnterpriseStudentTextMessage,
  startEnterpriseStudentConversation,
  uploadCustomerServiceMedia,
  type CustomerServiceMessage
} from '@/services/customerService'
import {
  createCustomerServiceSocket,
  type CustomerServiceRealtimeMessage
} from '@/services/customerServiceWebSocket'

type MessageType = 'text' | 'image' | 'video'
type MessageSender = 'service' | 'student'

type SupportMessage = {
  id: number
  sender: MessageSender
  type: MessageType
  content: string
  createdAt: string
  title?: string
  cover?: string
  duration?: string
}

const DEFAULT_CHAT_TITLE = '我的客服'
const WELCOME_MESSAGE = '您好,欢迎咨询云技客服。'

const draft = ref('')
const mediaPanelOpen = ref(false)
const keyboardOpen = ref(false)
const loading = ref(false)
const sending = ref(false)
const loadError = ref('')
const messages = ref<SupportMessage[]>([])
const scrollTarget = ref('')
const conversationId = ref('')
const studentId = ref('')
const studentName = ref('')
const realtimeError = ref('')
const connectedConversationId = ref('')
const activeSessionId = ref(0)
const socketClient = createCustomerServiceSocket({
  onMessage: handleRealtimeMessage,
  onError: (message) => {
    realtimeError.value = message
  }
})

const canSendText = computed(() => draft.value.trim().length > 0 && !sending.value)
const chatTitle = computed(() => studentName.value || DEFAULT_CHAT_TITLE)
const isEnterpriseTeacherConversation = computed(() => appState.loginIdentity === 'enterprise' && isEnterpriseStudentChat())

const handleKeyboardHeightChange = (event: { height: number }) => {
  keyboardOpen.value = event.height > 0
}

onLoad((query) => {
  registerKeyboardHeightListener()
  if (query?.conversationId && typeof query.conversationId === 'string') {
    conversationId.value = decodeURIComponent(query.conversationId)
  }
  if (query?.studentId && typeof query.studentId === 'string') {
    studentId.value = decodeURIComponent(query.studentId)
  }
  if (query?.studentName && typeof query.studentName === 'string') {
    studentName.value = decodeURIComponent(query.studentName)
  }
})

onShow(() => {
  if (requireLogin()) {
    loadConversation()
  }
})

onHide(() => {
  keyboardOpen.value = false
  socketClient.close()
})

onUnload(() => {
  unregisterKeyboardHeightListener()
  keyboardOpen.value = false
  socketClient.close()
})

async function loadConversation() {
  loading.value = true
  loadError.value = ''
  realtimeError.value = ''
  try {
    if (isEnterpriseStudentChat()) {
      const enterpriseConversationId = resolveEnterpriseConversationId()
      if (enterpriseConversationId) {
        const result = await fetchAllEnterpriseStudentMessages(
          enterpriseConversationId,
          Number(studentId.value)
        )
        messages.value = result.map(toSupportMessage)
        activeSessionId.value = enterpriseConversationId
        connectedConversationId.value = `${enterpriseConversationId}`
      } else {
        messages.value = []
        activeSessionId.value = 0
        connectedConversationId.value = ''
      }
    } else {
      const session = await fetchCustomerServiceSession()
      activeSessionId.value = session.id || 0
      connectedConversationId.value = `${session.id || conversationId.value}`
      messages.value = (session.messages || []).map(toSupportMessage)
    }
    connectRealtime()
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '客服消息加载失败，点击重试'
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

async function refreshMessages() {
  const enterpriseConversationId = resolveEnterpriseConversationId()
  const result = isEnterpriseStudentChat()
    ? enterpriseConversationId
      ? await fetchAllEnterpriseStudentMessages(enterpriseConversationId, Number(studentId.value))
      : []
    : await fetchCustomerServiceMessages()
  messages.value = result.map(toSupportMessage)
}

async function sendText() {
  const content = draft.value.trim()
  if (!content || sending.value) return
  sending.value = true
  try {
    draft.value = ''
    mediaPanelOpen.value = false
    const enterpriseConversationId = isEnterpriseStudentChat()
      ? await ensureEnterpriseConversation()
      : 0
    if (shouldUseRealtimeSocket()) {
      try {
        await socketClient.sendTextMessage({
          conversationId: enterpriseConversationId || undefined,
          studentId: isEnterpriseStudentChat() ? Number(studentId.value) : undefined,
          content
        })
      } catch (socketError) {
        const message = isEnterpriseStudentChat()
          ? await sendEnterpriseStudentTextMessage(
            enterpriseConversationId,
            Number(studentId.value),
            content
          )
          : await sendCustomerServiceTextMessage(content)
        appendMessage(toSupportMessage(message))
        if (socketError instanceof Error) {
          realtimeError.value = socketError.message
        }
      }
    } else {
      const message = isEnterpriseStudentChat()
        ? await sendEnterpriseStudentTextMessage(
          enterpriseConversationId,
          Number(studentId.value),
          content
        )
        : await sendCustomerServiceTextMessage(content)
      appendMessage(toSupportMessage(message))
    }
    scrollToBottom()
  } catch (error) {
    draft.value = content
    uni.showToast({
      title: error instanceof Error ? error.message : '消息发送失败',
      icon: 'none'
    })
  } finally {
    sending.value = false
  }
}

function sendImage() {
  if (sending.value) return
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed', 'original'],
    sourceType: ['album', 'camera'],
    success: (res) => {
      const filePath = res.tempFilePaths?.[0]
      if (filePath) {
        sendMedia('image', filePath)
      }
    }
  })
}

function sendVideo() {
  if (sending.value) return
  uni.chooseVideo({
    sourceType: ['album', 'camera'],
    compressed: true,
    success: (res) => {
      if (res.tempFilePath) {
        sendMedia('video', res.tempFilePath)
      }
    }
  })
}

async function sendMedia(messageType: 'image' | 'video', filePath: string) {
  sending.value = true
  mediaPanelOpen.value = false
  try {
    const uploaded = await uploadCustomerServiceMedia(filePath, messageType)
    const enterpriseConversationId = isEnterpriseStudentChat()
      ? await ensureEnterpriseConversation()
      : 0
    const message = isEnterpriseStudentChat()
      ? await sendEnterpriseStudentMediaMessage(
        enterpriseConversationId,
        Number(studentId.value),
        messageType,
        uploaded.url
      )
      : await sendCustomerServiceMediaMessage(messageType, uploaded.url)
    appendMessage(toSupportMessage(message))
    scrollToBottom()
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '媒体发送失败',
      icon: 'none'
    })
  } finally {
    sending.value = false
  }
}

function previewImage(url: string) {
  uni.previewImage({
    current: url,
    urls: messages.value.filter((item) => item.type === 'image').map((item) => item.content)
  })
}

function toggleMediaPanel() {
  mediaPanelOpen.value = !mediaPanelOpen.value
}

function closeMediaPanel() {
  mediaPanelOpen.value = false
}

function registerKeyboardHeightListener() {
  if (typeof uni.onKeyboardHeightChange === 'function') {
    uni.onKeyboardHeightChange(handleKeyboardHeightChange)
  }
}

function unregisterKeyboardHeightListener() {
  if (typeof uni.offKeyboardHeightChange === 'function') {
    uni.offKeyboardHeightChange(handleKeyboardHeightChange)
  }
}

function scrollToBottom() {
  nextTick(() => {
    scrollTarget.value = ''
    nextTick(() => {
      scrollTarget.value = 'message-bottom'
    })
  })
}

function isEnterpriseStudentChat() {
  const id = Number(studentId.value)
  return Number.isFinite(id) && id > 0
}

function resolveEnterpriseConversationId() {
  const id = Number(conversationId.value || connectedConversationId.value || activeSessionId.value)
  return Number.isFinite(id) && id > 0 ? id : 0
}

async function ensureEnterpriseConversation() {
  const existingConversationId = resolveEnterpriseConversationId()
  if (existingConversationId) {
    return existingConversationId
  }

  const conversation = await startEnterpriseStudentConversation(Number(studentId.value))
  const startedConversationId = Number(conversation.conversationId)
  if (!Number.isFinite(startedConversationId) || startedConversationId <= 0) {
    throw new Error('发起学员会话失败')
  }
  conversationId.value = `${startedConversationId}`
  connectedConversationId.value = `${startedConversationId}`
  activeSessionId.value = startedConversationId
  return startedConversationId
}

function connectRealtime() {
  if (!shouldUseRealtimeSocket()) return
  socketClient.close()
  socketClient.connect()
}

function shouldUseRealtimeSocket() {
  return Boolean(appState.userSession?.token)
}

function handleRealtimeMessage(message: CustomerServiceRealtimeMessage) {
  if (!isCurrentConversationMessage(message)) {
    return
  }
  appendMessage(toSupportMessageFromRealtime(message))
  if (!activeSessionId.value && message.sessionId) {
    activeSessionId.value = message.sessionId
    connectedConversationId.value = `${message.sessionId}`
  }
  scrollToBottom()
}

function resolveCurrentConversationId() {
  if (isEnterpriseStudentChat()) {
    return `${resolveEnterpriseConversationId()}`
  }
  return connectedConversationId.value || `${activeSessionId.value || conversationId.value}`
}

function isCurrentConversationMessage(message: CustomerServiceRealtimeMessage) {
  if (isEnterpriseStudentChat()) {
    return resolveEnterpriseConversationId() > 0 &&
      message.studentId === Number(studentId.value) &&
      message.sessionId === resolveEnterpriseConversationId()
  }
  return message.conversationId === resolveCurrentConversationId()
}

function appendMessage(message: SupportMessage) {
  const exists = messages.value.some((item) => item.id === message.id)
  if (exists) return
  messages.value = [...messages.value, message]
}

function showLeadingIdentity(message: SupportMessage) {
  return message.sender === 'service'
}

function showTrailingIdentity(message: SupportMessage) {
  return message.sender === 'student'
}

function messageIdentityLabel(message: SupportMessage) {
  if (isEnterpriseTeacherConversation.value) {
    return message.sender === 'service' ? '学员' : '我'
  }
  return message.sender === 'service' ? '教员' : '我'
}

function messageIdentityClass(message: SupportMessage) {
  return message.sender === 'service' ? 'message-identity--peer' : 'message-identity--self'
}

function toSupportMessage(message: CustomerServiceMessage): SupportMessage {
  const type = normalizeMessageType(message.messageType)
  return {
    id: message.id,
    sender: message.mine ? 'student' : 'service',
    type,
    content: message.content,
    createdAt: formatMessageTime(message.createTime)
  }
}

function toSupportMessageFromRealtime(message: CustomerServiceRealtimeMessage): SupportMessage {
  const type = normalizeMessageType(message.messageType)
  const currentUserId = appState.userSession?.userId || 0
  const mine = isEnterpriseStudentChat()
    ? message.sessionFrom !== Number(studentId.value)
    : message.sessionFrom === currentUserId
  const sender: MessageSender = mine ? 'student' : 'service'
  return {
    id: message.id,
    sender,
    type,
    content: message.content,
    createdAt: formatMessageTime(message.createTime)
  }
}

function normalizeMessageType(messageType: string): MessageType {
  if (messageType === 'image' || messageType === 'video') {
    return messageType
  }
  return 'text'
}

function formatMessageTime(value?: string) {
  const date = value ? new Date(value) : new Date()
  if (Number.isNaN(date.getTime())) return ''
  const hour = `${date.getHours()}`.padStart(2, '0')
  const minute = `${date.getMinutes()}`.padStart(2, '0')
  return `${hour}:${minute}`
}

function goBack() {
  const pages = getCurrentPages()
  if (pages.length > 1) {
    uni.navigateBack()
    return
  }
  uni.reLaunch({ url: '/pages/service/customer-service' })
}
</script>

<style lang="scss">
page {
  height: 100%;
  overflow: hidden;
  background: #F2F7FC;
}

button::after {
  border: 0;
}

.chat-page {
  position: relative;
  isolation: isolate;
  display: grid;
  grid-template-rows: calc(var(--app-safe-area-top) + var(--app-page-header-height)) minmax(0, 1fr) auto;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  color: #082047;
  background:
    linear-gradient(rgba(244, 249, 255, 0.82), rgba(244, 249, 255, 0.82)),
    url('@/static/profile-settings/settings-paper-texture.jpg') center top / 320rpx 188rpx repeat,
    #F2F7FC;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.chat-page::before {
  position: absolute;
  z-index: 0;
  top: 0;
  right: 0;
  left: 0;
  height: 360rpx;
  pointer-events: none;
  content: "";
  background:
    url('@/static/profile-settings/settings-contours-top.svg') left -270rpx top 80rpx / 400rpx 315rpx no-repeat,
    url('@/static/profile-settings/settings-contours-top.svg') right -45rpx top -48rpx / 430rpx 338rpx no-repeat;
  opacity: 0.9;
}

.chat-header {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 86rpx minmax(0, 1fr) 86rpx;
  align-items: center;
  height: calc(var(--app-safe-area-top) + var(--app-page-header-height));
  padding: var(--app-safe-area-top) 26rpx 0;
  border-bottom: 0;
  background: transparent;
  box-shadow: none;
}

.chat-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #082047;
  transform: translateX(-6rpx);
}

.chat-back__icon {
  position: relative;
  display: block;
  width: 34rpx;
  height: 44rpx;
  overflow: hidden;
  color: transparent;
  font-size: 0;
}

.chat-back__icon::before {
  position: absolute;
  top: 7rpx;
  left: 10rpx;
  box-sizing: border-box;
  width: 29rpx;
  height: 29rpx;
  content: "";
  border-bottom: 5rpx solid #082047;
  border-left: 5rpx solid #082047;
  border-radius: 2rpx;
  transform: rotate(45deg);
}

.chat-title-wrap {
  min-width: 0;
  text-align: center;
  transform: none;
}

.chat-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-title {
  color: #082047;
  font-size: 35rpx;
  line-height: 1.2;
  font-weight: 600;
}

.message-scroll {
  position: relative;
  z-index: 1;
  min-height: 0;
  height: 100%;
}

.message-list {
  box-sizing: border-box;
  min-height: 100%;
  padding: 75rpx 56rpx 36rpx;
}

.message-state {
  position: relative;
  box-sizing: border-box;
  width: 386rpx;
  max-width: 100%;
  margin: 0;
  padding: 24rpx 28rpx;
  border: 0;
  border-radius: 20rpx;
  background: #ffffff;
  color: #082047;
  font-size: 29rpx;
  line-height: 1.5;
  font-weight: 500;
  text-align: left;
  box-shadow: 0 13rpx 34rpx rgba(18, 48, 82, 0.07);
}

.message-state::before {
  position: absolute;
  top: 50%;
  left: -10rpx;
  width: 0;
  height: 0;
  content: "";
  border-top: 11rpx solid transparent;
  border-right: 12rpx solid #ffffff;
  border-bottom: 11rpx solid transparent;
  filter: drop-shadow(0 5rpx 8rpx rgba(18, 48, 82, 0.04));
  transform: translateY(-50%);
}

.message-state--error {
  color: #082047;
  cursor: pointer;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 0;
  margin-bottom: 40rpx;
}

.message-state + .message-row {
  margin-top: 41rpx;
}

.message-row--student {
  justify-content: flex-end;
}

.message-identity {
  display: none;
  flex: 0 0 78rpx;
  flex-direction: column;
  align-items: center;
  gap: 10rpx;
}

.message-identity--self {
  margin-left: 2rpx;
}

.message-identity__avatar {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 78rpx;
  height: 78rpx;
  overflow: hidden;
  border: 1rpx solid rgba(255, 255, 255, 0.96);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 14rpx 32rpx rgba(37, 104, 168, 0.12);
}

.message-identity__avatar-image {
  display: block;
  width: 44rpx;
  height: 44rpx;
}

.message-identity__label {
  color: #6d7f99;
  font-size: 22rpx;
  line-height: 1.2;
  font-weight: 620;
  text-align: center;
}


.message-body {
  max-width: 100%;
  min-width: 0;
}

.message-row--student .message-body {
  display: flex;
  justify-content: flex-end;
}

.message-bubble {
  position: relative;
  box-sizing: border-box;
  overflow: visible;
  border-radius: 20rpx;
  box-shadow: 0 13rpx 34rpx rgba(18, 48, 82, 0.08);
}

.message-bubble--text {
  padding: 24rpx 28rpx;
  font-size: 26.2rpx;
  line-height: 43.5rpx;
  font-weight: 500;
}

.message-row--service .message-bubble--text {
  border: 0;
  background: #ffffff;
  color: #082047;
}

.message-row--student .message-bubble--text {
  background: #0868F4;
  color: #ffffff;
}

.message-row--service .message-bubble::before,
.message-row--student .message-bubble::after {
  position: absolute;
  top: 50%;
  width: 0;
  height: 0;
  content: "";
  filter: drop-shadow(0 5rpx 8rpx rgba(18, 48, 82, 0.04));
  transform: translateY(-50%);
}

.message-row--service .message-bubble::before {
  left: -10rpx;
  border-top: 11rpx solid transparent;
  border-right: 12rpx solid #ffffff;
  border-bottom: 11rpx solid transparent;
}

.message-row--student .message-bubble::after {
  right: -10rpx;
  border-top: 11rpx solid transparent;
  border-bottom: 11rpx solid transparent;
  border-left: 12rpx solid #0868F4;
}

.message-bubble--text text {
  display: block;
  word-break: break-word;
}

.message-bubble--media {
  padding: 20rpx;
  border: 0;
  background: #ffffff;
}

.message-row--student .message-bubble--media {
  background: #0868F4;
}

.image-message {
  display: block;
  width: 330rpx;
  height: 230rpx;
  border-radius: 10rpx;
  background: #dcecff;
}

.video-message {
  position: relative;
  width: 388rpx;
}

.video-player {
  display: block;
  width: 100%;
  height: 240rpx;
  border-radius: 14rpx;
  background: #dcecff;
}

.composer {
  position: relative;
  z-index: 2;
  box-sizing: border-box;
  height: 112rpx;
  margin: 0 32rpx calc(env(safe-area-inset-bottom) + 72rpx);
  padding: 0 28rpx 0 24rpx;
  border: 0;
  border-radius: 56rpx;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 15rpx 38rpx rgba(18, 48, 82, 0.11);
}

.composer--expanded {
  height: auto;
  padding-bottom: 18rpx;
  border-radius: 32rpx;
}

.composer--keyboard-open {
  margin-bottom: 12rpx;
}

.composer-line {
  display: grid;
  grid-template-columns: 56rpx minmax(0, 1fr) 76rpx;
  column-gap: 18rpx;
  align-items: center;
  height: 112rpx;
  overflow: visible;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.media-toggle,
.send-button {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0;
  padding: 0;
}

.media-toggle {
  box-sizing: border-box;
  width: 56rpx;
  height: 56rpx;
  justify-self: center;
  border: 3rpx solid #082047;
  border-radius: 14rpx;
  background: transparent;
  color: #082047;
}

.media-toggle__icon {
  position: relative;
  display: block;
  width: 30rpx;
  height: 30rpx;
  overflow: hidden;
  color: transparent;
  font-size: 0;
  transition: transform 0.18s ease;
}

.media-toggle__icon::before,
.media-toggle__icon::after {
  position: absolute;
  top: 50%;
  left: 50%;
  content: "";
  border-radius: 2rpx;
  background: #082047;
  transform: translate(-50%, -50%);
}

.media-toggle__icon::before {
  width: 30rpx;
  height: 4rpx;
}

.media-toggle__icon::after {
  width: 4rpx;
  height: 30rpx;
}

.media-toggle--open .media-toggle__icon {
  transform: rotate(45deg);
}

.message-input {
  box-sizing: border-box;
  width: 100%;
  height: 76rpx;
  padding: 0 22rpx;
  border: 1rpx solid rgba(8, 32, 71, 0.1);
  border-radius: 22rpx;
  background: rgba(255, 255, 255, 0.9);
  color: #082047;
  font-size: 28rpx;
  line-height: 76rpx;
}

.message-input__placeholder {
  color: #afb5c1;
}

.send-button {
  width: 78rpx;
  height: 74rpx;
  justify-self: end;
  border-radius: 18rpx;
  background: #0868F4;
  color: #ffffff;
  transform: translateX(2rpx);
}

.send-button text {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
  white-space: nowrap;
}

.send-button::before {
  width: 34rpx;
  height: 33rpx;
  content: "";
  background: #ffffff;
  clip-path: polygon(0 0, 100% 50%, 0 100%, 14% 61%, 66% 50%, 14% 39%);
  transform: translateX(2rpx);
}

.send-button--disabled {
  opacity: 1;
}

.message-bottom {
  width: 1rpx;
  height: 1rpx;
}

.media-panel {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18rpx;
  margin-top: 14rpx;
  padding: 18rpx;
  border-radius: 24rpx;
  background: #f7fbff;
  box-shadow: inset 0 0 0 1rpx rgba(54, 93, 132, 0.08);
}

.media-action {
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 78rpx minmax(0, 1fr);
  column-gap: 20rpx;
  align-items: center;
  min-height: 110rpx;
  padding: 20rpx 22rpx;
  border: 1rpx solid rgba(54, 93, 132, 0.1);
  border-radius: 18rpx;
  background: #ffffff;
  box-shadow: 0 10rpx 26rpx rgba(18, 48, 82, 0.055);
}

.media-action__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  width: 64rpx;
  height: 64rpx;
  border-radius: 12rpx;
  background: #07325c;
  color: #ffffff;
}

.media-action__icon--video {
  border-radius: 10rpx;
  background: #0878EE;
}

.media-action__icon--image::before {
  position: absolute;
  right: 12rpx;
  bottom: 13rpx;
  left: 12rpx;
  height: 24rpx;
  content: "";
  border-radius: 4rpx;
  background: #ffffff;
  clip-path: polygon(0 100%, 34% 44%, 48% 66%, 68% 30%, 100% 100%);
}

.media-action__icon--image::after {
  position: absolute;
  top: 13rpx;
  left: 14rpx;
  width: 13rpx;
  height: 13rpx;
  content: "";
  border-radius: 50%;
  background: #ffffff;
}

.media-action__icon--video::before {
  position: absolute;
  top: 14rpx;
  bottom: 14rpx;
  left: 11rpx;
  width: 34rpx;
  content: "";
  border-radius: 6rpx;
  background: #ffffff;
}

.media-action__icon--video::after {
  position: absolute;
  top: 20rpx;
  right: 9rpx;
  width: 16rpx;
  height: 24rpx;
  content: "";
  background: #ffffff;
  clip-path: polygon(0 24%, 100% 0, 100% 100%, 0 76%);
}

.media-action__title,
.media-action__desc {
  display: block;
}

.media-action__title {
  color: #052658;
  font-size: 26rpx;
  line-height: 1.2;
  font-weight: 800;
}

.media-action__desc {
  margin-top: 8rpx;
  color: #939eaa;
  font-size: 21rpx;
  line-height: 1.2;
  font-weight: 540;
}

@media (max-width: 360px) {
  .message-body {
    max-width: 76%;
  }

  .message-bubble--text {
    font-size: 25rpx;
  }

  .video-message {
    width: 370rpx;
  }

  .video-player {
    height: 208rpx;
  }
}
</style>
