<template>
  <template v-if="agentCallingRow">
    <ContentWrap>
      <div class="flex flex-wrap items-center justify-between gap-12px">
        <div>
          <div class="text-18px font-semibold">{{ getAgentCallTitle(agentCallingRow) }}调用测试</div>
          <div class="mt-4px max-w-900px text-13px text-gray-500">{{ getAgentId(agentCallingRow) }}</div>
        </div>
        <el-button @click="backToAgentList">
          <Icon icon="ep:back" class="mr-5px" />
          返回
        </el-button>
      </div>
    </ContentWrap>

    <ContentWrap>
      <el-form label-position="top">
        <el-form-item label="输入内容">
          <el-input
            v-model="agentCallInput"
            type="textarea"
            :rows="8"
            maxlength="4000"
            show-word-limit
            placeholder="请输入要发送给智能体的内容"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            :disabled="agentCallLoading"
            :loading="agentCallLoading"
            type="primary"
            @click="sendAgentCall"
          >
            <Icon icon="ep:promotion" class="mr-5px" />
            发送
          </el-button>
        </el-form-item>
        <el-form-item label="返回结果">
          <el-input
            v-model="agentCallResult"
            type="textarea"
            :rows="12"
            readonly
            placeholder="发送后在这里显示智能体返回结果"
          />
        </el-form-item>
      </el-form>
    </ContentWrap>
  </template>

  <template v-else-if="currentConfig.customerService">
    <ContentWrap>
      <div class="flex items-center justify-between">
        <div>
          <div class="text-18px font-semibold">{{ currentConfig.title }}</div>
          <div class="mt-4px text-13px text-gray-500">{{ currentConfig.description }}</div>
        </div>
        <el-button @click="getList">
          <Icon icon="ep:refresh" class="mr-5px" />
          刷新
        </el-button>
      </div>
    </ContentWrap>
    <ContentWrap>
      <div class="yj-chat">
        <div class="yj-chat__sessions">
          <el-input
            v-model="queryParams.keyword"
            clearable
            placeholder="搜索最近消息"
            @keyup.enter="handleQuery"
          >
            <template #append>
              <el-button @click="handleQuery">
                <Icon icon="ep:search" />
              </el-button>
            </template>
          </el-input>
          <div v-loading="loading" class="yj-chat__session-list">
            <button
              v-for="item in list"
              :key="item.id"
              class="yj-chat__session"
              :class="{ 'is-active': selectedRow?.id === item.id }"
              @click="selectSession(item)"
            >
              <div class="yj-chat__avatar">{{ getAvatarText(item) }}</div>
              <div class="min-w-0 flex-1 text-left">
                <div class="flex items-center justify-between gap-8px">
                  <span class="truncate font-medium">{{ getSessionTitle(item) }}</span>
                  <span class="shrink-0 text-12px text-gray-400">
                    {{ formatCell(item.last_message_time, { prop: 'last_message_time', label: '最近时间', type: 'datetime' }) }}
                  </span>
                </div>
                <div class="mt-4px truncate text-12px text-gray-500">
                  {{ item.last_message_content || '暂无消息' }}
                </div>
              </div>
              <el-badge v-if="Number(item.unread_count || 0) > 0" :value="item.unread_count" />
            </button>
          </div>
          <Pagination
            v-model:limit="queryParams.pageSize"
            v-model:page="queryParams.pageNo"
            :total="total"
            small
            @pagination="getList"
          />
        </div>
        <div class="yj-chat__window">
          <template v-if="selectedRow">
            <div class="yj-chat__header">
              <div>
                <div class="font-semibold">{{ getSessionTitle(selectedRow) }}</div>
                <div class="mt-4px text-12px text-gray-500">
                  学员 {{ getStudentName(selectedRow) }} / 客服 {{ getStaffName(selectedRow) }}
                </div>
              </div>
              <el-button plain @click="openRelated(selectedRow)">消息记录</el-button>
            </div>
            <div v-loading="messageLoading" class="yj-chat__messages">
              <div
                v-for="messageItem in messageList"
                :key="messageItem.id"
                class="yj-chat__message"
                :class="{ 'is-admin': isAdminMessage(messageItem) }"
              >
                <div class="yj-chat__message-avatar">{{ getMessageAvatarText(messageItem) }}</div>
                <div class="yj-chat__bubble">
                  <div class="mb-4px text-12px font-medium opacity-80">{{ getMessageSenderName(messageItem) }}</div>
                  <el-image
                    v-if="isImageMessage(messageItem)"
                    class="yj-chat__media-image"
                    :preview-src-list="[messageItem.content]"
                    :src="messageItem.content"
                    fit="cover"
                    preview-teleported
                  />
                  <video
                    v-else-if="isVideoMessage(messageItem)"
                    class="yj-chat__media-video"
                    :src="messageItem.content"
                    controls
                  ></video>
                  <div v-else class="whitespace-pre-wrap">{{ messageItem.content }}</div>
                  <div class="mt-6px text-11px opacity-70">
                    {{ formatCell(messageItem.create_time, { prop: 'create_time', label: '发送时间', type: 'datetime' }) }}
                  </div>
                </div>
              </div>
              <el-empty v-if="!messageLoading && messageList.length === 0" description="暂无消息" />
            </div>
          </template>
          <el-empty v-else description="请选择左侧会话" />
        </div>
      </div>
    </ContentWrap>
  </template>

  <template v-else>
    <ContentWrap>
      <div class="flex flex-wrap items-center justify-between gap-12px">
        <div>
          <div class="text-18px font-semibold">{{ currentConfig.title }}</div>
          <div class="mt-4px text-13px text-gray-500">{{ currentConfig.description }}</div>
        </div>
        <div class="flex flex-wrap items-center gap-8px">
          <el-button
            v-if="canSyncQwenPaw"
            :loading="syncQwenPawLoading"
            type="success"
            plain
            @click="handleSyncQwenPaw"
          >
            <Icon icon="ep:refresh" class="mr-5px" />
            同步 QwenPaw
          </el-button>
          <el-button type="primary" plain :disabled="currentConfig.readonly" @click="openForm('create')">
            <Icon icon="ep:plus" class="mr-5px" />
            新增
          </el-button>
        </div>
      </div>
    </ContentWrap>

    <ContentWrap>
      <el-form
        ref="queryFormRef"
        :inline="true"
        :model="queryParams"
        class="-mb-15px"
        label-width="96px"
      >
        <el-form-item label="关键词" prop="keyword">
          <el-input
            v-model="queryParams.keyword"
            class="!w-240px"
            clearable
            :placeholder="currentConfig.keywordPlaceholder || '请输入关键词'"
            @keyup.enter="handleQuery"
          />
        </el-form-item>
        <el-form-item v-for="field in searchFields" :key="field.prop" :label="field.label" :prop="field.prop">
          <component
            :is="getSearchComponent(field)"
            v-model="queryParams[field.prop]"
            class="!w-220px"
            clearable
            :placeholder="`请选择${field.label}`"
            v-bind="getSearchBind(field)"
          >
            <el-option
              v-for="option in getFieldOptions(field)"
              :key="String(option.value)"
              :label="option.label"
              :value="option.value"
            />
          </component>
        </el-form-item>
        <el-form-item v-if="currentConfig.searchCreateTime !== false" label="创建时间" prop="createTimeRange">
          <el-date-picker
            v-model="queryParams.createTimeRange"
            class="!w-260px"
            end-placeholder="结束日期"
            start-placeholder="开始日期"
            type="daterange"
            value-format="YYYY-MM-DD HH:mm:ss"
          />
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
        <el-table-column
          v-for="field in tableFields"
          :key="field.prop"
          :label="field.label"
          align="center"
          :prop="field.prop"
          :width="field.width"
          :min-width="field.minWidth"
        >
          <template #default="scope">
            <el-switch
              v-if="field.type === 'switch' && !currentConfig.readonly"
              v-model="scope.row[field.prop]"
              @change="handleInlineUpdate(scope.row, field)"
            />
            <el-link
              v-else-if="field.type === 'url' && getExternalUrl(scope.row[field.prop])"
              :href="getExternalUrl(scope.row[field.prop])"
              target="_blank"
              rel="noopener noreferrer"
              :title="getExternalUrl(scope.row[field.prop])"
            >
              {{ getExternalUrl(scope.row[field.prop]) }}
            </el-link>
            <el-tag v-else-if="hasFieldOptions(field)" :type="getOptionType(field, scope.row[field.prop])">
              {{ getOptionLabel(field, scope.row[field.prop]) }}
            </el-tag>
            <span v-else>{{ formatCell(scope.row[field.prop], field) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" align="center" fixed="right" min-width="260">
          <template #default="scope">
            <el-button link type="primary" @click="openDetail(scope.row.id)">详情</el-button>
            <el-button v-if="canEditRow(scope.row)" link type="primary" @click="openForm('update', scope.row.id)">
              {{ currentConfig.resource === 'student-audit' ? '修改' : '编辑' }}
            </el-button>
            <el-button v-if="canCallAgentRow(scope.row)" link type="success" @click="openAgentCall(scope.row)">
              调用
            </el-button>
            <el-button v-if="showRelatedTableAction" link type="primary" @click="openRelated(scope.row)">
              {{ currentConfig.related?.title }}
            </el-button>
            <el-button
              v-if="isFeishuCollectionTask(scope.row)"
              link
              type="success"
              @click="openFeishuAudit(scope.row)"
            >
              飞书审计
            </el-button>
            <template v-if="canAuditRow(scope.row)">
              <el-button link type="success" @click="openAudit(scope.row, true)">通过</el-button>
              <el-button link type="danger" @click="openAudit(scope.row, false)">驳回</el-button>
            </template>
            <el-button v-if="canDeleteRow(scope.row)" link type="danger" @click="handleDelete(scope.row.id)">
              删除
            </el-button>
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

  <Dialog
    v-model="formVisible"
    :title="formTitle"
    width="860"
    scroll
    :max-height="currentConfig.resource === 'student-audit' ? '420px' : '620px'"
  >
    <el-form
      v-if="currentConfig.resource === 'student-audit'"
      ref="formRef"
      v-loading="formLoading"
      class="student-audit-edit-form"
      :model="formData"
      :rules="formRules"
    >
      <el-descriptions :column="2" border>
        <el-descriptions-item
          v-for="field in studentAuditEditFields"
          :key="`${field.prop}-${field.label}`"
          :label="field.label"
        >
          <el-form-item v-if="field.prop === 'student_name'" prop="student_name">
            <el-input
              v-model="formData.student_name"
              clearable
              maxlength="50"
              placeholder="请输入学员名称"
              show-word-limit
            />
          </el-form-item>
          <span v-else>{{ formatStudentAuditValue(field) }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-form>
    <el-form v-else ref="formRef" v-loading="formLoading" :model="formData" :rules="formRules" label-width="110px">
      <template v-for="field in formFields" :key="field.prop">
        <el-form-item :label="field.label" :prop="field.prop">
          <Editor
            v-if="field.type === 'editor'"
            v-model="formData[field.prop]"
            height="260px"
            directory="yj-admin"
          />
          <el-input
            v-else-if="field.type === 'textarea'"
            v-model="formData[field.prop]"
            type="textarea"
            :rows="4"
            :placeholder="`请输入${field.label}`"
          />
          <el-select
            v-else-if="field.type === 'select'"
            v-model="formData[field.prop]"
            clearable
            :placeholder="`请选择${field.label}`"
          >
            <el-option
              v-for="option in getFieldOptions(field)"
              :key="String(option.value)"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-switch v-else-if="field.type === 'switch'" v-model="formData[field.prop]" />
          <el-input-number v-else-if="field.type === 'number'" v-model="formData[field.prop]" :min="0" />
          <el-date-picker
            v-else-if="field.type === 'date' || field.type === 'datetime'"
            v-model="formData[field.prop]"
            :type="field.type"
            value-format="YYYY-MM-DD HH:mm:ss"
            :placeholder="`请选择${field.label}`"
          />
          <el-input v-else v-model="formData[field.prop]" :placeholder="`请输入${field.label}`" />
        </el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button :disabled="formLoading" type="primary" @click="submitForm">
        {{ formType === 'update' ? '保存' : '确定' }}
      </el-button>
      <el-button
        v-if="canCollectNow"
        :disabled="formLoading"
        :loading="collectNowLoading"
        type="success"
        plain
        @click="handleCollectNow"
      >
        立即采集
      </el-button>
      <el-button @click="formVisible = false">取消</el-button>
    </template>
  </Dialog>

  <Dialog v-model="detailVisible" title="详情" width="860" scroll max-height="620px">
    <el-descriptions :column="2" border>
      <el-descriptions-item v-for="field in detailFields" :key="field.prop" :label="field.label">
        <div v-if="field.type === 'editor'" class="yj-rich" v-html="detailData[field.prop]"></div>
        <el-link
          v-else-if="field.type === 'url' && getExternalUrl(detailData[field.prop])"
          :href="getExternalUrl(detailData[field.prop])"
          target="_blank"
          rel="noopener noreferrer"
          :title="getExternalUrl(detailData[field.prop])"
        >
          打开岗位链接
        </el-link>
        <span v-else>{{ formatCell(detailData[field.prop], field) }}</span>
      </el-descriptions-item>
    </el-descriptions>
    <div v-if="showDetailAttachments" v-loading="detailAttachmentLoading" class="yj-detail-attachments">
      <div class="yj-detail-attachments__title">资质材料</div>
      <div v-if="detailAttachmentImages.length > 0" class="yj-detail-attachments__grid">
        <div
          v-for="attachment in detailAttachmentImages"
          :key="attachment.id || attachment.file_path"
          class="yj-detail-attachments__item"
        >
          <el-image
            class="yj-detail-attachments__image"
            :preview-src-list="detailAttachmentPreviewList"
            :src="getAttachmentImageUrl(attachment)"
            fit="contain"
            preview-teleported
          />
          <div class="yj-detail-attachments__name">{{ attachment.file_name || attachment.file_path }}</div>
        </div>
      </div>
      <el-empty v-else description="暂无资质材料" />
    </div>
  </Dialog>

  <Dialog v-model="auditVisible" :title="auditForm.approved ? '审核通过' : '审核驳回'" width="520">
    <el-form label-width="90px">
      <el-form-item label="审核结论">
        <el-tag :type="auditForm.approved ? 'success' : 'danger'">
          {{ auditForm.approved ? '通过' : '驳回' }}
        </el-tag>
      </el-form-item>
      <el-form-item label="审核原因">
        <el-input v-model="auditForm.auditReason" type="textarea" :rows="4" placeholder="请输入审核原因" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button type="primary" @click="submitAudit">确定</el-button>
      <el-button @click="auditVisible = false">取消</el-button>
    </template>
  </Dialog>

  <Dialog v-model="feishuAuditVisible" title="飞书岗位采集审计" width="1180" scroll max-height="760px">
    <div v-loading="feishuAuditLoading" class="space-y-16px">
      <el-table :data="feishuAuditRuns" :show-overflow-tooltip="true" :stripe="true">
        <el-table-column label="运行编号" prop="id" width="90" />
        <el-table-column label="状态" prop="status" width="120">
          <template #default="scope">
            <el-tag :type="feishuRunStatusType(scope.row.status)">
              {{ feishuRunStatusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文档" width="90">
          <template #default="scope">
            {{ scope.row.documentsProcessed || 0 }}/{{ scope.row.documentsSeen || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="岗位结果" min-width="220">
          <template #default="scope">
            新增 {{ scope.row.jobsCreated || 0 }} / 跳过 {{ scope.row.jobsSkipped || 0 }} /
            失败 {{ scope.row.jobsFailed || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="开始时间" prop="startedAt" width="180" />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="selectFeishuAuditRun(scope.row)">查看明细</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-divider content-position="left">文档处理</el-divider>
      <el-table :data="feishuAuditDocuments" :show-overflow-tooltip="true" :stripe="true">
        <el-table-column label="文档名称" prop="documentName" min-width="230" />
        <el-table-column label="采集状态" prop="status" width="130" />
        <el-table-column label="解析岗位" prop="extractedCount" width="100" />
        <el-table-column label="新增" prop="createdCount" width="80" />
        <el-table-column label="跳过" prop="skippedCount" width="80" />
        <el-table-column label="失败" prop="failedCount" width="80" />
        <el-table-column label="错误" prop="lastError" min-width="220" />
      </el-table>
      <el-divider content-position="left">AI 解析与正式岗位回查</el-divider>
      <el-table :data="feishuAuditItems" :show-overflow-tooltip="true" :stripe="true">
        <el-table-column label="#" prop="itemIndex" width="60" />
        <el-table-column label="岗位名称" prop="name" min-width="190" />
        <el-table-column label="企业名称" prop="companyName" min-width="180" />
        <el-table-column label="来源" prop="sourceCode" width="110" />
        <el-table-column label="正式岗位编号" prop="targetPostId" width="120" />
        <el-table-column label="状态" prop="status" width="110" />
        <el-table-column label="错误" prop="errorMessage" min-width="220" />
      </el-table>
      <el-empty
        v-if="!feishuAuditLoading && feishuAuditRuns.length === 0"
        description="暂无飞书采集运行记录"
      />
    </div>
  </Dialog>

  <Dialog v-model="relatedVisible" :title="relatedTitle" width="980" scroll max-height="680px">
    <div v-if="activeRelated" class="space-y-16px">
      <div class="flex flex-wrap items-center justify-between gap-12px">
        <el-input
          v-if="activeRelated.searchable"
          v-model="relatedQuery.keyword"
          class="!w-240px"
          clearable
          placeholder="请输入关键词"
          @keyup.enter="getRelatedList"
        />
        <div class="ml-auto">
          <el-button @click="getRelatedList">
            <Icon icon="ep:refresh" class="mr-5px" />
            刷新
          </el-button>
          <el-button v-if="!isActiveRelatedReadonly" type="primary" plain @click="openRelatedForm('create')">
            <Icon icon="ep:plus" class="mr-5px" />
            新增
          </el-button>
        </div>
      </div>
      <el-table v-loading="relatedLoading" :data="relatedList" :show-overflow-tooltip="true" :stripe="true">
        <el-table-column label="编号" align="center" prop="id" width="90" />
        <el-table-column
          v-for="field in getTableFields(activeRelated.fields)"
          :key="field.prop"
          :label="field.label"
          align="center"
          :prop="field.prop"
          :width="field.width"
          :min-width="field.minWidth"
        >
          <template #default="scope">
            <el-tag v-if="hasFieldOptions(field)" :type="getOptionType(field, scope.row[field.prop])">
              {{ getOptionLabel(field, scope.row[field.prop]) }}
            </el-tag>
            <span v-else>{{ formatCell(scope.row[field.prop], field) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-if="showRelatedOperationColumn"
          label="操作"
          align="center"
          fixed="right"
          width="190"
        >
          <template #default="scope">
            <el-button v-if="!isActiveRelatedReadonly" link type="primary" @click="openRelatedForm('update', scope.row.id)">编辑</el-button>
            <el-button
              v-if="activeRelated.publishable"
              link
              type="success"
              @click="publishRelated(scope.row.id)"
            >
              发布
            </el-button>
            <el-button v-if="!isActiveRelatedReadonly" link type="danger" @click="deleteRelated(scope.row.id)">删除</el-button>
          </template>
        </el-table-column>
        <el-table-column
          v-if="canOpenNestedRelated"
          label="查看本次采集信息"
          align="center"
          fixed="right"
          width="160"
        >
          <template #default="scope">
            <el-button link type="primary" @click="openNestedRelated(scope.row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
      <Pagination
        v-model:limit="relatedQuery.pageSize"
        v-model:page="relatedQuery.pageNo"
        :total="relatedTotal"
        @pagination="getRelatedList"
      />
    </div>
  </Dialog>

  <Dialog v-model="relatedFormVisible" :title="relatedFormTitle" width="760" scroll max-height="620px">
    <el-form ref="relatedFormRef" v-loading="relatedFormLoading" :model="relatedFormData" :rules="relatedFormRules" label-width="110px">
      <template v-for="field in relatedFormFields" :key="field.prop">
        <el-form-item :label="field.label" :prop="field.prop">
          <Editor
            v-if="field.type === 'editor'"
            v-model="relatedFormData[field.prop]"
            height="260px"
            directory="yj-admin"
          />
          <el-input
            v-else-if="field.type === 'textarea'"
            v-model="relatedFormData[field.prop]"
            type="textarea"
            :rows="4"
            :placeholder="`请输入${field.label}`"
          />
          <el-select
            v-else-if="field.type === 'select'"
            v-model="relatedFormData[field.prop]"
            clearable
            :placeholder="`请选择${field.label}`"
          >
            <el-option
              v-for="option in getFieldOptions(field)"
              :key="String(option.value)"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-switch v-else-if="field.type === 'switch'" v-model="relatedFormData[field.prop]" />
          <el-input-number v-else-if="field.type === 'number'" v-model="relatedFormData[field.prop]" :min="0" />
          <el-date-picker
            v-else-if="field.type === 'date' || field.type === 'datetime'"
            v-model="relatedFormData[field.prop]"
            :type="field.type"
            value-format="YYYY-MM-DD HH:mm:ss"
            :placeholder="`请选择${field.label}`"
          />
          <el-input v-else v-model="relatedFormData[field.prop]" :placeholder="`请输入${field.label}`" />
        </el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button :disabled="relatedFormLoading" type="primary" @click="submitRelatedForm">确定</el-button>
      <el-button @click="relatedFormVisible = false">取消</el-button>
    </template>
  </Dialog>

  <Dialog v-model="nestedRelatedVisible" :title="nestedRelatedTitle" width="1080" scroll max-height="680px">
    <div v-if="nestedRelatedConfig" class="space-y-16px">
      <div class="flex flex-wrap items-center justify-between gap-12px">
        <el-input
          v-if="nestedRelatedConfig.searchable"
          v-model="nestedRelatedQuery.keyword"
          class="!w-240px"
          clearable
          placeholder="请输入关键词"
          @keyup.enter="getNestedRelatedList"
        />
        <div class="ml-auto">
          <el-button @click="getNestedRelatedList">
            <Icon icon="ep:refresh" class="mr-5px" />
            刷新
          </el-button>
        </div>
      </div>
      <el-table v-loading="nestedRelatedLoading" :data="nestedRelatedList" :show-overflow-tooltip="true" :stripe="true">
        <el-table-column label="编号" align="center" prop="id" width="90" />
        <el-table-column
          v-for="field in nestedRelatedFields"
          :key="field.prop"
          :label="field.label"
          align="center"
          :prop="field.prop"
          :width="field.width"
          :min-width="field.minWidth"
        >
          <template #default="scope">
            <el-tag v-if="hasFieldOptions(field)" :type="getOptionType(field, scope.row[field.prop])">
              {{ getOptionLabel(field, scope.row[field.prop]) }}
            </el-tag>
            <span v-else>{{ formatCell(scope.row[field.prop], field) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <Pagination
        v-model:limit="nestedRelatedQuery.pageSize"
        v-model:page="nestedRelatedQuery.pageNo"
        :total="nestedRelatedTotal"
        @pagination="getNestedRelatedList"
      />
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { formatDate, formatNullableDate } from '@/utils/formatTime'
import { getStrDictOptions } from '@/utils/dict'
import { useDictStoreWithOut } from '@/store/modules/dict'
import { useI18n } from '@/hooks/web/useI18n'
import { useMessage } from '@/hooks/web/useMessage'
import { FeishuAuditRun, YjApi, YjRecord } from '@/api/yj'
import {
  fallbackConfig,
  YjField,
  YjOption,
  YjRelatedConfig,
  YjResourceConfig,
  yjResourceConfigs
} from './config'

defineOptions({ name: 'YjResource' })

const message = useMessage()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const dictStore = useDictStoreWithOut()

const currentConfig = computed(() => {
  const metaQuery = route.meta?.query as Record<string, any> | undefined
  const resource = String(metaQuery?.resource || route.query.resource || fallbackConfig.resource)
  return yjResourceConfigs[resource] || fallbackConfig
})

const remoteOptions = ref<Record<string, YjOption[]>>({})

const loading = ref(false)
const list = ref<YjRecord[]>([])
const total = ref(0)
const selectedRow = ref<YjRecord>()
const queryFormRef = ref()
const queryParams = reactive<Record<string, any>>({
  pageNo: 1,
  pageSize: 10,
  keyword: '',
  createTimeRange: []
})

const tableFields = computed(() => getTableFields(currentConfig.value.fields))
const searchFields = computed(() => currentConfig.value.fields.filter((field) => field.search))
const formFields = computed(() =>
  getFormFields(currentConfig.value.fields, currentConfig.value.editableFields)
)
const showRelatedTableAction = computed(() =>
  Boolean(currentConfig.value.related) && currentConfig.value.resource !== 'enterprise-audit'
)
const detailFields = computed(() => [
  { prop: 'id', label: '编号' },
  ...currentConfig.value.fields.filter((field) => field.detail !== false),
  { prop: 'create_time', label: '创建时间', type: 'datetime' as const },
  { prop: 'update_time', label: '更新时间', type: 'datetime' as const }
])
const studentAuditEditFields = computed(() => {
  if (currentConfig.value.resource !== 'student-audit') return []
  const seen = new Set<string>()
  return detailFields.value.filter((field) => {
    if (seen.has(field.prop)) return false
    seen.add(field.prop)
    return true
  })
})

const AUDIT_STATUS_PENDING = 1
const AUDIT_STATUS_APPROVED = 2
const AUDIT_STATUS_REJECTED = 3

const getAuditStatus = (row: YjRecord) => Number(row.audit_status ?? row.auditStatus)

const canAuditRow = (row: YjRecord) => {
  if (!currentConfig.value.audit) return false
  return getAuditStatus(row) === AUDIT_STATUS_PENDING
}

const canEditRow = (_row: YjRecord) => {
  if (currentConfig.value.resource === 'student-audit') return Boolean(_row.id)
  if (currentConfig.value.readonly) return false
  return true
}

const canDeleteRow = (_row: YjRecord) => {
  if (currentConfig.value.readonly) return false
  return currentConfig.value.resource !== 'student-audit'
}

const getTableFields = (fields: YjField[]) => fields.filter((field) => field.table !== false)
const getFormFields = (fields: YjField[], editableFields?: string[]) => {
  if (editableFields) {
    return fields.filter((field) => editableFields.includes(field.prop))
  }
  return fields.filter(
    (field) =>
      field.form !== false &&
      !field.readonly &&
      field.prop !== 'create_time' &&
      field.prop !== 'update_time'
  )
}

const getOptionKey = (field: YjField) =>
  [field.optionsResource, field.optionLabelProp || 'name', field.optionValueProp || 'id'].join(':')

const getConfigFieldTree = (config: YjResourceConfig | undefined): YjField[] => {
  if (!config) return []
  return [
    ...config.fields,
    ...getConfigFieldTree(config.related ? yjResourceConfigs[config.related.resource] : undefined)
  ]
}

const getOptionFields = () => getConfigFieldTree(currentConfig.value).filter((field) => field.optionsResource)

const getDictFields = () => getConfigFieldTree(currentConfig.value).filter((field) => field.dictType)

const refreshMissingDictOptions = async () => {
  const dictFields = getDictFields()
  if (dictFields.some((field) => getStrDictOptions(field.dictType!).length === 0)) {
    await dictStore.resetDict()
  }
}

const loadRemoteOptions = async () => {
  const fields = getOptionFields()
  await Promise.all(fields.map(async (field) => {
    const key = getOptionKey(field)
    if (remoteOptions.value[key]) {
      return
    }
    const labelProp = field.optionLabelProp || 'name'
    const valueProp = field.optionValueProp || 'id'
    const rows: YjRecord[] = []
    let pageNo = 1
    let total = 0
    do {
      const data = await YjApi.getPage(field.optionsResource!, { pageNo, pageSize: 200 })
      rows.push(...(data.list || []))
      total = data.total || rows.length
      pageNo += 1
    } while (rows.length < total)
    remoteOptions.value[key] = rows.map((row) => ({
      label: formatValue(row[labelProp]),
      value: row[valueProp]
    }))
  }))
}

const hasOwn = (object: object, key: string) => Object.prototype.hasOwnProperty.call(object, key)

const getFieldQueryDefaultValue = (field: YjField) => {
  if (hasOwn(field, 'queryDefaultValue')) {
    return field.queryDefaultValue
  }
  return undefined
}

const resetDynamicQuery = () => {
  for (const field of currentConfig.value.fields) {
    if (field.search) {
      queryParams[field.prop] = getFieldQueryDefaultValue(field)
    }
  }
}

const QWENPAW_AGENT_ID_PREFIX = 'feixingxueyuan-'

const agentCallingRow = ref<YjRecord>()
const agentCallLoading = ref(false)
const agentCallInput = ref('')
const agentCallResult = ref('')

const getAgentId = (row?: YjRecord) => String(row?.agent_id || row?.agentId || '').trim()

const canCallAgentRow = (row: YjRecord) => {
  return currentConfig.value.resource === 'agent' && getAgentId(row).startsWith(QWENPAW_AGENT_ID_PREFIX)
}

const getAgentCallTitle = (row: YjRecord) => String(row.name || getAgentId(row) || '智能体')

const openAgentCall = async (row: YjRecord) => {
  agentCallingRow.value = row
  agentCallInput.value = ''
  agentCallResult.value = ''
  await router.replace({ query: { ...route.query, callId: String(row.id) } })
}

const backToAgentList = async () => {
  agentCallingRow.value = undefined
  agentCallInput.value = ''
  agentCallResult.value = ''
  const nextQuery = { ...route.query }
  delete nextQuery.callId
  await router.replace({ query: nextQuery })
}

const sendAgentCall = async () => {
  const row = agentCallingRow.value
  const input = agentCallInput.value.trim()
  if (!row) return
  if (!input) {
    message.warning('请输入要发送的内容')
    return
  }
  const agentId = getAgentId(row)
  if (!agentId) {
    message.warning('当前智能体未配置 agent_id')
    return
  }

  agentCallLoading.value = true
  agentCallResult.value = ''
  try {
    const result = await YjApi.callQwenPawAgent({
      id: row.id,
      agentId,
      question: input,
      sessionId: `yj-agent-call-${row.id}-${Date.now()}`
    })
    agentCallResult.value = formatAgentCallResult(result)
  } catch (error: any) {
    agentCallResult.value = error?.message || '智能体调用失败'
    message.error('智能体调用失败')
  } finally {
    agentCallLoading.value = false
  }
}

const formatAgentCallResult = (result: any) => {
  if (result?.content) return String(result.content)
  if (typeof result === 'string') return result
  return JSON.stringify(result, null, 2)
}

const syncAgentCallingRowFromRoute = async () => {
  const callId = Number(route.query.callId)
  if (currentConfig.value.resource !== 'agent' || !callId) return
  const existing = list.value.find((item) => Number(item.id) === callId)
  const row = existing || normalizeRow(await YjApi.get('agent', callId))
  if (canCallAgentRow(row)) {
    agentCallingRow.value = row
  }
}

const buildParams = (params: Record<string, any>) => {
  const result: Record<string, any> = {
    pageNo: params.pageNo,
    pageSize: params.pageSize
  }
  if (params.keyword) {
    result.keyword = params.keyword
  }
  for (const field of searchFields.value) {
    const value = params[field.prop]
    if (value !== undefined && value !== null && value !== '') {
      result[field.prop] = value
    }
  }
  if (params.createTimeRange?.length === 2) {
    result.beginCreateTime = params.createTimeRange[0]
    result.endCreateTime = params.createTimeRange[1]
  }
  return result
}

const getList = async () => {
  loading.value = true
  try {
    const data = await YjApi.getPage(currentConfig.value.resource, buildParams(queryParams))
    const currentSelectedId = selectedRow.value?.id
    list.value = normalizeRows(data.list || [])
    total.value = data.total || 0
    await syncAgentCallingRowFromRoute()
    if (currentConfig.value.customerService && currentSelectedId) {
      const latestSelected = list.value.find((item) => String(item.id) === String(currentSelectedId))
      if (latestSelected) {
        selectedRow.value = latestSelected
      }
    }
    if (currentConfig.value.customerService && !selectedRow.value && list.value.length > 0) {
      await selectSession(list.value[0])
    }
  } finally {
    loading.value = false
  }
}

const handleQuery = () => {
  queryParams.pageNo = 1
  getList()
}

const resetQuery = () => {
  queryFormRef.value?.resetFields()
  queryParams.keyword = ''
  queryParams.createTimeRange = []
  resetDynamicQuery()
  handleQuery()
}

watch(
  () => currentConfig.value.resource,
  async () => {
    selectedRow.value = undefined
    agentCallingRow.value = undefined
    agentCallInput.value = ''
    agentCallResult.value = ''
    queryParams.pageNo = 1
    queryParams.pageSize = 10
    queryParams.keyword = ''
    queryParams.createTimeRange = []
    resetDynamicQuery()
    await refreshMissingDictOptions()
    await loadRemoteOptions()
    getList()
  },
  { immediate: true }
)

watch(
  () => route.query.callId,
  async () => {
    if (!route.query.callId) {
      agentCallingRow.value = undefined
      return
    }
    await syncAgentCallingRowFromRoute()
  }
)

const formVisible = ref(false)
const formLoading = ref(false)
const formType = ref<'create' | 'update'>('create')
const formTitle = computed(() => {
  const action = formType.value === 'create' ? '新增' : currentConfig.value.resource === 'student-audit' ? '修改' : '编辑'
  return `${action}${currentConfig.value.title}`
})
const formData = ref<YjRecord>({})
const formRef = ref()
const formRules = computed(() => buildRules(formFields.value))
const collectNowLoading = ref(false)
const canCollectNow = computed(() => currentConfig.value.resource === 'collection-task')
const feishuAuditVisible = ref(false)
const feishuAuditLoading = ref(false)
const feishuAuditRuns = ref<FeishuAuditRun[]>([])
const feishuAuditDocuments = ref<YjRecord[]>([])
const feishuAuditItems = ref<YjRecord[]>([])
const selectedFeishuAuditRun = ref<FeishuAuditRun>()
const syncQwenPawLoading = ref(false)
const canSyncQwenPaw = computed(() => currentConfig.value.resource === 'agent')

const resolveStudentCustomerInfoId = async (data: YjRecord) => {
  const existingId = Number(data.customer_info_id)
  if (Number.isInteger(existingId) && existingId > 0) {
    return existingId
  }

  const customerAccountId = Number(data.customer_account_id)
  if (!Number.isInteger(customerAccountId) || customerAccountId <= 0) {
    return undefined
  }

  const result = await YjApi.getPage('customer-info', {
    pageNo: 1,
    pageSize: 1,
    customer_account_id: customerAccountId
  })
  const customerInfoId = Number(result.list?.[0]?.id)
  if (Number.isInteger(customerInfoId) && customerInfoId > 0) {
    data.customer_info_id = customerInfoId
    return customerInfoId
  }
  return undefined
}

const openForm = async (type: 'create' | 'update', id?: number) => {
  formType.value = type
  await refreshMissingDictOptions()
  formVisible.value = true
  formData.value = buildEmptyForm(formFields.value)
  await nextTick()
  formRef.value?.clearValidate()
  if (type === 'update' && id) {
    formLoading.value = true
    try {
      formData.value = normalizeRow(await YjApi.get(currentConfig.value.resource, id))
      if (currentConfig.value.resource === 'student-audit') {
        await resolveStudentCustomerInfoId(formData.value)
      }
    } finally {
      formLoading.value = false
    }
  }
}

const submitForm = async () => {
  const valid = await formRef.value?.validate()
  if (!valid) return
  formLoading.value = true
  try {
    const data = sanitizeFormData(formData.value, formFields.value)
    if (currentConfig.value.resource === 'student-audit') {
      const customerInfoId = await resolveStudentCustomerInfoId(formData.value)
      if (!customerInfoId) {
        message.error('学员资料不存在，无法保存')
        return
      }
      await YjApi.update('customer-info', {
        id: customerInfoId,
        real_name: formData.value.student_name
      })
      message.success(t('common.updateSuccess'))
    } else if (formType.value === 'create') {
      await YjApi.create(currentConfig.value.resource, data)
      message.success(t('common.createSuccess'))
    } else {
      await YjApi.update(currentConfig.value.resource, data)
      message.success(t('common.updateSuccess'))
    }
    formVisible.value = false
    await getList()
  } finally {
    formLoading.value = false
  }
}

const handleCollectNow = async () => {
  if (!canCollectNow.value) return
  const id = Number(formData.value.id)
  if (formType.value === 'create' || !id) {
    message.warning('请先保存采集配置')
    return
  }
  collectNowLoading.value = true
  try {
    await YjApi.collectNow(id)
    message.success('已触发立即采集')
    await getList()
  } finally {
    collectNowLoading.value = false
  }
}

const isFeishuCollectionTask = (row: YjRecord) =>
  currentConfig.value.resource === 'collection-task'
  && ['feishu_folder', 'feishu_folder_v2'].includes(String(row.collection_channel || ''))

const feishuRunStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    RUNNING: '运行中',
    SUCCESS: '成功',
    PARTIAL_FAILED: '部分失败',
    FAILED: '失败',
    DRY_RUN: '干跑'
  }
  return labels[status] || status || '未知'
}

const feishuRunStatusType = (status: string) => {
  if (status === 'SUCCESS') return 'success'
  if (status === 'PARTIAL_FAILED' || status === 'RUNNING') return 'warning'
  if (status === 'FAILED') return 'danger'
  return 'info'
}

const loadFeishuAuditDetail = async (runId: number) => {
  feishuAuditLoading.value = true
  try {
    const [documents, items] = await Promise.all([
      YjApi.getFeishuAuditDocuments(runId),
      YjApi.getFeishuAuditItems(runId)
    ])
    feishuAuditDocuments.value = documents
    feishuAuditItems.value = items
  } finally {
    feishuAuditLoading.value = false
  }
}

const selectFeishuAuditRun = async (run: FeishuAuditRun) => {
  selectedFeishuAuditRun.value = run
  await loadFeishuAuditDetail(run.id)
}

const openFeishuAudit = async (row: YjRecord) => {
  feishuAuditVisible.value = true
  feishuAuditLoading.value = true
  feishuAuditDocuments.value = []
  feishuAuditItems.value = []
  try {
    feishuAuditRuns.value = await YjApi.getFeishuAuditRuns(String(row.collection_key || ''))
    if (feishuAuditRuns.value.length > 0) {
      await selectFeishuAuditRun(feishuAuditRuns.value[0])
    }
  } finally {
    feishuAuditLoading.value = false
  }
}

const handleSyncQwenPaw = async () => {
  if (!canSyncQwenPaw.value) return
  await message.confirm('确认从 QwenPaw 工作区同步智能体？')
  syncQwenPawLoading.value = true
  try {
    const result = await YjApi.syncQwenPawAgents()
    message.success(
      `同步完成：共 ${result.total || 0} 个，新增 ${result.created || 0} 个，更新 ${result.updated || 0} 个，删除 ${result.deleted || 0} 个，跳过 ${result.skipped || 0} 个`
    )
    await getList()
  } finally {
    syncQwenPawLoading.value = false
  }
}

const handleInlineUpdate = async (row: YjRecord, field: YjField) => {
  await YjApi.update(currentConfig.value.resource, { id: row.id, [field.prop]: row[field.prop] })
  message.success(t('common.updateSuccess'))
}

const handleDelete = async (id: number) => {
  try {
    await message.delConfirm()
    await YjApi.delete(currentConfig.value.resource, id)
    message.success(t('common.delSuccess'))
    await getList()
  } catch {}
}

const detailVisible = ref(false)
const detailData = ref<YjRecord>({})
const detailAttachmentLoading = ref(false)
const detailAttachments = ref<YjRecord[]>([])
const showDetailAttachments = computed(() => currentConfig.value.resource === 'enterprise-audit')
const detailAttachmentImages = computed(() =>
  detailAttachments.value.filter((attachment) => Boolean(getAttachmentImageUrl(attachment)))
)
const detailAttachmentPreviewList = computed(() => detailAttachmentImages.value.map(getAttachmentImageUrl))

const openDetail = async (id: number) => {
  detailAttachments.value = []
  detailData.value = normalizeRow(await YjApi.get(currentConfig.value.resource, id))
  detailVisible.value = true
  if (showDetailAttachments.value) {
    await loadDetailAttachments(id)
  }
}

const loadDetailAttachments = async (companyId: number) => {
  detailAttachmentLoading.value = true
  try {
    const data = await YjApi.getPage('enterprise-audit-attachment', {
      pageNo: 1,
      pageSize: 100,
      company_id: companyId
    })
    detailAttachments.value = normalizeRows(data.list || [])
  } finally {
    detailAttachmentLoading.value = false
  }
}

const getAttachmentImageUrl = (attachment: YjRecord) => String(attachment.file_path || '').trim()

const auditVisible = ref(false)
const auditForm = reactive({
  id: undefined as number | undefined,
  approved: true,
  auditReason: ''
})

const openAudit = (row: YjRecord, approved: boolean) => {
  auditForm.id = row.id
  auditForm.approved = approved
  auditForm.auditReason = ''
  auditVisible.value = true
}

const submitAudit = async () => {
  if (!auditForm.id) return
  if (currentConfig.value.audit === 'enterprise') {
    await YjApi.auditEnterprise({
      id: auditForm.id,
      auditStatus: auditForm.approved ? 2 : 3,
      auditReason: auditForm.auditReason
    })
  } else {
    await YjApi.auditStudent({
      id: auditForm.id,
      auditStatus: auditForm.approved ? AUDIT_STATUS_APPROVED : AUDIT_STATUS_REJECTED,
      auditReason: auditForm.auditReason
    })
  }
  auditVisible.value = false
  message.success('审核处理成功')
  await getList()
}

const activeRelated = ref<YjRelatedConfig>()
const relatedVisible = ref(false)
const relatedLoading = ref(false)
const relatedList = ref<YjRecord[]>([])
const relatedTotal = ref(0)
const relatedParent = ref<YjRecord>()
const relatedQuery = reactive<Record<string, any>>({
  pageNo: 1,
  pageSize: 10,
  keyword: ''
})
const relatedTitle = computed(() =>
  activeRelated.value && relatedParent.value
    ? `${activeRelated.value.title} - #${relatedParent.value.id}`
    : '关联数据'
)
const isActiveRelatedReadonly = computed(() => {
  if (!activeRelated.value) return true
  return Boolean(yjResourceConfigs[activeRelated.value.resource]?.readonly)
})
const nestedRelatedConfig = computed(() => {
  if (!activeRelated.value) return undefined
  return yjResourceConfigs[activeRelated.value.resource]?.related
})
const canOpenNestedRelated = computed(() => Boolean(nestedRelatedConfig.value))
const showRelatedOperationColumn = computed(() => Boolean(activeRelated.value?.publishable) || !isActiveRelatedReadonly.value)

const openRelated = async (row: YjRecord) => {
  if (!currentConfig.value.related) return
  activeRelated.value = currentConfig.value.related
  relatedParent.value = row
  relatedVisible.value = true
  relatedQuery.pageNo = 1
  relatedQuery.keyword = ''
  await getRelatedList()
}

const getRelatedList = async () => {
  if (!activeRelated.value || !relatedParent.value) return
  relatedLoading.value = true
  try {
    const parentKey = activeRelated.value.parentKey || 'id'
    const data = await YjApi.getPage(activeRelated.value.resource, {
      pageNo: relatedQuery.pageNo,
      pageSize: relatedQuery.pageSize,
      keyword: relatedQuery.keyword,
      [activeRelated.value.foreignKey]: relatedParent.value[parentKey]
    })
    relatedList.value = normalizeRows(data.list || [])
    relatedTotal.value = data.total || 0
  } finally {
    relatedLoading.value = false
  }
}

const relatedFormVisible = ref(false)
const relatedFormLoading = ref(false)
const relatedFormType = ref<'create' | 'update'>('create')
const relatedFormTitle = computed(() =>
  `${relatedFormType.value === 'create' ? '新增' : '编辑'}${activeRelated.value?.title || ''}`
)
const relatedFormData = ref<YjRecord>({})
const relatedFormRef = ref()
const relatedFormFields = computed(() => (activeRelated.value ? getFormFields(activeRelated.value.fields) : []))
const relatedFormRules = computed(() => buildRules(relatedFormFields.value))

const openRelatedForm = async (type: 'create' | 'update', id?: number) => {
  if (!activeRelated.value || !relatedParent.value) return
  relatedFormType.value = type
  await refreshMissingDictOptions()
  relatedFormVisible.value = true
  relatedFormData.value = buildEmptyForm(relatedFormFields.value)
  relatedFormData.value[activeRelated.value.foreignKey] = relatedParent.value[activeRelated.value.parentKey || 'id']
  await nextTick()
  relatedFormRef.value?.clearValidate()
  if (type === 'update' && id) {
    relatedFormLoading.value = true
    try {
      relatedFormData.value = normalizeRow(await YjApi.get(activeRelated.value.resource, id))
    } finally {
      relatedFormLoading.value = false
    }
  }
}

const submitRelatedForm = async () => {
  if (!activeRelated.value) return
  const valid = await relatedFormRef.value?.validate()
  if (!valid) return
  relatedFormLoading.value = true
  try {
    const data = sanitizeFormData(relatedFormData.value, relatedFormFields.value)
    data[activeRelated.value.foreignKey] = relatedFormData.value[activeRelated.value.foreignKey]
    if (relatedFormType.value === 'create') {
      await YjApi.create(activeRelated.value.resource, data)
      message.success(t('common.createSuccess'))
    } else {
      await YjApi.update(activeRelated.value.resource, data)
      message.success(t('common.updateSuccess'))
    }
    relatedFormVisible.value = false
    await getRelatedList()
    await getList()
  } finally {
    relatedFormLoading.value = false
  }
}

const deleteRelated = async (id: number) => {
  if (!activeRelated.value) return
  try {
    await message.delConfirm()
    await YjApi.delete(activeRelated.value.resource, id)
    message.success(t('common.delSuccess'))
    await getRelatedList()
    await getList()
  } catch {}
}

const publishRelated = async (id: number) => {
  await message.confirm('确认发布该协议版本？')
  await YjApi.publishAgreementDetail({ id })
  message.success('发布成功')
  await getRelatedList()
}

const nestedRelatedVisible = ref(false)
const nestedRelatedLoading = ref(false)
const nestedRelatedList = ref<YjRecord[]>([])
const nestedRelatedTotal = ref(0)
const nestedRelatedParent = ref<YjRecord>()
const nestedRelatedQuery = reactive<Record<string, any>>({
  pageNo: 1,
  pageSize: 10,
  keyword: ''
})
const nestedRelatedTitle = computed(() =>
  nestedRelatedParent.value ? `查看本次采集信息 - #${nestedRelatedParent.value.id}` : '查看本次采集信息'
)
const nestedRelatedFields = computed(() => (nestedRelatedConfig.value ? getTableFields(nestedRelatedConfig.value.fields) : []))

const openNestedRelated = async (row: YjRecord) => {
  if (!nestedRelatedConfig.value) return
  nestedRelatedParent.value = row
  nestedRelatedVisible.value = true
  nestedRelatedQuery.pageNo = 1
  nestedRelatedQuery.keyword = ''
  await getNestedRelatedList()
}

const getNestedRelatedList = async () => {
  if (!nestedRelatedConfig.value || !nestedRelatedParent.value) return
  nestedRelatedLoading.value = true
  try {
    const parentKey = nestedRelatedConfig.value.parentKey || 'id'
    const data = await YjApi.getPage(nestedRelatedConfig.value.resource, {
      pageNo: nestedRelatedQuery.pageNo,
      pageSize: nestedRelatedQuery.pageSize,
      keyword: nestedRelatedQuery.keyword,
      [nestedRelatedConfig.value.foreignKey]: nestedRelatedParent.value[parentKey]
    })
    nestedRelatedList.value = normalizeRows(data.list || [])
    nestedRelatedTotal.value = data.total || 0
  } finally {
    nestedRelatedLoading.value = false
  }
}

const messageLoading = ref(false)
const messageList = ref<YjRecord[]>([])

const selectSession = async (row: YjRecord) => {
  selectedRow.value = row
  await getMessages(row)
}

const getMessages = async (row: YjRecord) => {
  messageLoading.value = true
  try {
    const data = await YjApi.getPage('customer-message', {
      pageNo: 1,
      pageSize: 100,
      session_id: row.id
    })
    messageList.value = normalizeRows(data.list || []).reverse()
  } finally {
    messageLoading.value = false
  }
}

const getStudentName = (row?: YjRecord) => formatName(row?.student_name, row?.session_from, '学员')

const getStaffName = (row?: YjRecord) => formatName(row?.staff_name, row?.session_to, '客服')

const getSessionTitle = (row: YjRecord) => `${getStudentName(row)} 的对话`

const getAvatarText = (row: YjRecord) => getNameInitials(getStudentName(row))

const getMessageSenderName = (messageItem: YjRecord) => {
  return isAdminMessage(messageItem)
    ? formatName(messageItem.staff_name || selectedRow.value?.staff_name, messageItem.session_from, '客服')
    : formatName(messageItem.student_name || selectedRow.value?.student_name, messageItem.session_from, '学员')
}

const getMessageAvatarText = (messageItem: YjRecord) => getNameInitials(getMessageSenderName(messageItem))

const isImageMessage = (messageItem: YjRecord) => messageItem.message_type === 'image' || messageItem.messageType === 'image'

const isVideoMessage = (messageItem: YjRecord) => messageItem.message_type === 'video' || messageItem.messageType === 'video'

const getNameInitials = (name: string) => {
  const normalized = name.trim()
  return normalized ? normalized.slice(0, 2) : '?'
}

const formatName = (name: any, id: any, fallbackPrefix: string) => {
  if (name !== undefined && name !== null && String(name).trim()) {
    return String(name).trim()
  }
  if (id !== undefined && id !== null && String(id).trim()) {
    return `${fallbackPrefix}${id}`
  }
  return fallbackPrefix
}

const isAdminMessage = (messageItem: YjRecord) => {
  const row = selectedRow.value
  return row ? String(messageItem.session_to) === String(row.session_from) : false
}

const getSearchComponent = (field: YjField) => {
  if (field.type === 'select' || field.type === 'switch') return 'el-select'
  if (field.type === 'number') return 'el-input-number'
  if (field.type === 'date' || field.type === 'datetime') return 'el-date-picker'
  return 'el-input'
}

const getSearchBind = (field: YjField) => {
  if (field.type === 'date' || field.type === 'datetime') {
    return { type: field.type, valueFormat: 'YYYY-MM-DD HH:mm:ss' }
  }
  return {}
}

const getFieldOptions = (field: YjField) => {
  if (field.options?.length) {
    return field.options
  }
  if (field.dictType) {
    return getStrDictOptions(field.dictType)
      .filter((dict) => !field.excludeValues?.some((value) => String(value) === String(dict.value)))
      .map((dict) => ({
      label: dict.label,
      value: dict.value,
      type: dict.colorType as any
      }))
  }
  if (field.optionsResource) {
    return remoteOptions.value[getOptionKey(field)] || []
  }
  if (field.type === 'switch') {
    const labels = field.switchLabels || { active: '启用', inactive: '停用' }
    return [
      { label: labels.active, value: true, type: 'success' as const },
      { label: labels.inactive, value: false, type: 'info' as const }
    ]
  }
  return []
}

const hasFieldOptions = (field: YjField) => getFieldOptions(field).length > 0

const getOptionLabel = (field: YjField, value: any) => {
  return getFieldOptions(field).find((option) => String(option.value) === String(value))?.label || formatValue(value)
}

const getOptionType = (field: YjField, value: any) => {
  return getFieldOptions(field).find((option) => String(option.value) === String(value))?.type
}

const formatCell = (value: any, field: YjField) => {
  if (hasFieldOptions(field)) return getOptionLabel(field, value)
  if (field.type === 'datetime') return formatNullableDate(value)
  if (field.type === 'date') return formatNullableDate(value, 'YYYY-MM-DD')
  if (field.type === 'switch') return formatSwitchValue(value, field)
  return formatValue(value)
}

const formatStudentAuditValue = (field: YjField) => formatCell(formData.value[field.prop], field)

const getExternalUrl = (value: any) => {
  const url = String(value ?? '').trim()
  return /^https?:\/\//i.test(url) ? url : ''
}

const formatSwitchValue = (value: any, field: YjField) => {
  const labels = field.switchLabels || { active: '启用', inactive: '停用' }
  return normalizeBool(value) ? labels.active : labels.inactive
}

const formatValue = (value: any) => {
  if (value === undefined || value === null || value === '') return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

const normalizeRows = (rows: YjRecord[]) => rows.map(normalizeRow)

const normalizeRow = (row: YjRecord) => {
  const result = { ...row }
  const fields = [...currentConfig.value.fields, ...(currentConfig.value.related?.fields || [])]
  for (const field of fields) {
    if (field.defaultValue !== undefined && (result[field.prop] === undefined || result[field.prop] === null)) {
      result[field.prop] = field.defaultValue
    } else if (
      (field.type === 'switch' ||
        Boolean(field.options?.length && field.options.every((option) => typeof option.value === 'boolean'))) &&
      field.prop in result
    ) {
      result[field.prop] = normalizeBool(result[field.prop])
    } else if ((field.type === 'date' || field.type === 'datetime') && field.prop in result) {
      result[field.prop] = normalizeDateValue(result[field.prop])
    }
  }
  return result
}

const normalizeDateValue = (value: any) => {
  if (value === undefined || value === null || value === '') {
    return undefined
  }
  return formatDate(value, 'YYYY-MM-DD HH:mm:ss')
}

const normalizeBool = (value: any) => {
  if (value === true || value === 1 || value === '1') return true
  if (value === false || value === 0 || value === '0') return false
  return Boolean(value)
}

const buildEmptyForm = (fields: YjField[]) => {
  const data: YjRecord = {}
  for (const field of fields) {
    if (field.defaultValue !== undefined) {
      data[field.prop] = field.defaultValue
    } else if (field.type === 'switch') {
      data[field.prop] = true
    } else if (field.type === 'number') {
      data[field.prop] = 0
    } else {
      data[field.prop] = undefined
    }
  }
  return data
}

const buildRules = (fields: YjField[]) => {
  const rules: Record<string, any[]> = {}
  for (const field of fields) {
    if (field.required) {
      rules[field.prop] = [{ required: true, message: `${field.label}不能为空`, trigger: 'blur' }]
    }
  }
  return rules
}

const sanitizeFormData = (data: YjRecord, fields: YjField[]) => {
  const result: YjRecord = {}
  if (data.id) result.id = data.id
  for (const field of fields) {
    result[field.prop] = sanitizeFieldValue(data[field.prop], field)
  }
  return result
}

const sanitizeFieldValue = (value: any, field: YjField) => {
  if (field.type === 'date' || field.type === 'datetime') {
    return normalizeDateValue(value)
  }
  return value
}
</script>

<style scoped lang="scss">
.student-audit-edit-form :deep(.el-form-item) {
  width: 100%;
  margin-bottom: 0;
}

.yj-chat {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  min-height: 620px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
}

.yj-chat__sessions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-right: 1px solid var(--el-border-color);
  background: #f8fafc;
}

.yj-chat__session-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.yj-chat__session {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
}

.yj-chat__session:hover,
.yj-chat__session.is-active {
  background: #fff;
}

.yj-chat__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  border-radius: 50%;
  color: #fff;
  background: var(--el-color-primary);
  font-size: 13px;
}

.yj-chat__window {
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: #fff;
}

.yj-chat__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
  padding: 0 16px;
  border-bottom: 1px solid var(--el-border-color);
}

.yj-chat__messages {
  flex: 1;
  min-height: 0;
  padding: 18px;
  overflow: auto;
  background: #f3f4f6;
}

.yj-chat__message {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
}

.yj-chat__message.is-admin {
  justify-content: flex-end;
}

.yj-chat__message.is-admin .yj-chat__message-avatar {
  background: var(--el-color-success);
}

.yj-chat__message-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  border-radius: 50%;
  color: #fff;
  background: var(--el-color-primary);
  font-size: 12px;
}

.yj-chat__bubble {
  max-width: min(560px, 72%);
  padding: 10px 12px;
  border-radius: 8px;
  background: #fff;
  line-height: 1.6;
}

.yj-chat__message.is-admin .yj-chat__bubble {
  background: #d9fdd3;
}

.yj-chat__media-image {
  display: block;
  width: 220px;
  height: 150px;
  border-radius: 6px;
  background: #eef2f7;
}

.yj-chat__media-video {
  display: block;
  width: 280px;
  max-width: 100%;
  height: 176px;
  border-radius: 6px;
  background: #111827;
}

.yj-rich {
  max-height: 320px;
  overflow: auto;
}

.yj-detail-attachments {
  margin-top: 16px;
}

.yj-detail-attachments__title {
  margin-bottom: 10px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.yj-detail-attachments__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.yj-detail-attachments__item {
  min-width: 0;
}

.yj-detail-attachments__image {
  display: block;
  width: 100%;
  height: 160px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: #f8fafc;
}

.yj-detail-attachments__name {
  margin-top: 6px;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 960px) {
  .yj-chat {
    grid-template-columns: 1fr;
  }

  .yj-chat__sessions {
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color);
  }
}
</style>
