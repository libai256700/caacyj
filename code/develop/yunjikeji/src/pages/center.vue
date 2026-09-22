<template>
  <view class="center-page" :style="$appSafeAreaStyle">
    <view class="center-page__bg"></view>

    <view class="center-page__content">
      <view class="center-nav">
        <text class="center-nav__title">小技</text>
      </view>

      <scroll-view
        class="chat-scroll"
        scroll-y
        scroll-with-animation
        :scroll-into-view="chatScrollTarget"
      >
        <view class="chat-flow">
          <view v-for="message in historyMessages" :key="message.id" class="free-message">
            <view class="chat-row chat-row--user">
              <view class="free-user">{{ message.question }}</view>
              <UserProfileAvatar
                class="chat-avatar chat-avatar--user"
                :avatar-id="userAvatarId"
              />
            </view>
            <view class="chat-row chat-row--bot">
              <view class="chat-avatar chat-avatar--bot">
                <image
                  class="chat-avatar__nav-source"
                  src="/static/brand/ai-assistant-logo.png"
                  mode="aspectFill"
                  aria-hidden="true"
                />
              </view>
              <view class="chat-bubble chat-bubble--bot">
                <text>{{ message.answer }}</text>
              </view>
            </view>
          </view>

          <view v-if="showWelcomeMessage" class="chat-row chat-row--bot">
            <view class="chat-avatar chat-avatar--bot">
              <image
                class="chat-avatar__nav-source"
                src="/static/brand/ai-assistant-logo.png"
                mode="aspectFill"
                aria-hidden="true"
              />
            </view>
            <view class="chat-bubble chat-bubble--bot">
              <text>你好，我是小技。</text>
              <text>我可以为你解答无人机飞行训练、飞行前检查、空域规则和手册要点等问题。</text>
            </view>
          </view>

          <view v-for="message in chatMessages" :key="message.id" class="free-message">
            <view class="chat-row chat-row--user">
              <view class="free-user">{{ message.question }}</view>
              <UserProfileAvatar
                class="chat-avatar chat-avatar--user"
                :avatar-id="userAvatarId"
              />
            </view>
            <view class="chat-row chat-row--bot">
              <view class="chat-avatar chat-avatar--bot">
                <image
                  class="chat-avatar__nav-source"
                  src="/static/brand/ai-assistant-logo.png"
                  mode="aspectFill"
                  aria-hidden="true"
                />
              </view>
              <view class="chat-bubble chat-bubble--bot">
                <text>{{ message.answer }}</text>
                <view v-if="message.references.length" class="knowledge-references">
                  <view
                    v-for="(reference, referenceIndex) in message.references"
                    :key="`${message.id}-${referenceIndex}`"
                    class="knowledge-reference"
                  >
                    <text class="knowledge-reference__source">{{ reference.source }}</text>
                    <text class="knowledge-reference__content">{{ reference.content }}</text>
                  </view>
                </view>
              </view>
            </view>
          </view>
          <view id="chat-bottom" class="chat-bottom"></view>
        </view>
      </scroll-view>

      <view class="assistant-input">
        <view class="assistant-input__row">
          <input
            v-model="questionDraft"
            class="ask-input"
            :adjust-position="false"
            confirm-type="send"
            placeholder="输入你的问题，获取专业解答..."
            placeholder-class="ask-input__placeholder"
            @focus="scrollToBottom"
            @confirm="sendQuestion"
          />
          <button class="send-button" :disabled="questionSending" @tap="sendQuestion">
            {{ questionSending ? '查询中' : '发送' }}
          </button>
        </view>
      </view>
    </view>

    <HomeProfileTabBar class="center-page__tabbar" active="center" />
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import HomeProfileTabBar from '@/components/HomeProfileTabBar.vue'
import UserProfileAvatar from '@/components/UserProfileAvatar.vue'
import { appState, requireLogin, setActiveTab } from '@/stores/appState'
import { fetchCurrentCustomer } from '@/services/customerAuth'
import {
  fetchAiCenterHistory,
  normalizeAppServiceErrorMessage,
  queryKnowledge,
  type AiKnowledgeReference
} from '@/services/practice'
import {
  cacheProfileAvatarId,
  readStoredProfileAvatarId
} from '@/utils/profileAvatar'

type FreeMessage = {
  id: number
  question: string
  answer: string
  status: 'loading' | 'done' | 'error'
  references: AiKnowledgeReference[]
}

const questionDraft = ref('')
const chatScrollTarget = ref('')
const questionSending = ref(false)
const userAvatarId = ref(readStoredProfileAvatarId())
const historyMessages = ref<FreeMessage[]>([])
const freeMessages = ref<FreeMessage[]>([])
const showWelcomeMessage = ref(false)
const chatMessages = computed(() => freeMessages.value)

const AI_WELCOME_SEEN_STORAGE_PREFIX = 'yunjikeji-ai-center-welcome-seen:'

const prepareWelcomeMessage = () => {
  const userId = appState.userSession?.userId
  if (typeof userId !== 'number' || !Number.isFinite(userId)) {
    showWelcomeMessage.value = true
    return
  }

  const storageKey = `${AI_WELCOME_SEEN_STORAGE_PREFIX}${userId}`
  const hasSeenWelcome = uni.getStorageSync(storageKey) === true
  showWelcomeMessage.value = !hasSeenWelcome

  if (!hasSeenWelcome) {
    uni.setStorageSync(storageKey, true)
  }
}

onShow(() => {
  if (requireLogin()) {
    if (appState.loginIdentity === 'enterprise') {
      uni.reLaunch({ url: '/pages/service/customer-service' })
      return
    }

    setActiveTab('center')
    prepareWelcomeMessage()
    freeMessages.value = []
    userAvatarId.value = readStoredProfileAvatarId()
    void loadCurrentUserAvatar()
    void loadChatHistory()
  }
})

const loadCurrentUserAvatar = async () => {
  try {
    const profile = await fetchCurrentCustomer()
    userAvatarId.value = cacheProfileAvatarId(profile.avatarUrl)
  } catch (error) {
    console.warn('load customer avatar failed', error)
  }
}

const loadChatHistory = async () => {
  try {
    const history = await fetchAiCenterHistory()
    historyMessages.value = history.map((item, index) => ({
      id: Number(item.id) || Date.now() + index,
      question: item.question,
      answer: item.answer,
      status: 'done',
      references: []
    }))
  } catch {
    historyMessages.value = []
  } finally {
    scrollToBottom()
  }
}

const scrollToBottom = () => {
  nextTick(() => {
    chatScrollTarget.value = ''
    nextTick(() => {
      chatScrollTarget.value = 'chat-bottom'
    })
  })
}

const sendQuestion = async () => {
  const text = questionDraft.value.trim()
  if (!text) {
    uni.showToast({
      title: '请输入问题',
      icon: 'none'
    })
    return
  }
  if (questionSending.value) {
    return
  }

  const messageId = Date.now()
  questionSending.value = true
  freeMessages.value = [
    ...freeMessages.value,
    {
      id: messageId,
      question: text,
      answer: '正在深度思考',
      status: 'loading',
      references: []
    }
  ]
  questionDraft.value = ''
  scrollToBottom()

  try {
    const result = await queryKnowledge(text)
    const answer = result.answer || '暂未查询到相关知识库内容，请换一种问法再试。'
    freeMessages.value = freeMessages.value.map((message) =>
      message.id === messageId
        ? {
            ...message,
            answer,
            status: 'done',
            references: result.references
          }
        : message
    )
  } catch (error) {
    const rawMessage = error instanceof Error ? error.message : ''
    const message = normalizeAppServiceErrorMessage(rawMessage, '知识库服务暂不可用，请稍后再试')
    freeMessages.value = freeMessages.value.map((item) =>
      item.id === messageId
        ? {
            ...item,
            answer: message,
            status: 'error',
            references: []
          }
        : item
    )
    uni.showToast({
      title: message,
      icon: 'none'
    })
  } finally {
    questionSending.value = false
    scrollToBottom()
  }
}

</script>

<style lang="scss">
page {
  height: 100%;
  min-height: 100%;
  overflow: hidden;
  background: #f8fbff;
}

button::after {
  border: 0;
}

.center-page {
  position: relative;
  box-sizing: border-box;
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
  color: #08253b;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: #f8fbff;
}

.center-page__bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: #f8fbff;
}

.center-page__content {
  position: absolute;
  z-index: 1;
  inset: 0;
  box-sizing: border-box;
}

.center-nav,
.chat-row,
.assistant-input__row {
  display: flex;
  align-items: center;
}

.center-nav {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  box-sizing: border-box;
  height: calc(var(--app-safe-area-top) + var(--app-page-header-height));
  padding-top: var(--app-safe-area-top);
  justify-content: center;
}

.center-nav__title,
.chat-bubble text,
.free-user {
  display: block;
}

.center-nav__title {
  color: #073948;
  font-size: 40rpx;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0;
}

.chat-scroll {
  position: absolute;
  top: calc(var(--app-safe-area-top) + 93rpx);
  right: 0;
  bottom: 285rpx;
  left: 0;
  box-sizing: border-box;
  width: auto;
  height: auto;
  margin: 0;
}

.chat-flow {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 0 21rpx 42rpx 38rpx;
}

.chat-bottom {
  width: 1rpx;
  height: 1rpx;
}

.chat-row {
  position: relative;
  align-items: flex-start;
}

.chat-row--bot {
  gap: 10.5rpx;
  padding-right: 38rpx;
}

.chat-row--user {
  gap: 11rpx;
  justify-content: flex-end;
  align-items: flex-start;
}

.chat-avatar {
  box-sizing: border-box;
  width: 108rpx;
  height: 108rpx;
  flex: 0 0 108rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 8rpx 18rpx rgba(29, 64, 103, 0.1);
}

.chat-avatar--bot {
  position: relative;
  height: 112rpx;
  margin-top: 8rpx;
  padding: 0;
  overflow: hidden;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: none;
}

.chat-avatar__nav-source {
  width: 100%;
  height: 100%;
}

.chat-avatar--user {
  width: 104rpx;
  height: 104rpx;
  flex-basis: 104rpx;
  border: 3rpx solid rgba(255, 255, 255, 0.9);
}

.chat-bubble {
  position: relative;
  box-sizing: border-box;
  min-width: 0;
  flex: 1;
  padding: 28rpx 32rpx;
  border: 1rpx solid rgba(51, 91, 132, 0.045);
  border-radius: 28rpx;
  color: #08253b;
  font-family: 'PingFang SC', DengXian, 'Microsoft YaHei', sans-serif;
  font-size: 26rpx;
  line-height: 49rpx;
  font-weight: 400;
  letter-spacing: 0;
}

.chat-bubble--bot {
  background: #F8FBFF;
  box-shadow: 0 12rpx 24rpx rgba(22, 63, 110, 0.12), inset 0 1rpx 0 rgba(255, 255, 255, 0.94);
}

.chat-flow > .chat-row--bot:first-child .chat-bubble {
  min-height: 200rpx;
  padding: 25rpx 28rpx 19rpx 34rpx;
}

.chat-flow > .chat-row--bot:first-child .chat-bubble text:first-child {
  font-size: 26rpx;
  line-height: 49rpx;
  font-weight: 400;
}

.chat-flow > .chat-row--bot:first-child .chat-bubble text + text {
  margin-top: 4rpx;
}

.free-message {
  display: flex;
  flex-direction: column;
  gap: 22rpx;
  padding-top: 32rpx;
}

.free-user {
  position: relative;
  box-sizing: border-box;
  min-height: 76rpx;
  max-width: calc(100% - 115rpx);
  margin-top: 12.5rpx;
  padding: 18rpx 21rpx;
  border-radius: 18rpx;
  background: #0868F4;
  color: #ffffff;
  box-shadow: 0 10rpx 20rpx rgba(20, 96, 188, 0.16);
  font-size: 24rpx;
  line-height: 40rpx;
  font-weight: 500;
  letter-spacing: 0;
}

.free-user::after {
  position: absolute;
  top: 17rpx;
  right: -13rpx;
  width: 0;
  height: 0;
  border-top: 13rpx solid transparent;
  border-bottom: 13rpx solid transparent;
  border-left: 14rpx solid #0868F4;
  content: '';
}

.knowledge-references {
  margin-top: 20rpx;
  padding-top: 16rpx;
  border-top: 1rpx solid rgba(79, 106, 135, 0.16);
}

.knowledge-reference {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.knowledge-reference + .knowledge-reference {
  margin-top: 12rpx;
}

.knowledge-reference__source {
  color: #0868F4;
  font-size: 21rpx;
  line-height: 1.35;
  font-weight: 700;
}

.knowledge-reference__content {
  color: #60738A;
  font-size: 21rpx;
  line-height: 1.45;
}

.assistant-input {
  position: fixed;
  z-index: 20;
  right: 32rpx;
  bottom: 100rpx;
  left: 25.5rpx;
  box-sizing: border-box;
  height: 130rpx;
  padding: 24rpx 21.5rpx 24rpx 18rpx;
  border: 1rpx solid rgba(63, 96, 132, 0.07);
  border-radius: 32rpx;
  background: #F7FAFE;
  box-shadow: 0 12rpx 28rpx rgba(22, 63, 110, 0.1), inset 0 1rpx 0 rgba(255, 255, 255, 0.96);
}

.assistant-input__row {
  height: 80rpx;
  gap: 12.5rpx;
}

.ask-input {
  box-sizing: border-box;
  flex: 1;
  min-width: 0;
  height: 80rpx;
  padding: 0 24rpx;
  border: 1rpx solid rgba(70, 99, 128, 0.14);
  border-radius: 20rpx;
  background: #F7FAFE;
  color: #08253b;
  box-shadow: 0 5rpx 14rpx rgba(22, 63, 110, 0.06), inset 0 1rpx 0 rgba(255, 255, 255, 0.96);
  font-size: 24rpx;
  line-height: 80rpx;
  letter-spacing: 0;
}

.ask-input__placeholder {
  color: #7b8084;
}

.send-button {
  width: 107rpx;
  height: 80rpx;
  flex: 0 0 107rpx;
  margin: 0;
  padding: 0;
  border: 1rpx solid rgba(0, 91, 216, 0.28);
  border-radius: 20rpx;
  color: #ffffff;
  background: linear-gradient(180deg, #59A9FF 0%, #0868F4 100%);
  box-shadow: 0 8rpx 16rpx rgba(18, 91, 190, 0.18), inset 0 1rpx 0 rgba(255, 255, 255, 0.3);
  font-size: 26rpx;
  line-height: 78rpx;
  font-weight: 500;
  letter-spacing: 0;
  text-indent: -2rpx;
}

</style>
