<template>
  <view class="self-test-page" :class="{ 'self-test-page--core-scale': showCoreScale, 'self-test-page--grouped': showGroupedQuestion }" :style="$appSafeAreaStyle">
    <view class="self-test-page__backdrop"></view>
    <scroll-view class="self-test-page__scroll" scroll-y :show-scrollbar="false">
      <view class="self-test-page__content">
      <view class="self-test-nav">
        <button class="self-test-nav__back" aria-label="返回" @tap="goBack"><uv-icon name="arrow-left" color="#06224A" size="44rpx" /></button>
        <text class="self-test-nav__title">{{ assessmentTitle }}</text>
        <text class="self-test-nav__count" v-if="stage === 'questions' && totalQuestions">{{ progressLabel }}</text>
      </view>

      <AppStateView v-if="status === 'empty' || status === 'error'" :status="status" :title="stateTitle" :message="errorMessage" action-text="重新加载" @retry="loadQuestions" />
      <template v-else-if="currentQuestion">
        <view class="self-test-progress"><view class="self-test-progress__bar" :style="{ width: `${progress}%` }"></view></view>
        <CoreScaleQuestionGroup
          v-if="showGroupedQuestion"
          :questions="groupQuestions"
          :answers="answers"
          :group-start-index="groupStartIndex"
          :variant="showSupplementGroup ? 'supplement' : 'core'"
          :title="showSupplementGroup ? '补充模块' : '核心量表'"
          :guide-text="showSupplementGroup ? '请选择最符合你当前情况的数字' : '请选择最符合你当前感受的数字'"
          :section-title="showSupplementGroup ? '工作特征' : undefined"
          :show-endpoints="!showSupplementGroup"
          :stem-prefix="showSupplementGroup ? '对以下工作特征，您的接受程度如何？' : undefined"
          :strip-stem-brackets="showSupplementGroup"
          @select="toggleQuestionOption"
        />
        <view v-else class="self-test-card">
          <view class="self-test-card__intro">
            <view class="self-test-card__owl" aria-hidden="true"></view>
            <view class="self-test-card__intro-copy">
              <text v-if="currentQuestion.stepName" class="self-test-card__title">{{ currentQuestion.stepName }}</text>
              <text class="self-test-card__type">{{ currentQuestion.type }}</text>
            </view>
          </view>
          <text class="self-test-card__stem">{{ currentQuestion.stem || currentQuestion.title }}<text v-if="isOptionalQuestion">（选填）</text></text>
          <textarea v-if="isTextQuestion" v-model="currentAnswer" class="self-test-card__text-input" placeholder="请输入你的答案" maxlength="500" auto-height />
          <view v-else class="self-test-options">
            <button v-for="option in currentQuestion.options" :key="option.id" class="self-test-option" :class="{ 'self-test-option--selected': selectedIds.includes(option.id) }" @tap="toggleOption(option.id)">
              <text class="self-test-option__label">{{ option.label }}</text><text class="self-test-option__content">{{ option.content }}</text>
              <uv-icon v-if="selectedIds.includes(option.id)" name="checkmark" color="#1579ed" size="28rpx" />
            </button>
          </view>
        </view>
        <view class="self-test-actions">
          <button v-if="previousIndex >= 0" class="self-test-previous" :disabled="submitting || questionLoading" @tap="goPrevious">{{ previousActionLabel }}</button>
          <button class="self-test-submit" :disabled="!canSubmit || submitting || questionLoading" @tap="submitCurrent">{{ submitting ? '提交中...' : (isLast ? '提交并生成报告' : nextActionLabel) }}</button>
        </view>
      </template>
      </view>
    </scroll-view>

    <view v-if="stage === 'profile'" class="profile-dialog">
      <view class="profile-dialog__header">
        <button class="profile-dialog__close" aria-label="关闭" @tap="goBack">
          <uv-icon name="arrow-left" color="#111111" size="46rpx" />
        </button>
        <text class="profile-dialog__page-title">自我测评</text>
        <view class="profile-dialog__intro">
          <view class="profile-dialog__mascot" aria-hidden="true"></view>
          <text class="profile-dialog__heading">填写基本资料</text>
        </view>
      </view>

      <view class="profile-form">
        <view v-for="field in profileFields" :key="field.key" class="profile-field-wrap">
          <text class="profile-field__label">{{ field.label }}<text v-if="!field.required && field.key !== 'idCard'" class="profile-field__optional">（选填）</text></text>
          <view class="profile-field" :class="{ 'profile-field--disabled': profileLoading }">
            <input
              :value="profileForm[field.key]"
              class="profile-field__input"
              :placeholder="field.placeholder"
              :maxlength="field.maxlength"
              :type="field.inputType"
              :disabled="profileLoading"
              placeholder-class="profile-field__placeholder"
              @input="updateProfileField(field.key, ($event as any).detail.value)"
              @blur="markProfileFieldTouched(field.key)"
            />
          </view>
          <text v-if="getProfileFieldError(field.key)" class="profile-field-error">{{ getProfileFieldError(field.key) }}</text>
        </view>

        <button
          class="profile-dialog__submit"
          :class="{ 'profile-dialog__submit--disabled': !canSaveProfile || profileLoading }"
          :disabled="profileSaving || profileLoading"
          @tap="submitProfile"
        >{{ profileSaving ? '保存中...' : '下一步' }}</button>
      </view>
    </view>

    <SelfTestSubmittedDialog :visible="submittedDialogVisible" @home="returnHome" />
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import AppStateView from '@/components/AppStateView.vue'
import CoreScaleQuestionGroup from '@/components/practice/CoreScaleQuestionGroup.vue'
import SelfTestSubmittedDialog from '@/components/practice/SelfTestSubmittedDialog.vue'
import { fetchAssessmentQuestion, fetchAssessmentQuestions, submitAssessmentAnswers, type AssessmentQuestion } from '@/services/assessment'
import { fetchCurrentCustomer, saveCustomerInfo, type CustomerProfile } from '@/services/customerAuth'
import { appState, type AppAsyncStatus, requireLogin } from '@/stores/appState'

type ProfileFieldKey = 'name' | 'phone' | 'idCard' | 'school' | 'major'
type SelfTestStage = 'profile' | 'questions'

const CORE_SCALE_STEP_NAME = '核心量表'
const CORE_SCALE_GROUP_SIZE = 5
const SUPPLEMENT_STEP_NAME = '补充模块'

const stage = ref<SelfTestStage>('profile')
const questionCache = ref<Record<number, AssessmentQuestion>>({})
const totalQuestions = ref(0)
const currentIndex = ref(0)
const answers = ref<Record<string, string[]>>({})
const textAnswers = ref<Record<string, string>>({})
const savedAnswers = ref<Record<string, string[]>>({})
const status = ref<AppAsyncStatus>('loading')
const errorMessage = ref('')
const submitting = ref(false)
const assessmentSaved = ref(false)
const profileLoading = ref(false)
const profileSaving = ref(false)
const profileVerified = ref(false)
const questionLoading = ref(false)
const coreScaleReady = ref(false)
const supplementGroupReady = ref(false)
const supplementGroupStartIndex = ref(0)
const supplementGroupEndIndex = ref(0)
const submittedDialogVisible = ref(false)
const assessmentCategoryName = ref('')
const profileForm = reactive({ name: '', phone: '', idCard: '', school: '', major: '' })
const profileTouched = reactive<Record<ProfileFieldKey, boolean>>({ name: false, phone: false, idCard: false, school: false, major: false })
const profileFields: Array<{
  key: ProfileFieldKey
  label: string
  icon: string
  placeholder: string
  maxlength: number
  inputType: 'text' | 'number'
  required?: boolean
}> = [
  { key: 'name', label: '姓名', icon: 'account', placeholder: '请输入姓名', maxlength: 20, inputType: 'text', required: true },
  { key: 'phone', label: '手机号', icon: 'phone', placeholder: '请输入手机号', maxlength: 11, inputType: 'number', required: true },
  { key: 'idCard', label: '身份证号', icon: 'file-text', placeholder: '请输入身份证号', maxlength: 18, inputType: 'text' },
  { key: 'school', label: '毕业院校', icon: 'home', placeholder: '请输入毕业院校', maxlength: 40, inputType: 'text' },
  { key: 'major', label: '专业', icon: 'file-text', placeholder: '请输入专业', maxlength: 30, inputType: 'text' }
]
const currentQuestion = computed(() => questionCache.value[currentIndex.value] || null)
const assessmentTitle = computed(() => assessmentCategoryName.value || '自我测评')
const isCoreScaleQuestion = (question: AssessmentQuestion | null | undefined) => question?.stepName?.trim() === CORE_SCALE_STEP_NAME
const isSupplementQuestion = (question: AssessmentQuestion | null | undefined) => question?.stepName?.trim() === SUPPLEMENT_STEP_NAME
const isSingleChoiceQuestion = (question: AssessmentQuestion | null | undefined) =>
  question?.type === '单选题' || question?.type === 'single_choice'
const normalizeOptionText = (value: string) => value.trim().replace(/\s+/g, ' ')
const optionSignature = (question: AssessmentQuestion) => question.options
  .map((option) => normalizeOptionText(option.content || option.label))
  .join('\u001f')
const hasSameOptions = (left: AssessmentQuestion, right: AssessmentQuestion) =>
  left.options.length > 0 && optionSignature(left) === optionSignature(right)
const isUniformSupplementQuestion = (question: AssessmentQuestion | null | undefined, reference?: AssessmentQuestion) =>
  Boolean(question && isSupplementQuestion(question) && isSingleChoiceQuestion(question)
    && (!reference || hasSameOptions(question, reference)))
const isCoreScale = computed(() => isCoreScaleQuestion(currentQuestion.value))
const isSupplement = computed(() => isSupplementQuestion(currentQuestion.value))
const coreScaleQuestions = computed(() => Object.values(questionCache.value)
  .filter((question) => isCoreScaleQuestion(question))
  .sort((left, right) => left.index - right.index))
const coreScaleStartIndex = computed(() => coreScaleQuestions.value[0]?.index ?? currentIndex.value)
const coreScaleGroupStartIndex = computed(() => {
  if (!isCoreScale.value) {
    return currentIndex.value
  }
  const offset = Math.max(0, currentIndex.value - coreScaleStartIndex.value)
  return coreScaleStartIndex.value + Math.floor(offset / CORE_SCALE_GROUP_SIZE) * CORE_SCALE_GROUP_SIZE
})
const coreScaleGroupQuestions = computed(() => coreScaleQuestions.value
  .filter((question) => question.index >= coreScaleGroupStartIndex.value
    && question.index < coreScaleGroupStartIndex.value + CORE_SCALE_GROUP_SIZE))
const showCoreScale = computed(() => isCoreScale.value && coreScaleReady.value && coreScaleGroupQuestions.value.length > 0)
const supplementGroupQuestions = computed(() => Object.values(questionCache.value)
  .filter((question) => question.index >= supplementGroupStartIndex.value
    && question.index <= supplementGroupEndIndex.value)
  .sort((left, right) => left.index - right.index))
const showSupplementGroup = computed(() => isSupplement.value
  && supplementGroupReady.value
  && supplementGroupQuestions.value.length > 1)
const showGroupedQuestion = computed(() => showCoreScale.value || showSupplementGroup.value)
const groupQuestions = computed(() => showSupplementGroup.value ? supplementGroupQuestions.value : coreScaleGroupQuestions.value)
const groupStartIndex = computed(() => showSupplementGroup.value ? supplementGroupStartIndex.value : coreScaleGroupStartIndex.value)
const displayGroupEndIndex = computed(() => showGroupedQuestion.value
  ? groupQuestions.value[groupQuestions.value.length - 1]?.index ?? currentIndex.value
  : currentIndex.value)
const isTextQuestion = computed(() => Boolean(currentQuestion.value && (currentQuestion.value.type === '文本题' || !currentQuestion.value.options.length)))
const isOptionalQuestion = computed(() => currentQuestion.value?.isRequired === false)
const selectedIds = computed(() => currentQuestion.value ? answers.value[currentQuestion.value.id] || [] : [])
const currentAnswer = computed({ get: () => currentQuestion.value ? textAnswers.value[currentQuestion.value.id] || '' : '', set: (value: string) => { if (currentQuestion.value) textAnswers.value[currentQuestion.value.id] = value } })
const previousIndex = computed(() => showGroupedQuestion.value ? groupStartIndex.value - 1 : currentIndex.value - 1)
const previousTargetIsGroup = ref(false)
const nextTargetIsGroup = ref(false)
const actionLabelRefreshId = ref(0)
const previousActionLabel = computed(() => previousTargetIsGroup.value ? '上一组' : '上一题')
const nextActionLabel = computed(() => nextTargetIsGroup.value ? '下一组' : '下一题')
const isLast = computed(() => totalQuestions.value > 0 && displayGroupEndIndex.value >= totalQuestions.value - 1)
const progress = computed(() => totalQuestions.value ? Math.round(((displayGroupEndIndex.value + 1) / totalQuestions.value) * 100) : 0)
const progressLabel = computed(() => totalQuestions.value
  ? `${showGroupedQuestion.value ? `${groupStartIndex.value + 1}-${displayGroupEndIndex.value + 1}` : currentIndex.value + 1}/${totalQuestions.value}`
  : '')
const coreScaleCanSubmit = computed(() => coreScaleGroupQuestions.value.every((question) =>
  question.isRequired === false || (answers.value[question.id] || []).length > 0))
const supplementGroupCanSubmit = computed(() => supplementGroupQuestions.value.every((question) =>
  question.isRequired === false || (answers.value[question.id] || []).length > 0))
const canSubmit = computed(() => showCoreScale.value
  ? coreScaleCanSubmit.value
  : showSupplementGroup.value
    ? supplementGroupCanSubmit.value
  : isOptionalQuestion.value || (isTextQuestion.value ? Boolean(currentAnswer.value.trim()) : selectedIds.value.length > 0))
const stateTitle = computed(() => status.value === 'loading' ? '正在加载自测题目' : status.value === 'empty' ? '暂无可用自测题目' : '自测题目加载失败')
const nameValid = computed(() => /^[\u4e00-\u9fa5A-Za-z·\s]{2,20}$/.test(profileForm.name.trim()))
const phoneValid = computed(() => /^1\d{10}$/.test(profileForm.phone.trim()))
const canSaveProfile = computed(() => nameValid.value && phoneValid.value && !profileSaving.value)
const profileValidationMessage = computed(() => {
  if (!profileForm.name.trim()) return '请输入姓名'
  if (!nameValid.value) return '姓名需为 2-20 位中文、英文或间隔点'
  if (!profileForm.phone.trim()) return '请输入手机号'
  if (!phoneValid.value) return '请输入正确的 11 位手机号'
  return ''
})

const resolveSavedOptionIds = (question: AssessmentQuestion, optionIds: string[]) => {
  if (question.type === '文本题' || !question.options.length) {
    return optionIds
  }
  return optionIds
    .map((optionId) => {
      const normalizedOptionId = optionId.trim()
      if (!normalizedOptionId) {
        return ''
      }
      const matchedOption = question.options.find((option) =>
        option.id === normalizedOptionId || option.label === normalizedOptionId
      )
      return matchedOption?.id || normalizedOptionId
    })
    .filter(Boolean)
}

const restoreSavedAnswer = (question: AssessmentQuestion) => {
  const selectedOptionIds = savedAnswers.value[question.id]
  if (!selectedOptionIds?.length || answers.value[question.id]?.length) {
    return
  }
  const restoredOptionIds = resolveSavedOptionIds(question, selectedOptionIds)
  if (question.type === '文本题' || !question.options.length) {
    textAnswers.value[question.id] = restoredOptionIds[0] || ''
    answers.value[question.id] = restoredOptionIds[0] ? [restoredOptionIds[0]] : []
    return
  }
  answers.value[question.id] = restoredOptionIds
}

const cacheQuestion = (question: AssessmentQuestion) => {
  questionCache.value = { ...questionCache.value, [question.index]: question }
  restoreSavedAnswer(question)
}

const fetchQuestionAt = async (targetIndex: number) => {
  const cachedQuestion = questionCache.value[targetIndex]
  if (cachedQuestion) {
    restoreSavedAnswer(cachedQuestion)
    return cachedQuestion
  }

  const page = await fetchAssessmentQuestion(targetIndex)
  assessmentCategoryName.value = page.categoryName || assessmentCategoryName.value
  totalQuestions.value = page.totalQuestions
  if (!page.question) {
    throw new Error('自测题目加载失败')
  }
  cacheQuestion(page.question)
  return page.question
}

const loadCoreScaleGroup = async (seedQuestion: AssessmentQuestion) => {
  coreScaleReady.value = false
  supplementGroupReady.value = false
  let groupStart = seedQuestion.index
  let groupEnd = seedQuestion.index

  while (groupStart > 0) {
    const previousQuestion = await fetchQuestionAt(groupStart - 1)
    if (!isCoreScaleQuestion(previousQuestion)) {
      break
    }
    groupStart = previousQuestion.index
  }

  while (groupEnd < totalQuestions.value - 1) {
    const nextQuestion = await fetchQuestionAt(groupEnd + 1)
    if (!isCoreScaleQuestion(nextQuestion)) {
      break
    }
    groupEnd = nextQuestion.index
  }

  const groupOffset = Math.max(0, seedQuestion.index - groupStart)
  currentIndex.value = groupStart + Math.floor(groupOffset / CORE_SCALE_GROUP_SIZE) * CORE_SCALE_GROUP_SIZE
  coreScaleReady.value = coreScaleQuestions.value.length > 0
}

const loadSupplementGroup = async (seedQuestion: AssessmentQuestion) => {
  supplementGroupReady.value = false
  coreScaleReady.value = false
  let groupStart = seedQuestion.index
  let groupEnd = seedQuestion.index

  while (groupStart > 0) {
    const previousQuestion = await fetchQuestionAt(groupStart - 1)
    if (!isUniformSupplementQuestion(previousQuestion, seedQuestion)) {
      break
    }
    groupStart = previousQuestion.index
  }

  while (groupEnd < totalQuestions.value - 1) {
    const nextQuestion = await fetchQuestionAt(groupEnd + 1)
    if (!isUniformSupplementQuestion(nextQuestion, seedQuestion)) {
      break
    }
    groupEnd = nextQuestion.index
  }

  supplementGroupStartIndex.value = groupStart
  supplementGroupEndIndex.value = groupEnd
  currentIndex.value = groupStart
  supplementGroupReady.value = groupEnd - groupStart + 1 > 1
}

const isGroupedDestination = async (targetIndex: number) => {
  if (targetIndex < 0 || targetIndex >= totalQuestions.value) {
    return false
  }
  const targetQuestion = await fetchQuestionAt(targetIndex)
  if (isCoreScaleQuestion(targetQuestion)) {
    return true
  }
  if (!isUniformSupplementQuestion(targetQuestion)) {
    return false
  }
  const previousQuestion = targetIndex > 0 ? await fetchQuestionAt(targetIndex - 1) : null
  if (isUniformSupplementQuestion(previousQuestion, targetQuestion)) {
    return true
  }
  const nextQuestion = targetIndex < totalQuestions.value - 1 ? await fetchQuestionAt(targetIndex + 1) : null
  return isUniformSupplementQuestion(nextQuestion, targetQuestion)
}

const refreshActionLabels = async () => {
  const refreshId = ++actionLabelRefreshId.value
  const [previousIsGroup, nextIsGroup] = await Promise.all([
    isGroupedDestination(previousIndex.value).catch(() => false),
    isGroupedDestination(displayGroupEndIndex.value + 1).catch(() => false)
  ])
  if (refreshId !== actionLabelRefreshId.value) {
    return
  }
  previousTargetIsGroup.value = previousIsGroup
  nextTargetIsGroup.value = nextIsGroup
}

const loadQuestions = async () => {
  if (!profileVerified.value) return
  questionLoading.value = true
  coreScaleReady.value = false
  supplementGroupReady.value = false
  status.value = 'loading'; errorMessage.value = ''
  try {
    const firstPage = await fetchAssessmentQuestions()
    assessmentCategoryName.value = firstPage.categoryName || assessmentCategoryName.value
    questionCache.value = {}
    totalQuestions.value = firstPage.totalQuestions
    currentIndex.value = firstPage.currentIndex; answers.value = {}; textAnswers.value = {}; savedAnswers.value = firstPage.savedAnswers || {}
    if (firstPage.question) {
      cacheQuestion(firstPage.question)
      if (isCoreScaleQuestion(firstPage.question)) {
        await loadCoreScaleGroup(firstPage.question)
      } else if (isUniformSupplementQuestion(firstPage.question)) {
        await loadSupplementGroup(firstPage.question)
      }
      await refreshActionLabels()
    }
    assessmentSaved.value = false
    status.value = firstPage.question && firstPage.totalQuestions > 0 ? 'ready' : 'empty'
  } catch (error) {
    status.value = 'error'; errorMessage.value = error instanceof Error ? error.message : '自测题目加载失败'
  } finally {
    stage.value = 'questions'
    questionLoading.value = false
  }
}
const fillProfilePhoneFromSession = () => { profileForm.phone = appState.userSession?.phone || '' }
const updateProfileField = (key: ProfileFieldKey, value: string) => { profileForm[key] = value }
const resetProfileForm = () => {
  profileForm.name = ''; fillProfilePhoneFromSession(); profileForm.idCard = ''; profileForm.school = ''; profileForm.major = ''
  ;(Object.keys(profileTouched) as ProfileFieldKey[]).forEach((key) => { profileTouched[key] = false })
}
const applyCustomerProfile = (profile: CustomerProfile) => {
  profileForm.name = profile.realName || profileForm.name
  profileForm.phone = profile.mobile || appState.userSession?.phone || ''
  profileForm.idCard = profile.idCard || profileForm.idCard
  profileForm.school = profile.schoolName || profileForm.school
  profileForm.major = profile.majorName || profileForm.major
}
const initializeProfile = async () => {
  resetProfileForm()
  profileLoading.value = true
  try {
    applyCustomerProfile(await fetchCurrentCustomer())
  } catch {
    fillProfilePhoneFromSession()
    uni.showToast({ title: '部分资料加载失败，请重新填写', icon: 'none' })
  } finally {
    profileLoading.value = false
  }
}
const markProfileFieldTouched = (key: ProfileFieldKey) => { profileTouched[key] = true }
const getProfileFieldError = (key: ProfileFieldKey) => {
  const value = profileForm[key].trim()
  if (!profileTouched[key] && !value) return ''
  if (key === 'name') {
    if (!value) return '请填写姓名，方便生成自测报告'
    if (!nameValid.value) return '姓名支持 2-20 位中文、英文或间隔点'
  }
  if (key === 'phone') {
    if (!value) return '请填写手机号，需为 11 位大陆手机号'
    if (!phoneValid.value) return '手机号格式还不对，请检查 11 位数字'
  }
  return ''
}
const submitProfile = async () => {
  if (!canSaveProfile.value) {
    ;(Object.keys(profileTouched) as ProfileFieldKey[]).forEach((key) => { profileTouched[key] = true })
    uni.showToast({ title: profileValidationMessage.value || '请完善资料', icon: 'none' })
    return
  }
  profileSaving.value = true
  questionLoading.value = true
  try {
    await saveCustomerInfo({
      realName: profileForm.name.trim(),
      idCard: profileForm.idCard.trim(),
      schoolName: profileForm.school.trim(),
      majorName: profileForm.major.trim()
    })
    profileVerified.value = true
    await loadQuestions()
  } catch (error) {
    questionLoading.value = false
    uni.showToast({ title: error instanceof Error ? error.message : '学员信息保存失败', icon: 'none' })
  } finally { profileSaving.value = false }
}
const toggleQuestionOption = (questionId: string, optionId: string) => {
  const question = Object.values(questionCache.value).find((item) => item.id === questionId)
  if (!question) return
  const current = answers.value[questionId] || []
  const multiple = question.type === '多选题'
  answers.value[questionId] = multiple
    ? (current.includes(optionId) ? current.filter((item) => item !== optionId) : [...current, optionId])
    : [optionId]
}

const toggleOption = (id: string) => {
  if (!currentQuestion.value) return
  toggleQuestionOption(currentQuestion.value.id, id)
}
const loadQuestion = async (targetIndex: number) => {
  questionLoading.value = true
  coreScaleReady.value = false
  supplementGroupReady.value = false
  try {
    const question = await fetchQuestionAt(targetIndex)
    if (isCoreScaleQuestion(question)) {
      await loadCoreScaleGroup(question)
    } else if (isUniformSupplementQuestion(question)) {
      await loadSupplementGroup(question)
    } else {
      currentIndex.value = question.index
    }
    await refreshActionLabels()
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '自测题目加载失败', icon: 'none' })
  } finally {
    questionLoading.value = false
  }
}
const goPrevious = async () => {
  if (previousIndex.value >= 0) {
    await loadQuestion(previousIndex.value)
  }
}
const goNext = async () => {
  await loadQuestion(displayGroupEndIndex.value + 1)
}
const submitCurrent = async () => {
  if (!currentQuestion.value || !canSubmit.value || submitting.value) return
  if (isTextQuestion.value && currentQuestion.value) answers.value[currentQuestion.value.id] = [currentAnswer.value.trim()]
  if (!isLast.value) { await goNext(); return }
  submitting.value = true
  try {
    let submissionPromise: ReturnType<typeof submitAssessmentAnswers> | null = null
    if (!assessmentSaved.value) {
      const loadedQuestions = Object.entries(questionCache.value)
        .sort(([leftIndex], [rightIndex]) => Number(leftIndex) - Number(rightIndex))
        .map(([, question]) => question)
      submissionPromise = submitAssessmentAnswers(loadedQuestions.map((question) => ({ questionId: question.id, selectedOptionIds: answers.value[question.id] || [] })))
    }
    submittedDialogVisible.value = true
    await nextTick()
    if (submissionPromise) {
      await submissionPromise
      assessmentSaved.value = true
    }
  } catch (error) {
    submittedDialogVisible.value = false
    uni.showToast({
      title: error instanceof Error ? error.message : '自测提交失败',
      icon: 'none'
    })
  } finally { submitting.value = false }
}
const returnHome = () => {
  submittedDialogVisible.value = false
  uni.reLaunch({ url: '/pages/home' })
}
const goBack = () => uni.navigateBack({ delta: 1, fail: () => uni.reLaunch({ url: '/pages/home' }) })
onLoad(() => { if (requireLogin()) void initializeProfile() })
</script>

<style lang="scss">

page {
  min-height: 100%;
  background: #F8FBFF;
}

.self-test-page {
  position: relative;
  height: 100vh;
  overflow: hidden;
  color: #000;
  font-family: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.self-test-page__backdrop {
  position: fixed;
  inset: 0;
  background-color: #F8FBFF;
  background-image:
    radial-gradient(circle at 7.3% 92.4%, rgba(157, 201, 242, .28) 0 4rpx, transparent 5rpx),
    radial-gradient(circle at 37.9% 98.4%, rgba(157, 201, 242, .24) 0 5rpx, transparent 6rpx),
    linear-gradient(rgba(248, 251, 255, .82), rgba(248, 251, 255, .82)),
    url('@/static/practice-start/paper-texture.jpg');
  background-repeat: no-repeat, no-repeat, no-repeat, repeat;
  background-size: 100% 100%, 100% 100%, 100% 100%, 256rpx 150rpx;
}

.self-test-page__backdrop::before,
.self-test-page__backdrop::after {
  content: '';
  position: absolute;
  opacity: 1;
  background-repeat: no-repeat;
  background-size: 100% 100%;
  pointer-events: none;
}

.self-test-page__backdrop::before {
  top: 0;
  right: 0;
  width: 257.6rpx;
  height: 158.3rpx;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http%3A//www.w3.org/2000/svg' viewBox='0 0 293 180'%3E%3Cg fill='none' stroke='%23f4ac7c' stroke-opacity='.10' stroke-width='1.05' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='43,0 49,10 57,20 67,30 84,40 124,50 171,60 190,70 202,80 211,90 218,100 244,125 253,135 264,145 276,155 287,165 293,171'/%3E%3Cpolyline points='84,0 92,10 105,20 127,30 166,40 194,50 209,60 220,70 231,80 238,89 249,95 255,105 265,115 275,125 288,135 293,139'/%3E%3Cpolyline points='129,0 145,10 170,20 190,30 204,40 215,50 224,60 231,70 238,80 244,90 246,95 260,105 280,115 293,122'/%3E%3Cpolyline points='179,0 196,10 212,20 225,30 235,40 245,50 253,60 260,70 269,80 279,90 290,100 293,102'/%3E%3Cpolyline points='220,0 232,10 243,20 253,30 262,40 272,50 282,60 293,69'/%3E%3Cpolyline points='257,0 266,10 275,20 286,30 293,35'/%3E%3Cpolyline points='286,0 293,7'/%3E%3C/g%3E%3C/svg%3E");
}

.self-test-page__backdrop::after {
  bottom: 0;
  left: 0;
  width: 250.6rpx;
  height: 170.6rpx;
  transform: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http%3A//www.w3.org/2000/svg' viewBox='0 0 285 194'%3E%3Cg fill='none' stroke='%23f4ac7c' stroke-opacity='.10' stroke-width='1.05' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='0,29 15,50 30,69 45,80 60,85 75,88 90,88 105,90 120,95 135,104 150,119 165,136 180,149 195,159 210,168 225,178 241,194'/%3E%3Cpolyline points='0,63 15,78 30,92 45,102 60,109 75,113 90,114 105,116 120,124 135,135 150,148 165,160 180,172 195,187 201,194'/%3E%3Cpolyline points='0,109 15,122 30,132 45,138 60,140 75,141 90,143 105,148 120,158 135,172 150,187 157,194'/%3E%3Cpolyline points='0,144 15,156 30,164 45,170 60,172 75,173 90,173 105,176 120,184 131,194'/%3E%3Cpolyline points='0,171 15,179 30,186 45,190 60,192 72,194'/%3E%3C/g%3E%3C/svg%3E");
}

.self-test-page__scroll {
  position: relative;
  z-index: 1;
  height: 100vh;
}

.self-test-page__content {
  position: relative;
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--app-safe-area-top) 28rpx calc(env(safe-area-inset-bottom) + 175rpx);
}

.self-test-nav {
  height: var(--app-page-header-height);
  display: grid;
  grid-template-columns: 150rpx minmax(0, 1fr) 150rpx;
  align-items: center;
}

.self-test-nav button {
  width: 72rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.self-test-nav__back {
  margin-left: 5rpx !important;
  transform: none;
}

.self-test-nav button::after {
  border: 0;
}

.self-test-nav__back .uv-icon,
.self-test-nav__back .uv-icon__icon {
  color: #080808 !important;
  font-weight: 700;
}

.self-test-nav__back .uv-icon__icon {
  transform: translateY(-.5rpx) scaleX(1.03) scaleY(1);
  transform-origin: left top;
}

.self-test-nav__title {
  color: #000;
  font-size: 39.5rpx;
  line-height: 1.2;
  font-weight: 500;
  -webkit-text-stroke: .7rpx #000;
  text-align: center;
  transform: translateX(-.5rpx) scaleX(.995) scaleY(.98);
}

.self-test-nav__count {
  padding-right: 7.5rpx;
  color: #090909;
  font-size: 25rpx;
  line-height: 1.2;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
  transform: scaleX(1.195) scaleY(.96);
  transform-origin: right center;
}

.self-test-progress {
  height: 7rpx;
  margin: 24rpx 6rpx 45rpx 5rpx;
  overflow: hidden;
  border-radius: 99rpx;
  background: #EDF5FD;
}

.self-test-progress__bar {
  height: 100%;
  min-width: 41.5rpx;
  border-radius: inherit;
  background: #0868F4;
}

.self-test-card {
  position: relative;
  box-sizing: border-box;
  height: auto;
  min-height: 1234rpx;
  min-height: max(
    1234rpx,
    calc(100vh - var(--app-safe-area-top) - env(safe-area-inset-bottom) - 387rpx)
  );
  padding: 40rpx 33rpx 170rpx 30rpx;
  border: 2rpx solid #dce7f2;
  border-radius: 23rpx;
  background: rgba(255, 255, 255, .3);
  box-shadow: none;
}

.self-test-card__intro {
  height: 46rpx;
  display: flex;
  align-items: flex-start;
}

.self-test-card__owl {
  width: 68rpx;
  height: 68rpx;
  flex: 0 0 68rpx;
  overflow: hidden;
  border-radius: 50%;
  background-image: url("@/static/brand/ai-assistant-logo.png");
  background-repeat: no-repeat;
  background-size: cover;
  background-position: center;
  transform: translate(.75rpx, -5.65rpx);
}

.self-test-card__intro-copy {
  min-width: 0;
  margin-left: 18rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
}

.self-test-card__type {
  box-sizing: border-box;
  height: 46rpx;
  margin-left: 20rpx;
  padding: 0 14rpx;
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  border: 2rpx solid #005BD8;
  border-radius: 12rpx;
  color: #005BD8;
  font-size: 24rpx;
  line-height: 1;
  font-weight: 400;
}

.self-test-card__title {
  color: #000;
  font-size: 34rpx;
  line-height: 1.2;
  font-weight: 500;
  -webkit-text-stroke: .55rpx #000;
  white-space: nowrap;
  transform: translate(1rpx, 1rpx) scaleX(.975) scaleY(.97);
  transform-origin: left center;
}

.self-test-card__stem {
  display: block;
  margin-top: 40rpx;
  color: #000;
  font-size: 36rpx;
  line-height: 49rpx;
  font-weight: 600;
}

.self-test-options {
  display: flex;
  flex-direction: column;
  gap: 19.9rpx;
  margin-top: 34rpx;
}

.self-test-option {
  box-sizing: border-box;
  width: 100%;
  height: auto;
  min-height: 121rpx;
  margin: 0;
  padding: 20rpx 72rpx 20rpx 26rpx;
  display: flex;
  align-items: center;
  gap: 8rpx;
  border: 2rpx solid #C9D8E8;
  border-radius: 14rpx;
  background:
    radial-gradient(
      circle at calc(100% - 47rpx) 50%,
      transparent 0 15.5rpx,
      #8ea4ba 16rpx 19rpx,
      transparent 19.5rpx
    ),
    rgba(255, 255, 255, .32);
  color: #000;
  line-height: 1.2;
  text-align: left;
}

.self-test-option::after {
  content: none;
  display: none;
}

.self-test-option .uv-icon {
  display: none;
}

.self-test-option--selected {
  border-color: #005BD8;
  background:
    radial-gradient(
      circle at calc(100% - 47rpx) 50%,
      #fff 0 7rpx,
      #0A67DA 7.5rpx 19.5rpx,
      transparent 20rpx
    ),
    #EAF4FF;
  color: #000;
}

.self-test-option--selected::after {
  content: none;
  display: none;
}

.self-test-option__label {
  flex: 0 0 auto;
  font-size: 30rpx;
  line-height: 1.2;
  font-weight: 700;
  transform: translate(0, -1rpx) scaleX(.84) scaleY(.97);
  transform-origin: left center;
}

.self-test-option__label::after {
  content: '.';
  position: relative;
  left: 1rpx;
}

.self-test-option__content {
  min-width: 0;
  flex: 1;
  font-size: 30rpx;
  line-height: 1.2;
  font-weight: 400;
  transform: translateY(-1rpx) scaleX(.89) scaleY(.97);
  transform-origin: left center;
}

.self-test-card__text-input {
  box-sizing: border-box;
  width: 100%;
  min-height: 200rpx;
  margin-top: 34rpx;
  padding: 24rpx 27rpx;
  border: 2rpx solid #C9D8E8;
  border-radius: 14rpx;
  background: rgba(255, 255, 255, .32);
  color: #000;
  font-size: 30rpx;
  line-height: 1.5;
}

.self-test-actions {
  position: relative;
  z-index: 2;
  box-sizing: border-box;
  width: calc(100% - 66rpx);
  margin: -142rpx 35rpx 0 32rpx;
  display: flex;
  gap: 18rpx;
}

.self-test-page--core-scale .self-test-actions,
.self-test-page--grouped .self-test-actions {
  width: calc(100% - 66rpx);
  margin: 28rpx 35rpx calc(env(safe-area-inset-bottom) + 24rpx) 32rpx;
  gap: 28rpx;
}

.self-test-submit,
.self-test-previous {
  position: relative;
  z-index: 2;
  box-sizing: border-box;
  height: 94rpx;
  margin: 0;
  padding: 0 0 0 4rpx;
  border: 0;
  border-radius: 14rpx;
  font-size: 35rpx;
  line-height: 90rpx;
  font-weight: 500;
  text-align: center;
}

.self-test-submit {
  min-width: 0;
  flex: 1;
  background: #005BD8;
  color: #fff;
  -webkit-text-stroke: .3rpx #fff;
}

.self-test-previous {
  width: 190rpx;
  flex: 0 0 190rpx;
  border: 2rpx solid #005BD8;
  background: rgba(255, 255, 255, .72);
  color: #005BD8;
}

.self-test-page--core-scale .self-test-submit,
.self-test-page--core-scale .self-test-previous,
.self-test-page--grouped .self-test-submit,
.self-test-page--grouped .self-test-previous {
  width: auto;
  min-width: 0;
  flex: 1 1 0;
}

.self-test-submit::after,
.self-test-previous::after {
  border: 0;
}

.self-test-submit[disabled] {
  opacity: 1 !important;
  background: #CFE5FB !important;
  color: #fff !important;
}

.self-test-previous[disabled] {
  opacity: .55 !important;
}
.profile-dialog {
  position: fixed;
  z-index: 41;
  inset: 0;
  box-sizing: border-box;
  min-height: 100vh;
  overflow-y: auto;
  isolation: isolate;
  padding: var(--app-safe-area-top) 55rpx calc(env(safe-area-inset-bottom) + 120rpx) 52rpx;
  background:
    linear-gradient(rgba(247, 250, 254, .9), rgba(247, 250, 254, .9)),
    url('@/static/practice-start/paper-texture.jpg') center / 256rpx 150rpx repeat;
  color: #09264b;
}

.profile-dialog::before,
.profile-dialog::after {
  content: '';
  position: fixed;
  z-index: 0;
  opacity: 1;
  pointer-events: none;
  background-repeat: no-repeat;
  background-position: center;
  background-size: 100% 100%;
}

.profile-dialog::before {
  top: 0;
  right: 0;
  width: 205rpx;
  height: 378rpx;
  background-image: url('@/static/practice-record/self-test-contour-top-reference.png');
}

.profile-dialog::after {
  right: 0;
  bottom: 0;
  width: 328rpx;
  height: 259rpx;
  background-image: url('@/static/practice-record/self-test-contour-bottom-reference.png');
}

.profile-dialog__header {
  position: relative;
  z-index: 1;
  height: 307rpx;
}

.profile-dialog__close {
  position: absolute;
  top: 0;
  left: -18rpx;
  z-index: 1;
  width: 76rpx;
  height: var(--app-page-header-height);
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
}

.profile-dialog__close::after {
  border: 0;
}

.profile-dialog__close .uv-icon {
  position: absolute;
  top: 7rpx;
  left: 2rpx;
}

.profile-dialog__close .uv-icon__icon {
  -webkit-text-stroke: 2rpx #111;
  transform: scaleX(.93);
}

.profile-dialog__page-title {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  display: block;
  color: #09264b;
  font-size: 40rpx;
  line-height: var(--app-page-header-height);
  font-weight: 700;
  text-align: center;
}

.profile-dialog__intro {
  position: absolute;
  bottom: 53rpx;
  left: -3rpx;
  display: flex;
  align-items: center;
  gap: 23rpx;
}

.profile-dialog__mascot {
  width: 68rpx;
  height: 68rpx;
  flex: 0 0 68rpx;
  overflow: hidden;
  border-radius: 50%;
  background-image: url("@/static/brand/ai-assistant-logo.png");
  background-repeat: no-repeat;
  background-position: center;
  background-size: cover;
}

.profile-dialog__heading {
  color: #09264b;
  font-size: 34rpx;
  line-height: 48rpx;
  font-weight: 700;
  transform: translateY(1rpx);
}

.profile-form {
  position: relative;
  z-index: 1;
  margin: 0;
}

.profile-field-wrap {
  margin: 0 0 52rpx;
}

.profile-field__label {
  display: block;
  margin: 0 0 21rpx;
  color: #09264b;
  font-size: 30rpx;
  line-height: 44rpx;
  font-weight: 700;
}

.profile-field__optional {
  display: inline-block;
  height: 44rpx;
  margin-left: 0;
  color: #929292;
  font-size: 26rpx;
  line-height: 44rpx;
  font-weight: 500;
  transform: translateY(4rpx);
  vertical-align: top;
}

.profile-field {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  height: 100rpx;
  padding: 0 24rpx;
  border: 2rpx solid #dce7f2;
  border-radius: 15rpx;
  background: rgba(255, 251, 251, .72);
}

.profile-field--disabled {
  background: rgba(233, 240, 247, .78);
}

.profile-field__input {
  flex: 1;
  min-width: 0;
  height: 96rpx;
  color: #09264b;
  font-size: 31.5rpx;
  line-height: 96rpx;
  font-weight: 400;
}

.profile-field__placeholder {
  color: #8ea4ba;
}

.profile-field-error {
  display: block;
  margin: 10rpx 0 0 4rpx;
  color: #c9715f;
  font-size: 20rpx;
  line-height: 1.4;
  font-weight: 650;
}

.profile-dialog__submit {
  width: 100%;
  height: 100rpx;
  margin-top: 64rpx;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 15rpx;
  background: #005BD8;
  box-shadow: none;
  color: #fff;
  font-size: 37rpx;
  line-height: 1;
  font-weight: 500;
}

.profile-dialog__submit::after {
  border: 0;
}

.profile-dialog__submit--disabled {
  opacity: 1;
  background: #005BD8;
}
</style>
