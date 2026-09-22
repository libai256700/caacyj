<template>
  <template v-if="!testingRow">
    <ContentWrap>
      <div class="flex flex-wrap items-center justify-between gap-12px">
        <div>
          <div class="text-18px font-semibold">知识库管理</div>
          <div class="mt-4px text-13px text-gray-500">维护知识库、条目数量、接口地址和启停状态</div>
        </div>
        <el-button @click="getList">
          <Icon icon="ep:refresh" class="mr-5px" />
          刷新
        </el-button>
      </div>
    </ContentWrap>

    <ContentWrap>
      <el-form :inline="true" :model="queryParams" class="-mb-15px" label-width="96px">
        <el-form-item label="关键字">
          <el-input
            v-model="queryParams.keyword"
            class="!w-240px"
            clearable
            placeholder="请输入知识库名称"
            @keyup.enter="handleQuery"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="queryParams.status" class="!w-180px" clearable placeholder="请选择状态">
            <el-option label="启用" :value="true" />
            <el-option label="停用" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="handleQuery">
            <Icon icon="ep:search" class="mr-5px" />
            搜索
          </el-button>
          <el-button @click="resetQuery">
            <Icon icon="ep:refresh" class="mr-5px" />
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </ContentWrap>

    <ContentWrap>
      <el-table v-loading="loading" :data="list" :show-overflow-tooltip="true" :stripe="true">
        <el-table-column label="编号" align="center" prop="id" width="90" />
        <el-table-column label="知识库名称" align="center" prop="name" min-width="180" />
        <el-table-column label="条目数量" align="center" prop="item_count" width="100" />
        <el-table-column label="状态" align="center" prop="status" width="100">
          <template #default="{ row }">
            <el-switch v-model="row.status" @change="handleStatusChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" align="center" prop="update_time" width="170">
          <template #default="{ row }">{{ formatDateText(row.update_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" align="center" fixed="right" width="120">
          <template #default="{ row }">
            <el-button link type="primary" @click="openTest(row)">测试</el-button>
          </template>
        </el-table-column>
      </el-table>
      <Pagination
        v-model:limit="queryParams.pageSize"
        v-model:page="queryParams.pageNo"
        :total="total"
        @pagination="getList"
      />
    </ContentWrap>
  </template>

  <template v-else>
    <ContentWrap>
      <div class="flex flex-wrap items-center justify-between gap-12px">
        <div>
          <div class="text-18px font-semibold">{{ testingRow.name }}测试</div>
          <div class="mt-4px max-w-900px text-13px text-gray-500">{{ testingRow.interface_url || '-' }}</div>
        </div>
        <el-button @click="backToList">
          <Icon icon="ep:back" class="mr-5px" />
          返回
        </el-button>
      </div>
    </ContentWrap>

    <ContentWrap>
      <el-form label-position="top">
        <el-form-item label="输入内容">
          <el-input
            v-model="testQuestion"
            type="textarea"
            :rows="8"
            maxlength="4000"
            show-word-limit
            placeholder="请输入要发送给知识库的内容"
          />
        </el-form-item>
        <el-form-item>
          <el-button :disabled="testLoading" :loading="testLoading" type="primary" @click="sendTest">
            <Icon icon="ep:promotion" class="mr-5px" />
            发送
          </el-button>
        </el-form-item>
        <el-form-item label="返回结果">
          <el-input
            v-model="testResult"
            type="textarea"
            :rows="12"
            readonly
            placeholder="发送后在这里显示知识库返回结果"
          />
        </el-form-item>
      </el-form>
    </ContentWrap>
  </template>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { YjApi, YjRecord } from '@/api/yj'
import { formatNullableDate } from '@/utils/formatTime'
import { useMessage } from '@/hooks/web/useMessage'

defineOptions({ name: 'YjKnowledgeBase' })

const message = useMessage()
const route = useRoute()
const router = useRouter()

const KNOWLEDGE_BASE_RESOURCE = 'knowledge-base'
const EXAM_KNOWLEDGE_BASE_NAME = '考试知识库'

const loading = ref(false)
const list = ref<YjRecord[]>([])
const total = ref(0)
const queryParams = reactive({
  pageNo: 1,
  pageSize: 10,
  keyword: '',
  status: undefined as boolean | undefined
})

const testingRow = ref<YjRecord>()
const testLoading = ref(false)
const testQuestion = ref('')
const testResult = ref('')

const getList = async () => {
  loading.value = true
  try {
    const data = await YjApi.getPage(KNOWLEDGE_BASE_RESOURCE, buildParams())
    list.value = (data.list || []).map(normalizeRow)
    total.value = data.total || 0
    await syncTestingRowFromRoute()
  } finally {
    loading.value = false
  }
}

const buildParams = () => {
  const params: Record<string, any> = {
    pageNo: queryParams.pageNo,
    pageSize: queryParams.pageSize
  }
  if (queryParams.keyword.trim()) params.keyword = queryParams.keyword.trim()
  if (queryParams.status !== undefined) params.status = queryParams.status
  return params
}

const handleQuery = async () => {
  queryParams.pageNo = 1
  await getList()
}

const resetQuery = async () => {
  queryParams.pageNo = 1
  queryParams.keyword = ''
  queryParams.status = undefined
  await getList()
}

const handleStatusChange = async (row: YjRecord) => {
  await YjApi.update(KNOWLEDGE_BASE_RESOURCE, { id: row.id, status: row.status })
  message.success('更新成功')
}

const openTest = async (row: YjRecord) => {
  testingRow.value = row
  testQuestion.value = ''
  testResult.value = ''
  await router.replace({ query: { ...route.query, testId: String(row.id) } })
}

const backToList = async () => {
  testingRow.value = undefined
  testQuestion.value = ''
  testResult.value = ''
  const nextQuery = { ...route.query }
  delete nextQuery.testId
  await router.replace({ query: nextQuery })
}

const sendTest = async () => {
  const row = testingRow.value
  const question = testQuestion.value.trim()
  if (!row) return
  if (!question) {
    message.warning('请输入要发送的内容')
    return
  }
  const interfaceUrl = String(row.interface_url || '').trim()
  if (!interfaceUrl) {
    message.warning('当前知识库未配置接口地址')
    return
  }

  testLoading.value = true
  testResult.value = ''
  try {
    const result = await requestKnowledgeBase(row, interfaceUrl, question)
    testResult.value = formatTestResult(result)
  } catch (error: any) {
    testResult.value = error?.message || '知识库访问失败'
    message.error('知识库访问失败')
  } finally {
    testLoading.value = false
  }
}

const requestKnowledgeBase = async (row: YjRecord, interfaceUrl: string, question: string) => {
  if (shouldUseOpenAiChat(row, interfaceUrl)) {
    return requestOpenAiCompatibleKnowledgeBase(interfaceUrl, question)
  }
  return YjApi.queryKnowledge(question)
}

const shouldUseOpenAiChat = (row: YjRecord, interfaceUrl: string) => {
  return String(row.name || '').trim() === EXAM_KNOWLEDGE_BASE_NAME || interfaceUrl.includes('/chat/completions')
}

const requestOpenAiCompatibleKnowledgeBase = async (interfaceUrl: string, question: string) => {
  const requestId = `admin-kb-test-${Date.now()}`
  const response = await fetch(interfaceUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'exam-kb-assistant',
      stream: false,
      messages: [{ role: 'user', content: question }],
      metadata: {
        session_id: requestId,
        question: {
          question_id: requestId,
          subject: '管理平台知识库测试',
          stem: question,
          options: [],
          correct_answer: '',
          student_answer: '',
          analysis_materials: []
        }
      }
    })
  })
  return parseResponse(response)
}

const parseResponse = async (response: Response) => {
  const text = await response.text()
  if (!response.ok) {
    throw new Error(text || `HTTP ${response.status}`)
  }
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

const formatTestResult = (result: any) => {
  const content = result?.choices?.[0]?.message?.content
  if (content) return String(content)
  if (typeof result === 'string') return result
  return JSON.stringify(result, null, 2)
}

const syncTestingRowFromRoute = async () => {
  const testId = Number(route.query.testId)
  if (!testId) return
  const existing = list.value.find((item) => Number(item.id) === testId)
  testingRow.value = existing || normalizeRow(await YjApi.get(KNOWLEDGE_BASE_RESOURCE, testId))
}

const normalizeRow = (row: YjRecord) => ({
  ...row,
  status: normalizeBool(row.status)
})

const normalizeBool = (value: any) => {
  if (value === true || value === 1 || value === '1') return true
  if (value === false || value === 0 || value === '0') return false
  return Boolean(value)
}

const formatDateText = (value: any) => formatNullableDate(value)

watch(
  () => route.query.testId,
  async () => {
    if (!route.query.testId) {
      testingRow.value = undefined
      return
    }
    await syncTestingRowFromRoute()
  }
)

onMounted(getList)
</script>
