<template>
  <template v-if="!detailRow">
    <ContentWrap>
      <div class="flex flex-wrap items-center justify-between gap-12px">
        <div>
          <div class="text-18px font-semibold">飞书文档采集</div>
          <div class="mt-4px text-13px text-gray-500">
            查看每个飞书文档的最近采集时间、采集状态和岗位结果概览。
          </div>
        </div>
        <el-button :loading="loading" @click="getList">
          <Icon icon="ep:refresh" class="mr-5px" />
          刷新
        </el-button>
      </div>
    </ContentWrap>

    <ContentWrap>
      <el-form :inline="true" :model="queryParams" class="-mb-15px" label-width="96px">
        <el-form-item label="文档关键字">
          <el-input
            v-model="queryParams.keyword"
            class="!w-260px"
            clearable
            placeholder="请输入文档名称或链接"
            @keyup.enter="handleQuery"
          />
        </el-form-item>
        <el-form-item label="目录标识">
          <el-input
            v-model="queryParams.folderToken"
            class="!w-260px"
            clearable
            placeholder="可选，按目录筛选"
            @keyup.enter="handleQuery"
          />
        </el-form-item>
        <el-form-item label="采集状态">
          <el-select
            v-model="queryParams.status"
            class="!w-180px"
            clearable
            placeholder="请选择状态"
          >
            <el-option
              v-for="option in statusOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleQuery">
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
        <el-table-column label="文档名称" min-width="380">
          <template #default="{ row }">
            <div class="document-name-cell" :title="row.documentName || '-'">
              {{ row.documentName || '-' }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="飞书文档链接" min-width="300">
          <template #default="{ row }">
            <el-link
              v-if="getExternalUrl(row.documentUrl)"
              :href="getExternalUrl(row.documentUrl)"
              target="_blank"
              rel="noopener noreferrer"
              :title="getExternalUrl(row.documentUrl)"
            >
              {{ getExternalUrl(row.documentUrl) }}
            </el-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="采集状态" prop="status" width="130">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近采集时间" prop="collectedAt" width="180">
          <template #default="{ row }">{{
            formatDateText(row.collectedAt || row.updateTime)
          }}</template>
        </el-table-column>
        <el-table-column label="解析岗位" prop="extractedCount" width="100" align="center" />
        <el-table-column label="新增" prop="createdCount" width="80" align="center" />
        <el-table-column label="跳过" prop="skippedCount" width="80" align="center" />
        <el-table-column label="失败" prop="failedCount" width="80" align="center" />
        <el-table-column label="最近错误" prop="lastError" min-width="220" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)"> 查看采集详情 </el-button>
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
          <div class="text-18px font-semibold">{{ detailRow.documentName || '飞书文档' }}</div>
          <div class="mt-4px max-w-1000px text-13px text-gray-500">
            <el-link
              v-if="getExternalUrl(detailRow.documentUrl)"
              :href="getExternalUrl(detailRow.documentUrl)"
              target="_blank"
              rel="noopener noreferrer"
            >
              {{ getExternalUrl(detailRow.documentUrl) }}
            </el-link>
            <span v-else>暂无文档链接</span>
          </div>
        </div>
        <el-button @click="backToList">
          <Icon icon="ep:back" class="mr-5px" />
          返回文档列表
        </el-button>
      </div>
    </ContentWrap>

    <ContentWrap>
      <el-descriptions v-loading="detailLoading" :column="4" border>
        <el-descriptions-item label="采集状态">
          <el-tag :type="statusType(detailRow.status)">{{ statusLabel(detailRow.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="本次采集时间">
          {{ formatDateText(run?.finishedAt || run?.startedAt || detailRow.collectedAt) }}
        </el-descriptions-item>
        <el-descriptions-item label="文档版本">
          {{ detailRow.documentRevisionId || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="内容摘要">
          {{ detailRow.contentHash ? detailRow.contentHash.slice(0, 12) + '...' : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="解析岗位">{{
          detailRow.extractedCount || 0
        }}</el-descriptions-item>
        <el-descriptions-item label="新增岗位">{{
          detailRow.createdCount || 0
        }}</el-descriptions-item>
        <el-descriptions-item label="跳过岗位">{{
          detailRow.skippedCount || 0
        }}</el-descriptions-item>
        <el-descriptions-item label="失败岗位">{{
          detailRow.failedCount || 0
        }}</el-descriptions-item>
        <el-descriptions-item v-if="detailRow.lastError" label="最近错误" :span="4">
          <span class="text-red-500">{{ detailRow.lastError }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </ContentWrap>

    <ContentWrap>
      <div class="mb-12px flex items-center justify-between">
        <div>
          <div class="text-16px font-semibold">本次采集的岗位</div>
          <div class="mt-4px text-13px text-gray-500">
            {{
              detailRow.status === 'SKIPPED'
                ? '该文档已成功采集，本次未重复读取；以下展示上次成功解析的岗位结果。'
                : '展示该文档本次采集解析并入库的岗位明细。'
            }}
          </div>
        </div>
        <el-button :loading="detailLoading" @click="loadDetail(detailRow)">
          <Icon icon="ep:refresh" class="mr-5px" />
          刷新详情
        </el-button>
      </div>
      <el-table
        v-loading="detailLoading"
        :data="items"
        :show-overflow-tooltip="true"
        :stripe="true"
      >
        <el-table-column label="#" prop="itemIndex" width="70" align="center" />
        <el-table-column label="岗位名称" prop="name" min-width="210" />
        <el-table-column label="企业名称" prop="companyName" min-width="180" />
        <el-table-column label="岗位链接" min-width="300">
          <template #default="{ row }">
            <el-link
              v-if="getExternalUrl(row.detailUrl)"
              :href="getExternalUrl(row.detailUrl)"
              target="_blank"
              rel="noopener noreferrer"
              :title="getExternalUrl(row.detailUrl)"
            >
              {{ getExternalUrl(row.detailUrl) }}
            </el-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="薪资范围" prop="salaryRange" min-width="130" />
        <el-table-column label="工作区域" prop="workArea" min-width="150" />
        <el-table-column label="入库状态" prop="status" width="120">
          <template #default="{ row }">
            <el-tag :type="itemStatusType(row.status)">{{ itemStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="正式岗位编号" prop="targetPostId" width="120" />
        <el-table-column label="失败原因" prop="errorMessage" min-width="220" />
      </el-table>
      <el-empty
        v-if="!detailLoading && items.length === 0"
        description="该文档本次没有解析出岗位"
      />
    </ContentWrap>
  </template>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { YjApi, YjRecord } from '@/api/yj'
import { formatNullableDate } from '@/utils/formatTime'

defineOptions({ name: 'YjFeishuDocument' })

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const detailLoading = ref(false)
const list = ref<YjRecord[]>([])
const total = ref(0)
const detailRow = ref<YjRecord>()
const run = ref<YjRecord>()
const items = ref<YjRecord[]>([])

const queryParams = reactive({
  pageNo: 1,
  pageSize: 10,
  keyword: '',
  folderToken: '',
  status: ''
})

const statusOptions = [
  { label: '未采集', value: 'NEW' },
  { label: '处理中', value: 'PROCESSING' },
  { label: '已采集', value: 'COLLECTED' },
  { label: '无岗位', value: 'NO_JOBS' },
  { label: '已采集，未重复读取', value: 'SKIPPED' },
  { label: '部分失败', value: 'PARTIAL_FAILED' },
  { label: '采集失败', value: 'FAILED' }
]

const getList = async () => {
  loading.value = true
  try {
    const data = await YjApi.getFeishuDocumentPage(buildParams())
    list.value = data.list || []
    total.value = data.total || 0
    await syncDetailRowFromRoute()
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
  if (queryParams.folderToken.trim()) params.folderToken = queryParams.folderToken.trim()
  if (queryParams.status) params.status = queryParams.status
  return params
}

const handleQuery = async () => {
  queryParams.pageNo = 1
  await getList()
}

const resetQuery = async () => {
  queryParams.pageNo = 1
  queryParams.keyword = ''
  queryParams.folderToken = ''
  queryParams.status = ''
  await getList()
}

const openDetail = async (row: YjRecord) => {
  detailRow.value = row
  await router.replace({ query: { ...route.query, documentId: String(row.id) } })
  await loadDetail(row)
}

const backToList = async () => {
  detailRow.value = undefined
  run.value = undefined
  items.value = []
  const nextQuery = { ...route.query }
  delete nextQuery.documentId
  await router.replace({ query: nextQuery })
}

const loadDetail = async (row: YjRecord) => {
  detailLoading.value = true
  try {
    run.value = row.lastRunId ? await YjApi.getFeishuAuditRun(Number(row.lastRunId)) : undefined
    items.value = row.lastRunId
      ? await YjApi.getFeishuAuditItems(Number(row.lastRunId), Number(row.id))
      : []
    if (items.value.length === 0) {
      items.value = await YjApi.getFeishuAuditItems(undefined, Number(row.id))
    }
  } finally {
    detailLoading.value = false
  }
}

const syncDetailRowFromRoute = async () => {
  const documentId = Number(route.query.documentId)
  if (!documentId) {
    detailRow.value = undefined
    return
  }
  detailRow.value = list.value.find((item) => Number(item.id) === documentId)
  if (!detailRow.value) {
    detailRow.value = await YjApi.getFeishuAuditDocument(documentId)
  }
  await loadDetail(detailRow.value)
}

const statusLabel = (status: any) => {
  const labels: Record<string, string> = {
    NEW: '未采集',
    PROCESSING: '处理中',
    COLLECTED: '已采集',
    NO_JOBS: '无岗位',
    SKIPPED: '已采集，未重复读取',
    PARTIAL_FAILED: '部分失败',
    FAILED: '采集失败'
  }
  return labels[String(status)] || String(status || '未知')
}

const statusType = (status: any) => {
  if (status === 'COLLECTED') return 'success'
  if (status === 'SKIPPED' || status === 'NO_JOBS' || status === 'PROCESSING') return 'warning'
  if (status === 'PARTIAL_FAILED' || status === 'FAILED') return 'danger'
  return 'info'
}

const itemStatusLabel = (status: any) => {
  const labels: Record<string, string> = {
    EXTRACTED: '已解析',
    CREATED: '已新增',
    UPDATED: '已更新',
    SKIPPED: '已跳过',
    FAILED: '失败'
  }
  return labels[String(status)] || String(status || '未知')
}

const itemStatusType = (status: any) => {
  if (status === 'CREATED' || status === 'UPDATED') return 'success'
  if (status === 'EXTRACTED' || status === 'SKIPPED') return 'warning'
  if (status === 'FAILED') return 'danger'
  return 'info'
}

const getExternalUrl = (value: any) => {
  const url = String(value ?? '').trim()
  return /^https?:\/\//i.test(url) ? url : ''
}

const formatDateText = (value: any) => formatNullableDate(value)

watch(
  () => route.query.documentId,
  async () => {
    await syncDetailRowFromRoute()
  }
)

onMounted(getList)
</script>

<style scoped>
.document-name-cell {
  display: -webkit-box;
  overflow: hidden;
  white-space: normal;
  word-break: break-word;
  line-height: 20px;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
</style>
